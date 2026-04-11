"""
setup_config.py – Interactive configuration wizard for MusicManager.

Reads the existing config.yaml (if present), prompts for every setting
(showing the current value as the default), and writes the result back.

This script is called automatically by setup.bat on first run, and
is also available through the "Edit settings" menu option.
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[ERROR] pyyaml is not installed. Run setup.bat to install dependencies first.")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"

# ── Default values (mirrors config.py DEFAULT_CONFIG) ────────────────────────

DEFAULTS: dict = {
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

# Each entry: (section, key, label, hint)
PROMPTS: list[tuple] = [
    ("paths",        "music_root",       "Music library root path",      "e.g. D:/Music/Artisti"),
    ("paths",        "playlists_root",   "Playlists root path",          "e.g. D:/Music/Playlist"),
    ("paths",        "temp",             "Temp download folder",         "relative or absolute path"),
    ("paths",        "inbox",            "Inbox folder",                 "drop files here for auto-import"),
    ("paths",        "queue_file",       "Queue file path",              "plain-text download queue"),
    ("spotify",      "client_id",        "Spotify Client ID",            "https://developer.spotify.com/dashboard"),
    ("spotify",      "client_secret",    "Spotify Client Secret",        ""),
    ("lastfm",       "api_key",          "Last.fm API Key",              "https://www.last.fm/api/account/create"),
    ("lastfm",       "api_secret",       "Last.fm API Secret",           ""),
    ("genius",       "token",            "Genius API Token",             "https://genius.com/api-clients"),
    ("musicbrainz",  "user_agent",       "MusicBrainz User-Agent",       "AppName/1.0 (your@email.com)"),
    ("naming",       "folder_template",  "Folder naming template",       "{artist}/{album} ({year})"),
    ("naming",       "file_template",    "File naming template",         "{track:02d}. {title}"),
    ("download",     "format",           "Audio format",                 "flac | mp3 | ogg | opus | m4a"),
    ("download",     "max_parallel",     "Max parallel downloads",       "1–4 recommended"),
    ("download",     "retry_max",        "Retry attempts on failure",    ""),
    ("download",     "retry_delay",      "Retry delay in seconds",       ""),
    ("foobar",       "exe_path",         "foobar2000 executable path",   "leave blank if not used"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_existing() -> dict:
    """Return the contents of config.yaml, or {} if it doesn't exist."""
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict):
            return data
    return {}


def _ask(label: str, hint: str, current) -> str:
    """Print a prompt line and return the user's input (or current if blank)."""
    display = str(current) if str(current) else ""
    suffix = f"  [{display}]" if display else ""
    if hint:
        print(f"  # {hint}")
    raw = input(f"  {label}{suffix}: ").strip()
    return raw if raw else str(current)


# ── Main wizard ───────────────────────────────────────────────────────────────

def main() -> None:
    existing = _load_existing()
    cfg = _deep_merge(DEFAULTS, existing)

    action = "Editing" if CONFIG_PATH.exists() else "Creating"
    print("=" * 62)
    print(f"  MusicManager – Configuration Wizard  ({action} config.yaml)")
    print("  Press ENTER to keep the value shown in [brackets].")
    print("=" * 62)

    current_section: str | None = None
    for section, key, label, hint in PROMPTS:
        if section != current_section:
            current_section = section
            print(f"\n  ── {section.upper()} " + "─" * (46 - len(section)))

        current_val = cfg.get(section, {}).get(key, DEFAULTS.get(section, {}).get(key, ""))
        new_val: str | int = _ask(label, hint, current_val)

        # Preserve integer type for numeric settings
        default_val = DEFAULTS.get(section, {}).get(key)
        if isinstance(default_val, int):
            try:
                new_val = int(new_val)
            except ValueError:
                print(f"  [WARN] Expected a number – keeping previous value ({current_val})")
                new_val = current_val

        cfg[section][key] = new_val

    # Write config.yaml with a header comment
    header = (
        "# MusicManager configuration file\n"
        "# This file is excluded from version control (see .gitignore).\n"
        "# Edit the values below to match your environment.\n\n"
    )
    CONFIG_PATH.write_text(
        header + yaml.dump(cfg, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"\n  [OK] Configuration saved to {CONFIG_PATH}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  [CANCELLED] No changes were saved.\n")
        sys.exit(1)
