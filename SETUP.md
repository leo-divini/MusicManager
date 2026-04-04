# MusicManager – Setup Guide

Follow these steps to get MusicManager running on Windows.

---

## Prerequisites

### 1. Install Python 3.11

1. Download the Python 3.11 installer from <https://www.python.org/downloads/release/python-3119/>.
2. Run the installer. **Check "Add Python to PATH"** before clicking Install.
3. Verify the installation:
   ```
   python --version
   ```
   Expected output: `Python 3.11.x`

### 2. Install ffmpeg and add it to PATH

1. Download a static Windows build from <https://ffmpeg.org/download.html> (e.g. "ffmpeg-release-essentials.zip" from gyan.dev or BtbN).
2. Extract the archive to a permanent location, e.g. `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your system `PATH`:
   - Open **Start → System → Advanced system settings → Environment Variables**.
   - Under *System variables*, select `Path` and click **Edit → New**.
   - Type `C:\ffmpeg\bin` and click OK through all dialogs.
4. Open a new terminal and verify:
   ```
   ffmpeg -version
   ```

---

## Installation

### 3. Clone the repository

```
git clone https://github.com/leo-divini/MusicManager.git
cd MusicManager
```

### 4. Install Python dependencies

```
pip install -r Backend/requirements.txt
```

> **Note:** `pywin32` requires a post-install step on some setups:
> ```
> python -m pip install --upgrade pywin32
> python Scripts/pywin32_postinstall.py -install
> ```

### 5. Configure the application

Copy the template and fill in your values:

```
copy config.yaml.template config.yaml
```

Open `config.yaml` in a text editor and fill in:

| Key | Where to get it |
|-----|----------------|
| `spotify.client_id` / `spotify.client_secret` | [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) – create an app, copy Client ID & Secret |
| `lastfm.api_key` / `lastfm.api_secret` | [Last.fm API](https://www.last.fm/api/account/create) – register an account, create an API application |
| `genius.token` | [Genius API Clients](https://genius.com/api-clients) – click "New API Client", copy the *Client Access Token* |
| `musicbrainz.user_agent` | Replace with your app name and contact e-mail, e.g. `MusicManager/1.0 (you@example.com)` |
| `paths.music_root` | Full path to your music library folder, e.g. `D:/Music/Artisti` |
| `paths.playlists_root` | Full path to your playlists folder, e.g. `D:/Music/Playlist` |
| `foobar.exe_path` | Full path to `foobar2000.exe`, e.g. `C:/Program Files/foobar2000/foobar2000.exe` |

### 6. Initialise the database

```
cd Backend
python main.py --stats
```

This creates `Backend/data/music.db` and prints `{}` (empty stats) if everything is working.

---

## Running the GUI

### 7. Open the solution in Visual Studio 2022

1. Install [Visual Studio 2022](https://visualstudio.microsoft.com/) with the **.NET desktop development** workload.
2. Open `GUI/MusicManager.sln`.
3. Visual Studio will restore NuGet packages automatically.
4. Press **F5** or click **Start** to build and run.

The GUI will launch and auto-detect your Python installation. If Python is not on PATH, set the path manually in `PythonBridge.cs` (`PythonExecutable` property) or in your environment variables.

---

## Usage

### CLI (Backend only)

```
cd Backend

# Download a track, album, or Spotify URL
python main.py --download "https://open.spotify.com/track/..."

# Process all pending items in queue.txt
python main.py --queue

# Sync all Spotify-sourced playlists
python main.py --sync

# Sync a specific playlist
python main.py --sync "My Playlist"

# Check library integrity
python main.py --check

# Show library statistics
python main.py --stats

# Search the library
python main.py --search "Artist Name"
```

All commands output JSON to stdout for easy scripting and GUI integration.

### Inbox watcher

Drop audio files into subfolders of `_Inbox/`. The subfolder name becomes the playlist name. Files are automatically imported and the subfolder is cleared after processing.

### Queue file

Add URLs or search terms (one per line) to `queue.txt`, then run:

```
python main.py --queue
```

Processed items are marked with `# [✅ date]`; failed items with `# [❌]`.

---

## Troubleshooting

- **`ModuleNotFoundError`** – run `pip install -r Backend/requirements.txt` again.
- **`ffmpeg not found`** – verify `ffmpeg -version` works in a new terminal.
- **Spotify/Last.fm errors** – double-check the API keys in `config.yaml`.
- **GUI doesn't find Python** – ensure Python is on `PATH`, or set `PythonExecutable` in `PythonBridge.cs` to the full path (e.g. `C:\Python311\python.exe`).
