"""
foobar.py – Refreshes the foobar2000 media library after downloads.

Uses the foobar2000 CLI interface (/add and /play flags).
Checks whether foobar2000 is already running via psutil before launching.
"""

import logging
import subprocess
from pathlib import Path

from modules.config import config

logger = logging.getLogger(__name__)


def _is_foobar_running() -> bool:
    """Return True if a foobar2000 process is currently running."""
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            if proc.info.get("name", "").lower() == "foobar2000.exe":
                return True
    except Exception as exc:
        logger.debug("psutil process check failed: %s", exc)
    return False


def refresh_library(path: str = None) -> dict:
    """
    Tell foobar2000 to rescan the library.
    If *path* is provided, adds only that path; otherwise rescans the full music root.

    Returns {"success": bool, "message": str}.
    """
    exe = config.foobar_exe
    if not Path(exe).exists():
        msg = f"foobar2000 not found at {exe}"
        logger.warning(msg)
        return {"success": False, "message": msg}

    if not _is_foobar_running():
        msg = "foobar2000 is not running – launch it first"
        logger.warning(msg)
        return {"success": False, "message": msg}

    target = path or str(config.music_root)

    try:
        result = subprocess.run(
            [str(exe), f"/add:{target}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            msg = f"foobar2000 library refreshed: {target}"
            logger.info(msg)
            return {"success": True, "message": msg}
        else:
            msg = f"foobar2000 returned {result.returncode}: {result.stderr.strip()}"
            logger.warning(msg)
            return {"success": False, "message": msg}
    except subprocess.TimeoutExpired:
        msg = "foobar2000 refresh timed out after 30 s"
        logger.warning(msg)
        return {"success": False, "message": msg}
    except Exception as exc:
        msg = f"foobar2000 refresh error: {exc}"
        logger.error(msg)
        return {"success": False, "message": msg}


def play_file(path: str) -> dict:
    """Open and play a specific file in foobar2000."""
    exe = config.foobar_exe
    if not Path(exe).exists():
        return {"success": False, "message": f"foobar2000 not found at {exe}"}
    try:
        subprocess.Popen([str(exe), str(path)])
        return {"success": True, "message": f"Playing: {path}"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}
