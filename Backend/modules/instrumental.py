"""
instrumental.py – Searches for and downloads instrumental versions of tracks.

• Searches Spotify and YouTube for instrumental versions.
• Validates duration within ±10 seconds of the original.
• Downloads to Artisti/{Artist}/Strumentali/{Album} [Instrumental]/.
• Logs when an instrumental version is not found.
"""

import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from modules.config import config
from modules.organizer import sanitize
from modules.database import SyncLog, db, init_db

logger = logging.getLogger(__name__)

_DURATION_TOLERANCE = 10  # seconds


# ---------------------------------------------------------------------------
# Spotify search
# ---------------------------------------------------------------------------

def _get_spotify_token() -> Optional[str]:
    if not config.spotify_client_id or not config.spotify_client_secret:
        return None
    try:
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(config.spotify_client_id, config.spotify_client_secret),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as exc:
        logger.debug("Spotify token error: %s", exc)
        return None


def _spotify_search_instrumental(artist: str, title: str, duration_s: float) -> Optional[str]:
    """Return a Spotify track URL for an instrumental version, or None."""
    token = _get_spotify_token()
    if not token:
        return None

    queries = [
        f'"{title}" "{artist}" instrumental',
        f'"{title}" instrumental',
        f'"{title}" karaoke',
    ]
    headers = {"Authorization": f"Bearer {token}"}

    for q in queries:
        try:
            resp = requests.get(
                "https://api.spotify.com/v1/search",
                params={"q": q, "type": "track", "limit": 5},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            tracks = resp.json().get("tracks", {}).get("items", [])
            for t in tracks:
                t_title = (t.get("name") or "").lower()
                t_duration = t.get("duration_ms", 0) / 1000
                keywords = {"instrumental", "karaoke", "backing track", "minus one"}
                if any(kw in t_title for kw in keywords):
                    if abs(t_duration - duration_s) <= _DURATION_TOLERANCE:
                        return t.get("external_urls", {}).get("spotify")
        except Exception as exc:
            logger.debug("Spotify instrumental search error: %s", exc)
        time.sleep(0.5)

    return None


# ---------------------------------------------------------------------------
# YouTube search via yt-dlp
# ---------------------------------------------------------------------------

def _youtube_search_instrumental(artist: str, title: str, duration_s: float) -> Optional[str]:
    """Return a YouTube URL for an instrumental version, or None."""
    queries = [
        f"{artist} {title} instrumental",
        f"{artist} {title} karaoke",
        f"{title} instrumental official",
    ]
    for q in queries:
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "yt_dlp",
                    f"ytsearch5:{q}",
                    "--get-url",
                    "--get-duration",
                    "--no-playlist",
                    "--quiet",
                ],
                capture_output=True, text=True, timeout=30,
            )
            lines = result.stdout.strip().splitlines()
            # Output alternates: url, duration, url, duration…
            pairs = list(zip(lines[::2], lines[1::2]))
            for url, dur_str in pairs:
                dur_s = _parse_yt_duration(dur_str)
                if dur_s is not None and abs(dur_s - duration_s) <= _DURATION_TOLERANCE:
                    if re.search(r"instrumental|karaoke|backing|minus.?one", url, re.I):
                        return url
            # If no keyword match, take first duration-matching result
            for url, dur_str in pairs:
                dur_s = _parse_yt_duration(dur_str)
                if dur_s is not None and abs(dur_s - duration_s) <= _DURATION_TOLERANCE:
                    return url
        except Exception as exc:
            logger.debug("yt-dlp instrumental search failed: %s", exc)
    return None


def _parse_yt_duration(s: str) -> Optional[float]:
    parts = str(s).split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return float(parts[0])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Download via spotDL / yt-dlp
# ---------------------------------------------------------------------------

def _download_instrumental(url: str, dest_folder: Path) -> Optional[Path]:
    dest_folder.mkdir(parents=True, exist_ok=True)

    from urllib.parse import urlparse
    parsed = urlparse(url)
    is_spotify = (parsed.scheme == "spotify") or (
        parsed.netloc in {"open.spotify.com", "api.spotify.com"}
    )
    if is_spotify:
        cmd = [
            sys.executable, "-m", "spotdl",
            "download", url,
            "--output", str(dest_folder),
            "--format", config.download_format,
        ]
    else:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            url,
            "-x", "--audio-format", config.download_format,
            "-o", str(dest_folder / "%(title)s.%(ext)s"),
            "--quiet",
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            exts = {".flac", ".mp3", ".ogg", ".opus", ".m4a"}
            files = [p for p in dest_folder.rglob("*") if p.suffix.lower() in exts]
            return files[0] if files else None
    except Exception as exc:
        logger.error("Instrumental download failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_and_download_instrumental(
    artist: str,
    title: str,
    album: str,
    duration_s: float,
) -> Optional[Path]:
    """
    Find an instrumental version for the given track and download it.
    Returns the path of the downloaded file, or None if not found.
    """
    logger.info("Searching instrumental for: %s – %s", artist, title)

    url = _spotify_search_instrumental(artist, title, duration_s)
    if not url:
        url = _youtube_search_instrumental(artist, title, duration_s)

    if not url:
        _log_not_found(artist, title, album)
        return None

    # Build destination folder
    artist_safe = sanitize(artist)
    album_safe = sanitize(f"{album} [Instrumental]")
    dest_folder = config.music_root / artist_safe / "Strumentali" / album_safe

    downloaded = _download_instrumental(url, dest_folder)
    if downloaded:
        logger.info("Instrumental downloaded: %s", downloaded)
        return downloaded

    _log_not_found(artist, title, album)
    return None


def _log_not_found(artist: str, title: str, album: str) -> None:
    logger.warning("Instrumental not found: %s – %s (%s)", artist, title, album)
    init_db()
    with db:
        SyncLog.create(
            action="instrumental_not_found",
            detail=f"{artist} – {title} ({album})",
        )
