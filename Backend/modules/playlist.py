"""
playlist.py – Creates, modifies, and deletes local playlists.

• Copies files with progressive numbering: {NN}. {Artist} - {Title}.ext
• Maintains playlist.json with track info and origin path.
• Syncs tags between Artisti/ copies and Playlist/ copies.
• Renumbers files when order changes.
• Supports create, add_track, remove_track, reorder, delete, list operations.
"""

import datetime
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import mutagen

from modules.config import config
from modules.database import Playlist, PlaylistTrack, Track, db, init_db
from modules.organizer import sanitize

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON manifest helpers
# ---------------------------------------------------------------------------

def _manifest_path(playlist_folder: Path) -> Path:
    return playlist_folder / "playlist.json"


def _load_manifest(playlist_folder: Path) -> dict:
    p = _manifest_path(playlist_folder)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Corrupt playlist.json at %s: %s", p, exc)
    return {"name": playlist_folder.name, "source": None, "cover": "folder.jpg", "tracks": []}


def _save_manifest(playlist_folder: Path, data: dict) -> None:
    playlist_folder.mkdir(parents=True, exist_ok=True)
    _manifest_path(playlist_folder).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# File naming helpers
# ---------------------------------------------------------------------------

def _track_filename(position: int, artist: str, title: str, suffix: str) -> str:
    name = sanitize(f"{position:02d}. {artist} - {title}")
    return name + suffix


def _read_tags_easy(path: Path) -> dict:
    audio = mutagen.File(path, easy=True)
    if not audio:
        return {}
    result = {}
    for field in ("title", "artist", "albumartist", "album"):
        val = audio.get(field, [])
        result[field] = str(val[0]) if val else ""
    return result


# ---------------------------------------------------------------------------
# Playlist folder
# ---------------------------------------------------------------------------

def _playlist_folder(name: str) -> Path:
    return config.playlists_root / sanitize(name)


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def create_playlist(name: str, source: Optional[str] = None) -> dict:
    """Create an empty playlist. Returns the playlist info dict."""
    init_db()
    folder = _playlist_folder(name)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"name": name, "source": source, "cover": "folder.jpg", "tracks": []}
    _save_manifest(folder, manifest)

    with db:
        pl, _ = Playlist.get_or_create(
            name=name,
            defaults={"source": source, "folder_path": str(folder)},
        )
        pl.folder_path = str(folder)
        pl.source = source
        pl.save()

    return {"name": name, "folder": str(folder), "source": source}


def add_track(playlist_name: str, track_path: str, position: Optional[int] = None) -> dict:
    """
    Copy a track file into the playlist folder with correct numbering.
    Returns updated manifest.
    """
    init_db()
    track_path = Path(track_path)
    if not track_path.exists():
        raise FileNotFoundError(f"Track not found: {track_path}")

    tags = _read_tags_easy(track_path)
    artist = tags.get("artist") or tags.get("albumartist") or "Unknown"
    title = tags.get("title") or track_path.stem

    folder = _playlist_folder(playlist_name)
    manifest = _load_manifest(folder)
    tracks = manifest.get("tracks", [])

    # Determine position
    if position is None or position > len(tracks) + 1:
        position = len(tracks) + 1

    # Build new track entry
    new_entry = {
        "position": position,
        "title": title,
        "artist": artist,
        "origin": str(track_path),
        "playlist_path": "",
        "added": datetime.date.today().isoformat(),
    }

    # Insert into list and renumber
    tracks.insert(position - 1, new_entry)
    _renumber(tracks)

    # Copy file
    dest_name = _track_filename(position, artist, title, track_path.suffix.lower())
    dest = folder / dest_name
    shutil.copy2(str(track_path), str(dest))
    tracks[position - 1]["playlist_path"] = str(dest)

    # Rename all subsequent files
    _rename_files(folder, tracks)
    manifest["tracks"] = tracks
    _save_manifest(folder, manifest)
    _sync_db_playlist(playlist_name, manifest, folder)

    return manifest


def remove_track(playlist_name: str, position: int) -> dict:
    """Remove a track at the given position (1-based)."""
    folder = _playlist_folder(playlist_name)
    manifest = _load_manifest(folder)
    tracks = manifest.get("tracks", [])

    idx = position - 1
    if idx < 0 or idx >= len(tracks):
        raise IndexError(f"Position {position} out of range")

    entry = tracks[idx]
    pl_path = Path(entry.get("playlist_path", ""))
    if pl_path.exists():
        pl_path.unlink()

    tracks.pop(idx)
    _renumber(tracks)
    _rename_files(folder, tracks)
    manifest["tracks"] = tracks
    _save_manifest(folder, manifest)
    _sync_db_playlist(playlist_name, manifest, folder)
    return manifest


def reorder_tracks(playlist_name: str, new_order: list[int]) -> dict:
    """
    Reorder tracks by providing a list of current positions in the desired new order.
    Example: [3, 1, 2] moves what was position 3 to position 1, etc.
    """
    folder = _playlist_folder(playlist_name)
    manifest = _load_manifest(folder)
    tracks = manifest.get("tracks", [])

    if sorted(new_order) != list(range(1, len(tracks) + 1)):
        raise ValueError("new_order must be a permutation of 1..N")

    reordered = [tracks[i - 1] for i in new_order]
    _renumber(reordered)
    _rename_files(folder, reordered)
    manifest["tracks"] = reordered
    _save_manifest(folder, manifest)
    _sync_db_playlist(playlist_name, manifest, folder)
    return manifest


def delete_playlist(playlist_name: str, delete_files: bool = False) -> dict:
    """Delete a playlist. Optionally removes playlist folder."""
    init_db()
    folder = _playlist_folder(playlist_name)
    if delete_files and folder.exists():
        shutil.rmtree(str(folder), ignore_errors=True)
    with db:
        Playlist.delete().where(Playlist.name == playlist_name).execute()
    return {"deleted": playlist_name}


def list_playlists() -> list[dict]:
    """Return a list of all playlists with track counts."""
    init_db()
    result = []
    root = config.playlists_root
    if not root.exists():
        return []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        manifest = _load_manifest(folder)
        result.append({
            "name": manifest.get("name", folder.name),
            "source": manifest.get("source"),
            "track_count": len(manifest.get("tracks", [])),
            "folder": str(folder),
        })
    return result


def sync_tags(playlist_name: str) -> int:
    """
    Sync tags from Artisti/ (origin) copies to Playlist/ copies.
    Returns number of files updated.
    """
    folder = _playlist_folder(playlist_name)
    manifest = _load_manifest(folder)
    updated = 0

    for entry in manifest.get("tracks", []):
        origin = Path(entry.get("origin", ""))
        pl_path = Path(entry.get("playlist_path", ""))
        if origin.exists() and pl_path.exists():
            try:
                shutil.copy2(str(origin), str(pl_path))
                updated += 1
            except Exception as exc:
                logger.warning("Tag sync failed for %s: %s", pl_path, exc)

    return updated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _renumber(tracks: list[dict]) -> None:
    for i, t in enumerate(tracks, start=1):
        t["position"] = i


def _rename_files(folder: Path, tracks: list[dict]) -> None:
    """Rename playlist files to match their new positions."""
    for entry in tracks:
        old_path = Path(entry.get("playlist_path", ""))
        if not old_path.exists():
            continue
        pos = entry["position"]
        artist = entry.get("artist", "Unknown")
        title = entry.get("title", "Unknown")
        new_name = _track_filename(pos, artist, title, old_path.suffix.lower())
        new_path = folder / new_name
        if old_path != new_path:
            old_path.rename(new_path)
        entry["playlist_path"] = str(new_path)


def _sync_db_playlist(playlist_name: str, manifest: dict, folder: Path) -> None:
    init_db()
    with db:
        pl, _ = Playlist.get_or_create(
            name=playlist_name,
            defaults={"folder_path": str(folder)},
        )
        pl.folder_path = str(folder)
        pl.source = manifest.get("source")
        pl.date_modified = datetime.datetime.now(datetime.timezone.utc)
        pl.save()

        # Clear and re-insert
        PlaylistTrack.delete().where(PlaylistTrack.playlist == pl).execute()
        for entry in manifest.get("tracks", []):
            db_track = Track.get_or_none(Track.path == entry.get("origin", ""))
            PlaylistTrack.create(
                playlist=pl,
                track=db_track,
                position=entry["position"],
                title=entry.get("title"),
                artist=entry.get("artist"),
                origin_path=entry.get("origin"),
                playlist_path=entry.get("playlist_path"),
            )
