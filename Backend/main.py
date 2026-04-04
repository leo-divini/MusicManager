"""
main.py – Entry point for MusicManager.

Initialises the database and config, then delegates to cli.run().
All output is JSON to stdout.
"""

import logging
import sys
from pathlib import Path

# Ensure Backend/ is on the Python path so that `from modules.x import y` works
_backend_dir = Path(__file__).resolve().parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))


def _setup_logging() -> None:
    from modules.config import config
    log_path = config.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(str(log_path), encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main() -> None:
    _setup_logging()
    logger = logging.getLogger("main")

    try:
        from modules.database import init_db
        init_db()
    except Exception as exc:
        import json
        print(json.dumps({"error": f"Database init failed: {exc}"}))
        sys.exit(1)

    try:
        from modules.cli import run
        run()
    except SystemExit:
        raise
    except Exception as exc:
        import json
        logger.exception("Unhandled exception")
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
