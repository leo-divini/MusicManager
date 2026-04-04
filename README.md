# MusicManager

A comprehensive local music library manager with Spotify integration, automatic tagging, organized folder structures, and device export capabilities.

## Features

- **Download**: Download tracks, albums, artists, and playlists via spotDL (Spotify URLs or plain names)
- **Tagging**: Auto-complete tags via MusicBrainz, Last.fm genres, Genius lyrics, and ReplayGain
- **Organization**: Structured `Artisti/{Artist}/{Album}/` folder layout with configurable naming templates
- **Playlists**: Create/manage local playlists with numbered file copies and `playlist.json` manifests
- **Sync**: Keep local playlists in sync with Spotify source playlists via `.spotdl` files
- **Instrumentals**: Search and download instrumental versions organized separately
- **Device Export**: Convert FLAC → MP3 320 kbps and sync to external storage (e.g. TS1802 MicroSD)
- **Inbox Watcher**: Drop files into `_Inbox/{PlaylistName}/` for automatic playlist processing
- **Queue**: Process batch downloads from `queue.txt`
- **Foobar2000**: Auto-refresh library after downloads

## Project Structure

```
MusicManager/
├── Backend/
│   ├── main.py                  # CLI entry point
│   ├── requirements.txt
│   ├── sync-all.bat
│   ├── sync-playlist.bat
│   ├── export-device.bat
│   ├── data/
│   │   ├── music.db             # SQLite database (gitignored)
│   │   ├── music.log            # Log file (gitignored)
│   │   └── sync/                # .spotdl sync files (gitignored)
│   └── modules/
│       ├── config.py            # Config loader (config.yaml)
│       ├── database.py          # Peewee ORM models
│       ├── downloader.py        # spotDL wrapper with queue/retry
│       ├── tagger.py            # MusicBrainz/Last.fm/Genius tagging
│       ├── organizer.py         # File/folder organization
│       ├── folder_art.py        # Cover art & artist photos
│       ├── instrumental.py      # Instrumental version search/download
│       ├── playlist.py          # Playlist management
│       ├── inbox_watcher.py     # _Inbox/ folder watcher
│       ├── queue_watcher.py     # queue.txt processor
│       ├── device.py            # SD card export
│       ├── sync.py              # Spotify playlist sync
│       ├── foobar.py            # Foobar2000 library refresh
│       └── cli.py               # Argument parsing & JSON output
└── GUI/                         # WPF frontend (separate)
```

## Setup

### Prerequisites

- Python 3.10+
- ffmpeg (in PATH)
- foobar2000 (optional, for library refresh)

### Installation

```bash
cd Backend
pip install -r requirements.txt
```

### Configuration

On first run, a default `config.yaml` is generated in the repository root. Edit it with your API keys and paths:

```yaml
paths:
  music_root: "D:/Music/Artisti"
  playlists_root: "D:/Music/Playlist"
  temp: "_Temp"
  inbox: "_Inbox"
  queue_file: "queue.txt"

spotify:
  client_id: ""
  client_secret: ""

lastfm:
  api_key: ""
  api_secret: ""

genius:
  token: ""

musicbrainz:
  user_agent: "MusicManager/1.0 (your@email.com)"

naming:
  folder_template: "{artist}/{album} ({year})"
  file_template: "{track:02d}. {title}"

download:
  format: "flac"
  max_parallel: 2
  retry_max: 3
  retry_delay: 300

foobar:
  exe_path: "C:/Program Files/foobar2000/foobar2000.exe"
```

## CLI Usage

```bash
# Download a track, album, artist, or playlist
python main.py --download "https://open.spotify.com/track/..."
python main.py --download "Pink Floyd"

# Process queue.txt
python main.py --queue

# Sync all or one Spotify playlist
python main.py --sync
python main.py --sync "Dark Side of the Moon"

# Integrity check and auto-fix
python main.py --check
python main.py --fix

# Statistics
python main.py --stats

# Search local library
python main.py --search "Comfortably Numb"

# Export to device
python main.py --export-device --playlists "Rock,Workout"

# Re-tag a file
python main.py --retag "D:/Music/Artisti/Pink Floyd/..."

# Playlist management
python main.py --playlist-list
python main.py --playlist-add
python main.py --playlist-remove
python main.py --playlist-reorder

# Poll current operation status
python main.py --status
```

All commands output **JSON to stdout** for GUI consumption.

## queue.txt Format

```
# Lines starting with # are comments
https://open.spotify.com/album/...
Pink Floyd - The Wall
# [✅ 2026-04-04] https://open.spotify.com/track/...   ← done
# [❌] Bad Artist Name                                   ← error
```

## Folder Structure (Music Library)

```
D:/Music/
├── Artisti/
│   └── Pink Floyd/
│       └── The Dark Side of the Moon (1973)/
│           ├── 01. Speak to Me.flac
│           ├── folder.jpg
│           └── desktop.ini
├── Playlist/
│   └── Classic Rock/
│       ├── 01. Pink Floyd - Speak to Me.flac
│       ├── folder.jpg
│       └── playlist.json
└── _Inbox/
    └── MyPlaylist/        ← drop files here
```

## License

MIT
