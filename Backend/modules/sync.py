"""
sync.py – Syncs local playlists against their Spotify source playlists.

• Reads .spotdl files from data/sync/.
• Queries Spotify for the current playlist state.
• Downloads new tracks, removes deleted ones.
• Renumbers files if order changed.
• Updates playlist.json.
• Can be triggered: python main.py --sync or --sync "PlaylistName"
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from modules.config import config
from modules.database import SyncLog, db, init_db
from modules.downloader import download_now
from modules.organizer import sanitize
from modules.playlist import (
    _load_manifest, _playlist_folder, _save_manifest,
    _renumber, _rename_files, _sync_db_playlist,
    create_playlist,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spotify client
# ---------------------------------------------------------------------------

def _get_spotify() -> Optional[spotipy.Spotify]:
    if not config.spotify_client_id or not config.spotify_client_secret:
        logger.warning("Spotify credentials not configured.")
        return None
    try:
        auth = SpotifyClientCredentials(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
        )
        return spotipy.Spotify(auth_manager=auth)
    except Exception as exc:
        logger.error("Spotify client init failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# .spotdl file helpers
# ---------------------------------------------------------------------------

def _load_spotdl_files() -> list[dict]:
    """Return list of dicts with {name, source, path} for each .spotdl in sync/."""
    sync_dir = config.sync_dir
    sync_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for f in sync_dir.glob("*.spotdl"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "name": f.stem,
                "source": data.get("query") or data.get("url") or "",
                "path": f,
                "data": data,
            })
        except Exception as exc:
            logger.warning("Could not parse %s: %s", f, exc)
    return result


def _save_spotdl_file(playlist_name: str, source: str, tracks: list[dict]) -> Path:
    sync_dir = config.sync_dir
    sync_dir.mkdir(parents=True, exist_ok=True)
    path = sync_dir / f"{sanitize(playlist_name)}.spotdl"
    data = {
        "query": source,
        "tracks": tracks,
        "saved_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Spotify playlist fetching
# ---------------------------------------------------------------------------

def _fetch_spotify_tracks(sp: spotipy.Spotify, playlist_id: str) -> list[dict]:
    """Return ordered list of track dicts: {position, title, artist, spotify_id, duration_ms}."""
    tracks = []
    results = sp.playlist_tracks(playlist_id, fields="items,next,total")
    position = 1
    while results:
        for item in results.get("items", []):
            track = item.get("track")
            if not track:
                continue
            tracks.append({
                "position": position,
                "title": track.get("name", ""),
                "artist": ", ".join(a["name"] for a in track.get("artists", [])),
                "spotify_id": track.get("id", ""),
                "duration_ms": track.get("duration_ms", 0),
                "spotify_url": track.get("external_urls", {}).get("spotify", ""),
            })
            position += 1
        next_url = results.get("next")
        if next_url:
            results = sp.next(results)
        else:
            break
    return tracks


def _extract_playlist_id(source: str) -> Optional[str]:
    """Extract Spotify playlist ID from a URI, URL, or raw ID."""
    if "spotify:playlist:" in source:
        return source.split("spotify:playlist:")[-1].split("?")[0]
    if "open.spotify.com/playlist/" in source:
        return source.split("open.spotify.com/playlist/")[-1].split("?")[0]
    return source if len(source) == 22 else None


# ---------------------------------------------------------------------------
# Sync one playlist
# ---------------------------------------------------------------------------

def sync_playlist(playlist_name: str, source: Optional[str] = None) -> dict:
    """
    Sync a local playlist against its Spotify source.
    Returns a dict: {added, removed, reordered, errors}.
    """
    init_db()
    sp = _get_spotify()
    if sp is None:
        return {"error": "Spotify not configured", "added": [], "removed": [], "reordered": [], "errors": []}

    folder = _playlist_folder(playlist_name)
    manifest = _load_manifest(folder)
    source = source or manifest.get("source", "")
    if not source:
        return {"error": f"No Spotify source for '{playlist_name}'", "added": [], "removed": [], "reordered": [], "errors": []}

    playlist_id = _extract_playlist_id(source)
    if not playlist_id:
        return {"error": f"Cannot parse playlist ID from: {source}", "added": [], "removed": [], "reordered": [], "errors": []}

    try:
        remote_tracks = _fetch_spotify_tracks(sp, playlist_id)
    except Exception as exc:
        logger.error("Spotify fetch failed: %s", exc)
        return {"error": str(exc), "added": [], "removed": [], "reordered": [], "errors": [str(exc)]}

    local_tracks = manifest.get("tracks", [])
    local_by_spotify_id = {
        t.get("spotify_id", ""): t
        for t in local_tracks
        if t.get("spotify_id")
    }
    local_ids_ordered = [t.get("spotify_id") for t in local_tracks]
    remote_ids_ordered = [t["spotify_id"] for t in remote_tracks]

    report = {"added": [], "removed": [], "reordered": [], "errors": [], "playlist": playlist_name}

    # Download new tracks
    new_tracks = [t for t in remote_tracks if t["spotify_id"] not in local_by_spotify_id]
    for track_info in new_tracks:
        url = track_info["spotify_url"]
        if not url:
            continue
        logger.info("Downloading new track: %s – %s", track_info["artist"], track_info["title"])
        result = download_now(url, "track")
        if result.get("success"):
            report["added"].append(f"{track_info['artist']} – {track_info['title']}")
            _log_sync(playlist_name, "added", f"{track_info['artist']} – {track_info['title']}")
        else:
            report["errors"].append(f"Download failed: {track_info['title']}")
        time.sleep(1)

    # Remove deleted tracks
    removed_ids = set(local_by_spotify_id.keys()) - {t["spotify_id"] for t in remote_tracks}
    for sid in removed_ids:
        entry = local_by_spotify_id[sid]
        pl_path = Path(entry.get("playlist_path", ""))
        if pl_path.exists():
            pl_path.unlink()
        local_tracks = [t for t in local_tracks if t.get("spotify_id") != sid]
        report["removed"].append(entry.get("title", sid))
        _log_sync(playlist_name, "removed", entry.get("title", sid))

    # Rebuild manifest tracks in remote order
    id_to_local: dict[str, dict] = {
        t.get("spotify_id", ""): t for t in local_tracks
    }
    new_local_tracks = []
    for rt in remote_tracks:
        sid = rt["spotify_id"]
        if sid in id_to_local:
            entry = dict(id_to_local[sid])
            entry["position"] = rt["position"]
            entry["title"] = rt["title"]
            entry["artist"] = rt["artist"]
            new_local_tracks.append(entry)

    _renumber(new_local_tracks)
    # Detect reordering
    new_ids = [t.get("spotify_id") for t in new_local_tracks]
    old_local_ids = [t.get("spotify_id") for t in local_tracks if t.get("spotify_id") in {t["spotify_id"] for t in remote_tracks}]
    if new_ids != old_local_ids:
        report["reordered"] = [f"Reordered {len(new_local_tracks)} tracks"]
        _rename_files(folder, new_local_tracks)
        _log_sync(playlist_name, "reordered", f"{len(new_local_tracks)} tracks")

    manifest["tracks"] = new_local_tracks
    manifest["source"] = source
    _save_manifest(folder, manifest)
    _sync_db_playlist(playlist_name, manifest, folder)
    _save_spotdl_file(playlist_name, source, new_local_tracks)

    return report


def _log_sync(playlist_name: str, action: str, detail: str) -> None:
    init_db()
    with db:
        SyncLog.create(playlist_name=playlist_name, action=action, detail=detail)


# ---------------------------------------------------------------------------
# Sync all or one
# ---------------------------------------------------------------------------

def sync_all() -> list[dict]:
    """Sync all playlists that have a Spotify source."""
    init_db()
    spotdl_files = _load_spotdl_files()
    if not spotdl_files:
        # Fall back to scanning playlist manifests
        root = config.playlists_root
        if not root.exists():
            return []
        spotdl_files = []
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            manifest = _load_manifest(folder)
            source = manifest.get("source")
            if source:
                spotdl_files.append({
                    "name": manifest.get("name", folder.name),
                    "source": source,
                })

    results = []
    for entry in spotdl_files:
        name = entry["name"]
        source = entry["source"]
        logger.info("Syncing playlist: %s", name)
        result = sync_playlist(name, source)
        results.append(result)
    return results
