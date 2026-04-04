"""
downloader.py – Wraps spotDL to download tracks/albums/artists/playlists.

• Downloads to _Temp first, then calls tagger + organizer.
• Updates QueueItem status in the database.
• Retry logic: max 3 attempts, 300 s delay between retries.
• Supports parallel downloads (max 2 concurrent workers).
"""

import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import datetime

from modules.config import config
from modules.database import QueueItem, SyncLog, db, init_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spotdl_cmd(query: str, output_dir: Path, fmt: str = None) -> list[str]:
    fmt = fmt or config.download_format
    return [
        sys.executable, "-m", "spotdl",
        "download", query,
        "--output", str(output_dir),
        "--format", fmt,
        "--bitrate", "320k",
        "--threads", "4",
        "--no-cache",
        "--print-errors",
    ]


def _run_spotdl(query: str, output_dir: Path) -> tuple[bool, str]:
    """Run spotDL synchronously. Returns (success, stderr)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = _spotdl_cmd(query, output_dir)
    logger.info("spotDL command: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if result.returncode == 0:
            return True, result.stderr
        logger.warning("spotDL exited %d: %s", result.returncode, result.stderr[-2000:])
        return False, result.stderr[-2000:]
    except subprocess.TimeoutExpired:
        return False, "Timeout after 3600 s"
    except Exception as exc:
        return False, str(exc)


def _collect_downloaded_files(temp_dir: Path) -> list[Path]:
    exts = {".flac", ".mp3", ".ogg", ".opus", ".m4a", ".wav"}
    return [p for p in temp_dir.rglob("*") if p.suffix.lower() in exts]


def _process_downloaded_files(files: list[Path]) -> None:
    """Tag and organise every downloaded file."""
    from modules.tagger import tag_file
    from modules.organizer import organize_file

    for f in files:
        try:
            tag_file(f)
        except Exception as exc:
            logger.error("Tagging failed for %s: %s", f, exc)
        try:
            organize_file(f)
        except Exception as exc:
            logger.error("Organising failed for %s: %s", f, exc)


def _update_queue(item_id: int, status: str, progress: float = 0.0, error: str = None) -> None:
    with db:
        QueueItem.update(
            status=status,
            progress=progress,
            error_message=error,
            date_modified=datetime.datetime.utcnow(),
        ).where(QueueItem.id == item_id).execute()


# ---------------------------------------------------------------------------
# Core download function
# ---------------------------------------------------------------------------

def download_item(item_id: int) -> dict:
    """
    Download a single QueueItem by its database ID.
    Returns a result dict with keys: success, id, retries, error.
    """
    init_db()
    with db:
        try:
            item = QueueItem.get_by_id(item_id)
        except QueueItem.DoesNotExist:
            return {"success": False, "id": item_id, "error": "QueueItem not found", "retries": 0}

    query = item.url or item.name
    if not query:
        _update_queue(item_id, "error", error="No URL or name provided")
        return {"success": False, "id": item_id, "error": "No URL or name", "retries": 0}

    temp_dir = config.temp_dir / f"dl_{item_id}"
    retry_max = config.retry_max
    retry_delay = config.retry_delay

    for attempt in range(1, retry_max + 1):
        _update_queue(item_id, "downloading", progress=0.0)
        logger.info("Downloading [%d] attempt %d/%d: %s", item_id, attempt, retry_max, query)

        success, stderr = _run_spotdl(query, temp_dir)

        if success:
            files = _collect_downloaded_files(temp_dir)
            logger.info("Downloaded %d file(s) for item %d", len(files), item_id)
            _update_queue(item_id, "downloading", progress=50.0)
            _process_downloaded_files(files)
            _update_queue(item_id, "done", progress=100.0)
            with db:
                QueueItem.update(retries=attempt - 1).where(QueueItem.id == item_id).execute()
            # Clean up temp folder
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            return {"success": True, "id": item_id, "retries": attempt - 1, "files": len(files)}

        # Failed – log and maybe retry
        with db:
            QueueItem.update(retries=attempt).where(QueueItem.id == item_id).execute()

        if attempt < retry_max:
            logger.warning(
                "Download failed (attempt %d/%d), retrying in %d s…",
                attempt, retry_max, retry_delay,
            )
            time.sleep(retry_delay)
        else:
            _update_queue(item_id, "error", error=stderr)
            with db:
                SyncLog.create(action="error", detail=f"Download failed: {query}\n{stderr}")
            return {"success": False, "id": item_id, "retries": attempt, "error": stderr}

    return {"success": False, "id": item_id, "retries": retry_max, "error": "Unknown"}


# ---------------------------------------------------------------------------
# Queue a new download
# ---------------------------------------------------------------------------

def enqueue(url_or_name: str, item_type: str = None) -> QueueItem:
    """
    Add a new entry to the download queue and return the QueueItem.
    item_type: 'track' | 'album' | 'artist' | 'playlist' | None (auto-detect)
    """
    init_db()
    if item_type is None:
        item_type = _detect_type(url_or_name)

    is_url = url_or_name.startswith("http")
    with db:
        item = QueueItem.create(
            url=url_or_name if is_url else None,
            name=None if is_url else url_or_name,
            type=item_type,
            status="queued",
        )
    logger.info("Enqueued item %d: %s", item.id, url_or_name)
    return item


def _detect_type(query: str) -> str:
    q = query.lower()
    if "spotify.com/track" in q or "spotify:track:" in q:
        return "track"
    if "spotify.com/album" in q or "spotify:album:" in q:
        return "album"
    if "spotify.com/artist" in q or "spotify:artist:" in q:
        return "artist"
    if "spotify.com/playlist" in q or "spotify:playlist:" in q:
        return "playlist"
    return "track"


# ---------------------------------------------------------------------------
# Process the full queue
# ---------------------------------------------------------------------------

def process_queue() -> list[dict]:
    """
    Process all 'queued' items using a thread pool.
    Returns list of result dicts.
    """
    init_db()
    with db:
        items = list(
            QueueItem.select()
            .where(QueueItem.status == "queued")
            .order_by(QueueItem.date_added)
        )

    if not items:
        logger.info("Queue is empty.")
        return []

    results = []
    max_workers = config.max_parallel
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(download_item, item.id): item for item in items}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                item = futures[future]
                result = {"success": False, "id": item.id, "error": str(exc), "retries": 0}
                _update_queue(item.id, "error", error=str(exc))
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Direct download (no queue persistence)
# ---------------------------------------------------------------------------

def download_now(url_or_name: str, item_type: str = None) -> dict:
    """
    Immediately download without persisting to the DB queue.
    Returns result dict.
    """
    item = enqueue(url_or_name, item_type)
    return download_item(item.id)
