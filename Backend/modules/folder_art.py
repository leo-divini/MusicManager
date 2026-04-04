"""
folder_art.py – Downloads and embeds cover art and artist photos.

• Downloads artist photo from MusicBrainz / Last.fm.
• Downloads album covers: MusicBrainz (≥1000px) → iTunes API → Spotify.
• Saves folder.jpg in every artist and album folder.
• Generates desktop.ini for Windows folder icon support.
• Sets Hidden+System attributes on desktop.ini and ReadOnly on folder.jpg (Windows).
"""

import ctypes
import logging
import os
import platform
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import requests
from PIL import Image

import musicbrainzngs
from modules.config import config

logger = logging.getLogger(__name__)

_COVER_MIN_SIZE = 1000
_TIMEOUT = 15

# Re-configure MusicBrainz user-agent (already done in tagger but also needed standalone)
try:
    _ua = config.musicbrainz_user_agent.split("/", 1)
    musicbrainzngs.set_useragent(
        _ua[0].strip(),
        _ua[1].strip() if len(_ua) > 1 else "1.0",
        config.musicbrainz_user_agent,
    )
except Exception:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download_image(url: str) -> Optional[bytes]:
    try:
        resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": config.musicbrainz_user_agent})
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        logger.debug("Image download failed: %s", exc)
        return None


def _save_folder_jpg(folder: Path, data: bytes) -> Path:
    dest = folder / "folder.jpg"
    img = Image.open(BytesIO(data)).convert("RGB")
    img.save(str(dest), "JPEG", quality=92, optimize=True)
    _set_readonly(dest)
    logger.info("Saved folder.jpg: %s", dest)
    return dest


def _set_readonly(path: Path) -> None:
    if platform.system() != "Windows":
        return
    try:
        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x1)  # FILE_ATTRIBUTE_READONLY
    except Exception:
        pass


def _set_hidden_system(path: Path) -> None:
    if platform.system() != "Windows":
        return
    try:
        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x2 | 0x4)  # HIDDEN | SYSTEM
    except Exception:
        pass


def _write_desktop_ini(folder: Path) -> None:
    ini = folder / "desktop.ini"
    content = "[.ShellClassInfo]\nIconResource=folder.jpg,0\n[ViewState]\nMode=\nVid=\nFolderType=Music\n"
    ini.write_text(content, encoding="utf-8")
    _set_hidden_system(ini)


# ---------------------------------------------------------------------------
# MusicBrainz cover art
# ---------------------------------------------------------------------------

def _mb_cover(release_id: str) -> Optional[bytes]:
    try:
        data = musicbrainzngs.get_image_front(release_id, size="1200")
        return data
    except Exception as exc:
        logger.debug("MusicBrainz cover fetch failed for %s: %s", release_id, exc)
    return None


def _mb_release_id(artist: str, album: str) -> Optional[str]:
    try:
        res = musicbrainzngs.search_releases(artist=artist, release=album, limit=1)
        releases = res.get("release-list", [])
        if releases:
            return releases[0].get("id")
    except Exception as exc:
        logger.debug("MusicBrainz release search failed: %s", exc)
    return None


def _mb_cover_valid(data: bytes) -> bool:
    try:
        img = Image.open(BytesIO(data))
        w, h = img.size
        return w >= _COVER_MIN_SIZE and h >= _COVER_MIN_SIZE
    except Exception:
        return False


# ---------------------------------------------------------------------------
# iTunes cover art
# ---------------------------------------------------------------------------

def _itunes_cover(artist: str, album: str) -> Optional[bytes]:
    query = quote_plus(f"{artist} {album}")
    url = f"https://itunes.apple.com/search?term={query}&entity=album&limit=1"
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            art_url = results[0].get("artworkUrl100", "").replace("100x100", "3000x3000")
            if art_url:
                return _download_image(art_url)
    except Exception as exc:
        logger.debug("iTunes cover fetch failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Spotify cover art
# ---------------------------------------------------------------------------

def _get_spotify_token() -> Optional[str]:
    if not config.spotify_client_id or not config.spotify_client_secret:
        return None
    try:
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(config.spotify_client_id, config.spotify_client_secret),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as exc:
        logger.debug("Spotify token error: %s", exc)
        return None


def _spotify_cover(artist: str, album: str) -> Optional[bytes]:
    token = _get_spotify_token()
    if not token:
        return None
    query = quote_plus(f"album:{album} artist:{artist}")
    url = f"https://api.spotify.com/v1/search?q={query}&type=album&limit=1"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        resp.raise_for_status()
        items = resp.json().get("albums", {}).get("items", [])
        if items:
            images = items[0].get("images", [])
            if images:
                return _download_image(images[0]["url"])
    except Exception as exc:
        logger.debug("Spotify cover fetch failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Artist photo
# ---------------------------------------------------------------------------

def _mb_artist_id(artist: str) -> Optional[str]:
    try:
        res = musicbrainzngs.search_artists(artist=artist, limit=1)
        artists = res.get("artist-list", [])
        if artists:
            return artists[0].get("id")
    except Exception as exc:
        logger.debug("MusicBrainz artist search failed: %s", exc)
    return None


def _lastfm_artist_photo(artist: str) -> Optional[bytes]:
    api_key = config.lastfm_api_key
    if not api_key:
        return None
    try:
        url = (
            f"https://ws.audioscrobbler.com/2.0/?method=artist.getinfo"
            f"&artist={quote_plus(artist)}&api_key={api_key}&format=json"
        )
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        images = resp.json().get("artist", {}).get("image", [])
        for img in reversed(images):
            img_url = img.get("#text", "")
            if img_url and "2a96cbd8b46e442fc41c2b86b821562f" not in img_url:
                return _download_image(img_url)
    except Exception as exc:
        logger.debug("Last.fm artist photo failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def download_cover(artist: str, album: str, dest_folder: Path) -> Optional[Path]:
    """
    Download the best available album cover and save as folder.jpg.
    Returns the path to folder.jpg, or None if no image was found.
    """
    dest_folder = Path(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)

    # 1. MusicBrainz
    release_id = _mb_release_id(artist, album)
    if release_id:
        data = _mb_cover(release_id)
        if data and _mb_cover_valid(data):
            path = _save_folder_jpg(dest_folder, data)
            _write_desktop_ini(dest_folder)
            return path

    # 2. iTunes
    data = _itunes_cover(artist, album)
    if data:
        path = _save_folder_jpg(dest_folder, data)
        _write_desktop_ini(dest_folder)
        return path

    # 3. Spotify
    data = _spotify_cover(artist, album)
    if data:
        path = _save_folder_jpg(dest_folder, data)
        _write_desktop_ini(dest_folder)
        return path

    logger.warning("No cover art found for %s / %s", artist, album)
    return None


def download_artist_photo(artist: str, dest_folder: Path) -> Optional[Path]:
    """
    Download the artist photo and save as folder.jpg in the artist folder.
    Returns the path, or None if nothing found.
    """
    dest_folder = Path(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)

    data = _lastfm_artist_photo(artist)
    if data:
        path = _save_folder_jpg(dest_folder, data)
        _write_desktop_ini(dest_folder)
        return path

    logger.warning("No artist photo found for %s", artist)
    return None


def process_folder(folder: Path) -> None:
    """
    Ensure folder.jpg and desktop.ini exist for the given folder.
    Tries to infer artist/album from the folder path.
    """
    folder = Path(folder)
    folder_jpg = folder / "folder.jpg"
    if folder_jpg.exists():
        return

    parts = folder.parts
    if len(parts) >= 2:
        artist = parts[-2]
        album = parts[-1]
        download_cover(artist, album, folder)
    else:
        logger.debug("Cannot infer artist/album from path: %s", folder)
