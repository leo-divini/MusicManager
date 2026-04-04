"""
organizer.py – Moves downloaded files into the canonical library structure.

• Creates {music_root}/{artist}/{album} ({year})/ folders.
• Renames files using naming templates from config.
• Sanitizes filenames for Windows (removes <>:"/\\|?*).
• Max filename length: 180 characters.
• Handles duplicates by MD5 hash.
• Moves files from _Temp to final destination.
"""

import hashlib
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from modules.config import config
from modules.database import Track, db, init_db

logger = logging.getLogger(__name__)

_WINDOWS_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_NAME_LEN = 180


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def sanitize(name: str) -> str:
    """Remove characters illegal in Windows filenames and trim length."""
    name = _WINDOWS_ILLEGAL.sub("_", name).strip(". ")
    if len(name) > _MAX_NAME_LEN:
        name = name[:_MAX_NAME_LEN]
    return name or "Unknown"


def _render_template(template: str, tags: dict) -> str:
    try:
        track_num = int(tags.get("tracknumber", "0").split("/")[0]) if tags.get("tracknumber") else 0
        return template.format(
            artist=tags.get("artist") or "Unknown Artist",
            albumartist=tags.get("albumartist") or tags.get("artist") or "Unknown Artist",
            album=tags.get("album") or "Unknown Album",
            title=tags.get("title") or "Unknown Title",
            year=tags.get("date", "")[:4] or "0000",
            track=track_num,
            disc=tags.get("discnumber", "1").split("/")[0] if tags.get("discnumber") else "1",
            genre=tags.get("genre") or "Unknown",
        )
    except (KeyError, ValueError, IndexError) as exc:
        logger.warning("Template render failed (%s): %s", template, exc)
        return "Unknown"


# ---------------------------------------------------------------------------
# Tag reading (easy interface)
# ---------------------------------------------------------------------------

def _read_easy_tags(path: Path) -> dict:
    audio = mutagen.File(path, easy=True)
    if audio is None:
        return {}
    result = {}
    for field in ("title", "artist", "albumartist", "album", "date", "genre",
                  "tracknumber", "discnumber"):
        val = audio.get(field, [])
        result[field] = str(val[0]) if val else ""
    return result


def _get_duration(path: Path) -> Optional[float]:
    try:
        audio = mutagen.File(path)
        if audio and hasattr(audio.info, "length"):
            return audio.info.length
    except Exception:
        pass
    return None


def _get_bitrate(path: Path) -> Optional[int]:
    try:
        audio = mutagen.File(path)
        if audio and hasattr(audio.info, "bitrate"):
            return audio.info.bitrate // 1000
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# MD5 hash
# ---------------------------------------------------------------------------

def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _find_duplicate(md5: str) -> Optional[Path]:
    """Return the path of an existing track with the same MD5, or None."""
    init_db()
    with db:
        existing = Track.get_or_none(Track.hash_md5 == md5)
    if existing and Path(existing.path).exists():
        return Path(existing.path)
    return None


def _ensure_artist_subfolders(artist_folder: Path) -> None:
    """Create Immagini/ and Strumentali/ subfolders the first time an artist folder is made."""
    for subfolder in ("Immagini", "Strumentali"):
        sub = artist_folder / subfolder
        if not sub.exists():
            sub.mkdir(parents=True, exist_ok=True)
            logger.debug("Created artist subfolder: %s", sub)


# ---------------------------------------------------------------------------
# Main organize function
# ---------------------------------------------------------------------------

def organize_file(src: Path) -> Optional[Path]:
    """
    Move *src* from _Temp into the configured library structure.
    Returns the final destination path, or None on failure.
    """
    src = Path(src)
    if not src.exists():
        logger.error("Source file not found: %s", src)
        return None

    # Compute MD5 and check for duplicates
    md5 = md5_file(src)
    duplicate = _find_duplicate(md5)
    if duplicate:
        logger.info("Duplicate detected (MD5 %s), skipping: %s", md5, src)
        try:
            src.unlink()
        except Exception:
            pass
        return duplicate

    # Read tags
    tags = _read_easy_tags(src)
    artist = sanitize(tags.get("albumartist") or tags.get("artist") or "Unknown Artist")
    album_raw = tags.get("album") or "Unknown Album"
    year = (tags.get("date") or "")[:4]
    album = sanitize(f"{album_raw} ({year})" if year else album_raw)

    # Folder path
    folder_rel = _render_template(config.folder_template, tags)
    dest_folder = config.music_root / sanitize(folder_rel.split("/")[0]) / sanitize(
        "/".join(folder_rel.split("/")[1:]) if "/" in folder_rel else folder_rel
    )
    # Simpler: just build from artist / album directly
    dest_folder = config.music_root / artist / album
    artist_folder = config.music_root / artist
    _ensure_artist_subfolders(artist_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)

    # File name
    file_stem = sanitize(_render_template(config.file_template, tags))
    dest_name = file_stem + src.suffix.lower()
    dest = dest_folder / dest_name

    # Avoid overwriting a *different* file (same name, different content)
    counter = 1
    while dest.exists():
        existing_md5 = md5_file(dest)
        if existing_md5 == md5:
            logger.info("Identical file already exists at %s", dest)
            try:
                src.unlink()
            except Exception:
                pass
            return dest
        dest = dest_folder / f"{file_stem} ({counter}){src.suffix.lower()}"
        counter += 1

    # Move
    shutil.move(str(src), str(dest))
    logger.info("Organized: %s → %s", src.name, dest)

    # Update database
    init_db()
    with db:
        track, created = Track.get_or_create(
            path=str(dest),
            defaults={
                "hash_md5": md5,
                "artist": tags.get("artist") or tags.get("albumartist") or "",
                "album": tags.get("album") or "",
                "title": tags.get("title") or "",
                "year": int(year) if year.isdigit() else None,
                "genre": tags.get("genre") or "",
                "format": dest.suffix.lstrip(".").lower(),
                "bitrate": _get_bitrate(dest),
                "duration": _get_duration(dest),
                "track_number": _parse_track_num(tags.get("tracknumber", "")),
            },
        )
        if not created:
            track.hash_md5 = md5
            track.date_modified = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            track.save()

    return dest


def _parse_track_num(val: str) -> Optional[int]:
    if not val:
        return None
    try:
        return int(str(val).split("/")[0])
    except (ValueError, IndexError):
        return None
