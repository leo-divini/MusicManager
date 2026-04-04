"""
inbox_watcher.py – Monitors the _Inbox/ folder with watchdog.

• Detects files dropped into a subfolder of _Inbox/.
• Debounces 3 seconds after the last file event.
• Uses the subfolder name as the playlist destination name.
• Calls playlist.py to process the files.
• Clears the subfolder after successful processing.
"""

import logging
import os
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

from modules.config import config
from modules.playlist import add_track, create_playlist, list_playlists

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 3


# ---------------------------------------------------------------------------
# Debounce helper
# ---------------------------------------------------------------------------

class _DebounceTimer:
    """Fires a callback after *delay* seconds of inactivity."""

    def __init__(self, delay: float, callback):
        self._delay = delay
        self._callback = callback
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def reset(self, *args, **kwargs):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._callback, args=args, kwargs=kwargs)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None


# ---------------------------------------------------------------------------
# File event handler
# ---------------------------------------------------------------------------

class _InboxHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        # Map: subfolder_name → DebounceTimer
        self._timers: dict[str, _DebounceTimer] = {}
        self._lock = threading.Lock()

    def _get_playlist_name(self, path: str) -> str | None:
        """
        Return the immediate subdirectory name under _Inbox/, or None if the
        file is directly in _Inbox/ (not a subfolder).
        """
        inbox = config.inbox_dir.resolve()
        try:
            rel = Path(path).resolve().relative_to(inbox)
        except ValueError:
            return None
        parts = rel.parts
        if len(parts) < 2:
            return None
        return parts[0]

    def _on_file_event(self, path: str):
        playlist_name = self._get_playlist_name(path)
        if not playlist_name:
            return
        with self._lock:
            if playlist_name not in self._timers:
                self._timers[playlist_name] = _DebounceTimer(
                    _DEBOUNCE_SECONDS, self._process_subfolder
                )
        self._timers[playlist_name].reset(playlist_name)

    def on_created(self, event):
        if not event.is_directory:
            self._on_file_event(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._on_file_event(event.dest_path)

    def _process_subfolder(self, playlist_name: str):
        inbox = config.inbox_dir
        subfolder = inbox / playlist_name
        if not subfolder.exists():
            return

        audio_exts = {".flac", ".mp3", ".ogg", ".opus", ".m4a", ".wav", ".aac"}
        files = sorted(
            p for p in subfolder.iterdir()
            if p.is_file() and p.suffix.lower() in audio_exts
        )

        if not files:
            logger.info("_Inbox/%s: no audio files found", playlist_name)
            return

        logger.info("Processing %d file(s) from _Inbox/%s → playlist '%s'",
                    len(files), playlist_name, playlist_name)

        # Ensure playlist exists
        existing = {pl["name"] for pl in list_playlists()}
        if playlist_name not in existing:
            create_playlist(playlist_name)

        errors = 0
        for f in files:
            try:
                add_track(playlist_name, str(f))
                logger.debug("Added to playlist '%s': %s", playlist_name, f.name)
            except Exception as exc:
                logger.error("Failed to add %s to playlist: %s", f, exc)
                errors += 1

        # Clear subfolder (even if some files errored)
        for f in files:
            try:
                if f.exists():
                    f.unlink()
            except Exception as exc:
                logger.warning("Could not delete %s from inbox: %s", f, exc)

        logger.info("_Inbox/%s processed (%d files, %d errors)", playlist_name, len(files), errors)

        # Clean up timer
        with self._lock:
            self._timers.pop(playlist_name, None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_watcher() -> Observer:
    """
    Start the inbox folder watcher. Returns the Observer (still running).
    Call observer.stop() / observer.join() to shut down.
    """
    inbox = config.inbox_dir
    inbox.mkdir(parents=True, exist_ok=True)

    handler = _InboxHandler()
    observer = Observer()
    observer.schedule(handler, str(inbox), recursive=True)
    observer.start()
    logger.info("Inbox watcher started: %s", inbox)
    return observer


def run_forever():
    """Start the watcher and block until interrupted."""
    observer = start_watcher()
    try:
        while observer.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        logger.info("Inbox watcher stopped.")
