"""
config.py – Reads, validates, and provides access to config.yaml.
Generates a default config.yaml on first run.
"""

import os
import sys
import yaml
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = _ROOT / "config.yaml"

DEFAULT_CONFIG: dict = {
    "paths": {
        "music_root": "D:/Music/Artisti",
        "playlists_root": "D:/Music/Playlist",
        "temp": "_Temp",
        "inbox": "_Inbox",
        "queue_file": "queue.txt",
    },
    "spotify": {
        "client_id": "",
        "client_secret": "",
    },
    "lastfm": {
        "api_key": "",
        "api_secret": "",
    },
    "genius": {
        "token": "",
    },
    "musicbrainz": {
        "user_agent": "MusicManager/1.0 (your@email.com)",
    },
    "naming": {
        "folder_template": "{artist}/{album} ({year})",
        "file_template": "{track:02d}. {title}",
    },
    "download": {
        "format": "flac",
        "max_parallel": 2,
        "retry_max": 3,
        "retry_delay": 300,
    },
    "foobar": {
        "exe_path": "C:/Program Files/foobar2000/foobar2000.exe",
    },
}

_REQUIRED_KEYS: list[tuple] = [
    ("paths", "music_root"),
    ("paths", "playlists_root"),
    ("paths", "temp"),
    ("paths", "inbox"),
    ("paths", "queue_file"),
    ("naming", "folder_template"),
    ("naming", "file_template"),
    ("download", "format"),
    ("download", "max_parallel"),
    ("download", "retry_max"),
    ("download", "retry_delay"),
]


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _generate_default() -> None:
    """Write DEFAULT_CONFIG to config.yaml with comments."""
    lines = [
        "# MusicManager configuration file",
        "# This file is excluded from version control (see .gitignore).",
        "# Edit the values below to match your environment.",
        "",
    ]
    lines.append(yaml.dump(DEFAULT_CONFIG, default_flow_style=False, allow_unicode=True))
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


def _load_raw() -> dict:
    if not CONFIG_PATH.exists():
        _generate_default()
        print(
            f"[config] Default config.yaml created at {CONFIG_PATH}. "
            "Please edit it before running again.",
            file=sys.stderr,
        )
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError("config.yaml must be a YAML mapping at the top level.")
    return raw


def _validate(cfg: dict) -> None:
    for section, key in _REQUIRED_KEYS:
        section_data = cfg.get(section, {})
        if not isinstance(section_data, dict) or key not in section_data:
            raise KeyError(
                f"config.yaml is missing required key: [{section}] {key}"
            )


class _Config:
    """Singleton config accessor."""

    def __init__(self) -> None:
        raw = _load_raw()
        merged = _deep_merge(DEFAULT_CONFIG, raw)
        _validate(merged)
        self._data: dict = merged

    # ------------------------------------------------------------------ #
    # Generic access
    # ------------------------------------------------------------------ #

    def get(self, *keys, default=None):
        """Access nested config values by key path, e.g. get('paths', 'music_root')."""
        node = self._data
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, None)
            if node is None:
                return default
        return node

    def __getitem__(self, key):
        return self._data[key]

    # ------------------------------------------------------------------ #
    # Convenience properties
    # ------------------------------------------------------------------ #

    @property
    def music_root(self) -> Path:
        return Path(self._data["paths"]["music_root"])

    @property
    def playlists_root(self) -> Path:
        return Path(self._data["paths"]["playlists_root"])

    @property
    def temp_dir(self) -> Path:
        return Path(self._data["paths"]["temp"])

    @property
    def inbox_dir(self) -> Path:
        return Path(self._data["paths"]["inbox"])

    @property
    def queue_file(self) -> Path:
        return Path(self._data["paths"]["queue_file"])

    @property
    def spotify_client_id(self) -> str:
        return self._data["spotify"]["client_id"]

    @property
    def spotify_client_secret(self) -> str:
        return self._data["spotify"]["client_secret"]

    @property
    def lastfm_api_key(self) -> str:
        return self._data["lastfm"]["api_key"]

    @property
    def lastfm_api_secret(self) -> str:
        return self._data["lastfm"]["api_secret"]

    @property
    def genius_token(self) -> str:
        return self._data["genius"]["token"]

    @property
    def musicbrainz_user_agent(self) -> str:
        return self._data["musicbrainz"]["user_agent"]

    @property
    def folder_template(self) -> str:
        return self._data["naming"]["folder_template"]

    @property
    def file_template(self) -> str:
        return self._data["naming"]["file_template"]

    @property
    def download_format(self) -> str:
        return self._data["download"]["format"]

    @property
    def max_parallel(self) -> int:
        return int(self._data["download"]["max_parallel"])

    @property
    def retry_max(self) -> int:
        return int(self._data["download"]["retry_max"])

    @property
    def retry_delay(self) -> int:
        return int(self._data["download"]["retry_delay"])

    @property
    def foobar_exe(self) -> Path:
        return Path(self._data["foobar"]["exe_path"])

    @property
    def data_dir(self) -> Path:
        """Backend/data/ directory, resolved relative to Backend/."""
        return Path(__file__).resolve().parents[1] / "data"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "music.db"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "music.log"

    @property
    def sync_dir(self) -> Path:
        return self.data_dir / "sync"


# Module-level singleton – import and use directly:
#   from modules.config import config
config = _Config()
