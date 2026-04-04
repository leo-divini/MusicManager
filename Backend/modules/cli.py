"""
cli.py – Argument parsing and command dispatch for MusicManager.

All commands output JSON to stdout for GUI consumption.
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# JSON output helper
# ---------------------------------------------------------------------------

def _out(data: Any) -> None:
    """Print *data* as JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _error(message: str, code: int = 1) -> None:
    _out({"error": message, "code": code})
    sys.exit(code)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_download(args) -> None:
    from modules.downloader import download_now
    query = args.download
    result = download_now(query)
    _out(result)


def cmd_queue(args) -> None:
    from modules.queue_watcher import process_queue_file
    results = process_queue_file()
    _out({"processed": len(results), "results": results})


def cmd_sync(args) -> None:
    from modules.sync import sync_all, sync_playlist
    playlist_name = getattr(args, "sync_name", None)
    if playlist_name:
        result = sync_playlist(playlist_name)
        _out(result)
    else:
        results = sync_all()
        _out({"synced": len(results), "results": results})


def cmd_check(args) -> None:
    """Integrity check: verify every track in DB still exists and hash matches."""
    from modules.database import Track, db, init_db
    init_db()
    issues = []
    with db:
        tracks = list(Track.select())
    for track in tracks:
        path = Path(track.path)
        if not path.exists():
            issues.append({"path": track.path, "issue": "file_missing"})
            continue
        if track.hash_md5:
            h = hashlib.md5()
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            if h.hexdigest() != track.hash_md5:
                issues.append({"path": track.path, "issue": "hash_mismatch"})
    _out({"total_tracks": len(tracks), "issues": len(issues), "details": issues})


def cmd_fix(args) -> None:
    """Auto-repair: remove DB entries for missing files, re-tag files with hash mismatches."""
    from modules.database import Track, db, init_db
    from modules.tagger import tag_file
    init_db()
    removed = []
    retagged = []
    with db:
        tracks = list(Track.select())
    for track in tracks:
        path = Path(track.path)
        if not path.exists():
            with db:
                Track.delete().where(Track.id == track.id).execute()
            removed.append(track.path)
        else:
            try:
                tag_file(path)
                retagged.append(track.path)
            except Exception as exc:
                pass
    _out({"removed_db_entries": len(removed), "retagged": len(retagged)})


def cmd_stats(args) -> None:
    from modules.database import Track, Album, Artist, Playlist, db, init_db
    init_db()
    with db:
        stats = {
            "tracks": Track.select().count(),
            "albums": Album.select().count(),
            "artists": Artist.select().count(),
            "playlists": Playlist.select().count(),
        }
        # Format breakdown
        fmt_counts = {}
        for track in Track.select(Track.format).distinct():
            fmt = track.format or "unknown"
            fmt_counts[fmt] = Track.select().where(Track.format == fmt).count()
        stats["formats"] = fmt_counts

        # Total duration
        total_dur = sum(
            t.duration or 0
            for t in Track.select(Track.duration)
        )
        stats["total_duration_hours"] = round(total_dur / 3600, 2)
    _out(stats)


def cmd_search(args) -> None:
    from modules.database import Track, db, init_db
    init_db()
    query = args.search
    pattern = f"%{query}%"
    with db:
        results = list(
            Track.select()
            .where(
                Track.title.contains(query) |
                Track.artist.contains(query) |
                Track.album.contains(query)
            )
            .limit(50)
        )
    _out([{
        "id": t.id,
        "path": t.path,
        "title": t.title,
        "artist": t.artist,
        "album": t.album,
        "year": t.year,
    } for t in results])


def cmd_export_device(args) -> None:
    from modules.device import export_playlists, detect_device
    playlists_arg = getattr(args, "playlists", None)
    if playlists_arg:
        playlist_names = [p.strip() for p in playlists_arg.split(",")]
    else:
        from modules.playlist import list_playlists
        playlist_names = [p["name"] for p in list_playlists()]

    device_root = detect_device()
    if device_root is None:
        _error("No removable device detected.")
    result = export_playlists(playlist_names, device_root)
    _out(result)


def cmd_retag(args) -> None:
    from modules.tagger import tag_file
    path = Path(args.retag)
    if not path.exists():
        _error(f"File not found: {path}")
    result = tag_file(path)
    _out(result)


def cmd_playlist_list(args) -> None:
    from modules.playlist import list_playlists
    _out(list_playlists())


def cmd_playlist_add(args) -> None:
    """Interactive: reads playlist_name and track_path from args or prompts."""
    from modules.playlist import add_track, create_playlist, list_playlists
    playlist_name = getattr(args, "playlist_name", None)
    track_path = getattr(args, "track_path", None)
    if not playlist_name or not track_path:
        _error("--playlist-add requires --playlist-name and --track-path")
    existing = {p["name"] for p in list_playlists()}
    if playlist_name not in existing:
        create_playlist(playlist_name)
    result = add_track(playlist_name, track_path, getattr(args, "position", None))
    _out({"playlist": playlist_name, "tracks": len(result.get("tracks", []))})


def cmd_playlist_remove(args) -> None:
    from modules.playlist import remove_track
    playlist_name = getattr(args, "playlist_name", None)
    position = getattr(args, "position", None)
    if not playlist_name or position is None:
        _error("--playlist-remove requires --playlist-name and --position")
    result = remove_track(playlist_name, int(position))
    _out({"playlist": playlist_name, "tracks": len(result.get("tracks", []))})


def cmd_playlist_reorder(args) -> None:
    from modules.playlist import reorder_tracks
    playlist_name = getattr(args, "playlist_name", None)
    order_str = getattr(args, "new_order", None)
    if not playlist_name or not order_str:
        _error("--playlist-reorder requires --playlist-name and --new-order")
    new_order = [int(x.strip()) for x in order_str.split(",")]
    result = reorder_tracks(playlist_name, new_order)
    _out({"playlist": playlist_name, "tracks": len(result.get("tracks", []))})


def cmd_status(args) -> None:
    """Return current queue status for polling."""
    from modules.database import QueueItem, db, init_db
    init_db()
    with db:
        items = list(QueueItem.select().order_by(QueueItem.date_added.desc()).limit(50))
    _out([{
        "id": i.id,
        "url": i.url,
        "name": i.name,
        "type": i.type,
        "status": i.status,
        "progress": i.progress,
        "retries": i.retries,
        "date_added": i.date_added.isoformat() if i.date_added else None,
    } for i in items])


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="MusicManager CLI – outputs JSON to stdout",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--download", metavar="URL_OR_NAME",
                       help="Download a track, album, artist, or playlist")
    group.add_argument("--queue", action="store_true",
                       help="Process queue.txt")
    group.add_argument("--sync", nargs="?", const="__all__", metavar="PLAYLIST_NAME",
                       help="Sync all or a named Spotify playlist")
    group.add_argument("--check", action="store_true",
                       help="Integrity check")
    group.add_argument("--fix", action="store_true",
                       help="Auto-repair issues found by --check")
    group.add_argument("--stats", action="store_true",
                       help="Print library statistics")
    group.add_argument("--search", metavar="QUERY",
                       help="Search local library")
    group.add_argument("--export-device", action="store_true",
                       help="Export playlists to removable device")
    group.add_argument("--retag", metavar="PATH",
                       help="Re-tag a specific file")
    group.add_argument("--playlist-list", action="store_true",
                       help="List all playlists")
    group.add_argument("--playlist-add", action="store_true",
                       help="Add a track to a playlist (needs --playlist-name --track-path)")
    group.add_argument("--playlist-remove", action="store_true",
                       help="Remove a track from a playlist (needs --playlist-name --position)")
    group.add_argument("--playlist-reorder", action="store_true",
                       help="Reorder playlist tracks (needs --playlist-name --new-order)")
    group.add_argument("--status", action="store_true",
                       help="Return current queue/download status as JSON")

    # Optional modifiers
    parser.add_argument("--playlists", metavar="NAME1,NAME2",
                        help="Comma-separated playlist names (for --export-device)")
    parser.add_argument("--playlist-name", metavar="NAME",
                        help="Playlist name (for --playlist-add/remove/reorder)")
    parser.add_argument("--track-path", metavar="PATH",
                        help="Audio file path (for --playlist-add)")
    parser.add_argument("--position", type=int, metavar="N",
                        help="Track position (for --playlist-add/remove)")
    parser.add_argument("--new-order", metavar="1,3,2",
                        help="Comma-separated new position order (for --playlist-reorder)")

    return parser


def run(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.download:
        cmd_download(args)
    elif args.queue:
        cmd_queue(args)
    elif args.sync is not None:
        if args.sync == "__all__":
            args.sync_name = None
        else:
            args.sync_name = args.sync
        cmd_sync(args)
    elif args.check:
        cmd_check(args)
    elif args.fix:
        cmd_fix(args)
    elif args.stats:
        cmd_stats(args)
    elif args.search:
        cmd_search(args)
    elif args.export_device:
        cmd_export_device(args)
    elif args.retag:
        cmd_retag(args)
    elif args.playlist_list:
        cmd_playlist_list(args)
    elif args.playlist_add:
        cmd_playlist_add(args)
    elif args.playlist_remove:
        cmd_playlist_remove(args)
    elif args.playlist_reorder:
        cmd_playlist_reorder(args)
    elif args.status:
        cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)
