"""
device.py – Exports playlists to a removable SD card device (e.g. TS1802).

• Auto-detects the TS1802 MicroSD (removable drive on Windows).
• Shows available playlists with estimated MP3 size.
• Remembers last playlist selection in the database.
• Converts FLAC → MP3 320 kbps via ffmpeg.
• Only converts/copies new or updated tracks.
• Removes from SD tracks deleted from the playlist.
• Reports: new, already_present, updated, removed.

Target structure: {sd_root}/Playlist/{PlaylistName}/{NN}. {Artist} - {Title}.mp3
"""

import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from modules.config import config
from modules.database import DeviceExport, Playlist, db, init_db
from modules.playlist import _load_manifest, _playlist_folder

logger = logging.getLogger(__name__)

_BITRATE = "320k"
_TARGET_SUBDIR = "Playlist"


# ---------------------------------------------------------------------------
# Device detection (Windows only; stubs for Linux/macOS)
# ---------------------------------------------------------------------------

def detect_device() -> Optional[Path]:
    """
    Return the root path of the first removable drive found (TS1802 or any).
    Returns None if not found or not on Windows.
    """
    if platform.system() != "Windows":
        logger.debug("Device detection is Windows-only.")
        return None
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        removable = []
        for i in range(26):
            if bitmask & (1 << i):
                drive = f"{chr(65 + i)}:\\"
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                if drive_type == 2:  # DRIVE_REMOVABLE
                    removable.append(Path(drive))
        return removable[0] if removable else None
    except Exception as exc:
        logger.warning("Device detection failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Size estimation
# ---------------------------------------------------------------------------

def _flac_to_mp3_size_estimate(flac_path: Path) -> int:
    """Rough MP3 320kbps size estimate from FLAC file duration."""
    try:
        import mutagen
        audio = mutagen.File(str(flac_path))
        if audio and hasattr(audio.info, "length"):
            return int(audio.info.length * 320 * 1000 / 8)
    except Exception:
        pass
    # Fallback: assume 5 MB
    return 5 * 1024 * 1024


def estimate_playlist_size(playlist_name: str) -> int:
    """Return estimated MP3 size in bytes for all tracks in a playlist."""
    folder = _playlist_folder(playlist_name)
    manifest = _load_manifest(folder)
    total = 0
    for entry in manifest.get("tracks", []):
        src = Path(entry.get("playlist_path") or entry.get("origin", ""))
        if src.exists():
            if src.suffix.lower() == ".flac":
                total += _flac_to_mp3_size_estimate(src)
            else:
                total += src.stat().st_size
    return total


def list_playlists_with_size() -> list[dict]:
    """Return all playlists with estimated MP3 sizes."""
    root = config.playlists_root
    if not root.exists():
        return []
    result = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        manifest = _load_manifest(folder)
        name = manifest.get("name", folder.name)
        size_bytes = estimate_playlist_size(name)
        result.append({
            "name": name,
            "track_count": len(manifest.get("tracks", [])),
            "estimated_mp3_size_mb": round(size_bytes / (1024 * 1024), 1),
        })
    return result


# ---------------------------------------------------------------------------
# MD5 helpers
# ---------------------------------------------------------------------------

def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# FLAC → MP3 conversion
# ---------------------------------------------------------------------------

def _convert_to_mp3(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(src),
                "-ab", _BITRATE,
                "-map_metadata", "0",
                "-id3v2_version", "3",
                str(dest),
            ],
            capture_output=True, text=True, timeout=300,
        )
        return result.returncode == 0
    except Exception as exc:
        logger.error("ffmpeg conversion failed (%s → %s): %s", src, dest, exc)
        return False


# ---------------------------------------------------------------------------
# Export logic
# ---------------------------------------------------------------------------

def export_playlist(
    playlist_name: str,
    device_root: Path,
    report: Optional[dict] = None,
) -> dict:
    """
    Export one playlist to the device.
    Returns a report dict with keys: new, already_present, updated, removed, errors.
    """
    if report is None:
        report = {"new": [], "already_present": [], "updated": [], "removed": [], "errors": []}

    init_db()
    folder = _playlist_folder(playlist_name)
    manifest = _load_manifest(folder)
    device_pl_dir = device_root / _TARGET_SUBDIR / playlist_name
    device_pl_dir.mkdir(parents=True, exist_ok=True)

    expected_files: set[str] = set()

    for entry in manifest.get("tracks", []):
        src = Path(entry.get("playlist_path") or entry.get("origin", ""))
        if not src.exists():
            report["errors"].append(f"Source not found: {src}")
            continue

        pos = entry.get("position", 0)
        artist = entry.get("artist", "Unknown")
        title = entry.get("title", "Unknown")
        dest_name = f"{pos:02d}. {artist} - {title}.mp3"
        dest = device_pl_dir / dest_name
        expected_files.add(dest_name)

        src_md5 = _md5(src)

        # Check existing export record
        with db:
            record = DeviceExport.get_or_none(
                (DeviceExport.playlist_name == playlist_name) &
                (DeviceExport.track_path == str(src))
            )

        if dest.exists() and record and record.mp3_hash == src_md5:
            report["already_present"].append(dest_name)
            continue

        # Convert (or copy if already MP3)
        if src.suffix.lower() == ".mp3":
            shutil.copy2(str(src), str(dest))
            ok = True
        else:
            ok = _convert_to_mp3(src, dest)

        if ok:
            new_hash = _md5(dest)
            with db:
                DeviceExport.delete().where(
                    (DeviceExport.playlist_name == playlist_name) &
                    (DeviceExport.track_path == str(src))
                ).execute()
                DeviceExport.create(
                    playlist_name=playlist_name,
                    track_path=str(src),
                    mp3_hash=src_md5,
                )
            if record:
                report["updated"].append(dest_name)
            else:
                report["new"].append(dest_name)
        else:
            report["errors"].append(f"Conversion failed: {src.name}")

    # Remove stale files from device
    for existing in list(device_pl_dir.iterdir()):
        if existing.is_file() and existing.name not in expected_files:
            existing.unlink()
            report["removed"].append(existing.name)
            logger.info("Removed stale file from device: %s", existing.name)

    return report


def export_playlists(playlist_names: list[str], device_root: Optional[Path] = None) -> dict:
    """Export multiple playlists to the device. Auto-detects device if not specified."""
    if device_root is None:
        device_root = detect_device()
    if device_root is None:
        raise RuntimeError("No removable device detected.")

    overall = {"device": str(device_root), "playlists": {}}
    for name in playlist_names:
        logger.info("Exporting playlist '%s' to %s", name, device_root)
        report = export_playlist(name, device_root)
        overall["playlists"][name] = report
    return overall
