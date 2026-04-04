"""
queue_watcher.py – Reads and processes queue.txt.

Format:
  • Plain lines: URL or artist/album name to download.
  • Lines starting with #: comments (status markers).
    # [✅ 2026-04-04] <url> → done
    # [❌] <url>           → error

Updates queue.txt in-place by prepending status comments.
"""

import datetime
import logging
import re
from pathlib import Path
from typing import Optional

from modules.config import config
from modules.database import QueueItem, db, init_db
from modules.downloader import download_item, enqueue

logger = logging.getLogger(__name__)

_STATUS_DONE = re.compile(r"^#\s*\[✅[^\]]*\]", re.UNICODE)
_STATUS_ERROR = re.compile(r"^#\s*\[❌[^\]]*\]", re.UNICODE)
_COMMENT = re.compile(r"^\s*#")


# ---------------------------------------------------------------------------
# Parse queue.txt
# ---------------------------------------------------------------------------

def _parse_queue_file(path: Path) -> list[dict]:
    """
    Parse queue.txt and return a list of entries:
    {"line": str, "query": str, "status": "pending"|"done"|"error", "index": int}
    """
    entries = []
    if not path.exists():
        return entries

    for i, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = raw_line.strip()
        if not line:
            continue

        if _STATUS_DONE.match(line):
            query = _extract_query_from_comment(line)
            entries.append({"line": raw_line, "query": query, "status": "done", "index": i})
        elif _STATUS_ERROR.match(line):
            query = _extract_query_from_comment(line)
            entries.append({"line": raw_line, "query": query, "status": "error", "index": i})
        elif _COMMENT.match(line):
            # Plain comment – ignore
            continue
        else:
            entries.append({"line": raw_line, "query": line, "status": "pending", "index": i})

    return entries


def _extract_query_from_comment(line: str) -> str:
    """Strip leading comment marker and status badge, return the original query."""
    # Remove leading #
    text = line.lstrip("#").strip()
    # Remove status badge e.g. [✅ 2026-04-04] or [❌]
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Write status back to queue.txt
# ---------------------------------------------------------------------------

def _update_queue_file(path: Path, entries: list[dict]) -> None:
    """Rewrite queue.txt reflecting current statuses."""
    today = datetime.date.today().isoformat()
    lines = []
    for entry in entries:
        if entry["status"] == "done":
            lines.append(f"# [✅ {today}] {entry['query']}")
        elif entry["status"] == "error":
            lines.append(f"# [❌] {entry['query']}")
        else:
            lines.append(entry["query"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_queue_file(queue_path: Optional[Path] = None) -> list[dict]:
    """
    Read queue.txt, download all pending items, and update the file with
    status markers. Returns a list of result dicts.
    """
    queue_path = queue_path or config.queue_file
    queue_path = Path(queue_path)

    if not queue_path.exists():
        logger.info("queue.txt not found: %s", queue_path)
        return []

    entries = _parse_queue_file(queue_path)
    pending = [e for e in entries if e["status"] == "pending"]
    logger.info("Queue: %d pending, %d done, %d error",
                len(pending),
                sum(1 for e in entries if e["status"] == "done"),
                sum(1 for e in entries if e["status"] == "error"))

    results = []
    for entry in entries:
        if entry["status"] != "pending":
            continue

        query = entry["query"]
        logger.info("Processing queue item: %s", query)

        try:
            db_item = enqueue(query)
            result = download_item(db_item.id)
            if result["success"]:
                entry["status"] = "done"
            else:
                entry["status"] = "error"
            result["query"] = query
            results.append(result)
        except Exception as exc:
            logger.error("Queue item failed (%s): %s", query, exc)
            entry["status"] = "error"
            results.append({"query": query, "success": False, "error": str(exc)})

    _update_queue_file(queue_path, entries)
    return results


def get_queue_status(queue_path: Optional[Path] = None) -> list[dict]:
    """Return parsed status of every entry in queue.txt without executing anything."""
    queue_path = queue_path or config.queue_file
    entries = _parse_queue_file(Path(queue_path))
    return [
        {"query": e["query"], "status": e["status"]}
        for e in entries
    ]


def add_to_queue_file(query: str, queue_path: Optional[Path] = None) -> None:
    """Append a new pending item to queue.txt."""
    queue_path = Path(queue_path or config.queue_file)
    with queue_path.open("a", encoding="utf-8") as fh:
        fh.write(query + "\n")
