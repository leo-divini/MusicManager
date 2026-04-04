"""
tagger.py – Verifies and enriches audio file tags.

• Checks completeness after download.
• Queries MusicBrainz for missing fields.
• Queries Last.fm for genre.
• Downloads and embeds lyrics from Genius.
• Calculates and writes ReplayGain via ffmpeg.
• Backs up original tags before modifying.
"""

import json
import logging
import os
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional

import musicbrainzngs
import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK, USLT, APIC, RVA2, TXXX,
)
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from modules.config import config

logger = logging.getLogger(__name__)

# Configure MusicBrainz
_ua = config.musicbrainz_user_agent
_ua_parts = _ua.split("/", 1)
_app = _ua_parts[0].strip()
_ver_contact = _ua_parts[1].strip() if len(_ua_parts) > 1 else "1.0"
musicbrainzngs.set_useragent(_app, _ver_contact, _ua)


# ---------------------------------------------------------------------------
# Tag backup
# ---------------------------------------------------------------------------

def _backup_tags(path: Path) -> dict:
    """Return a dict copy of all current tags (for audit purposes)."""
    try:
        audio = mutagen.File(path, easy=False)
        if audio is None:
            return {}
        tags = {}
        for k, v in audio.items():
            try:
                tags[k] = str(v)
            except Exception:
                tags[k] = repr(v)
        return tags
    except Exception as exc:
        logger.warning("Could not back up tags for %s: %s", path, exc)
        return {}


def _save_tag_backup(path: Path, backup: dict) -> None:
    backup_path = path.with_suffix(path.suffix + ".tags.json")
    try:
        backup_path.write_text(json.dumps(backup, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("Tag backup write failed: %s", exc)


# ---------------------------------------------------------------------------
# Read basic metadata
# ---------------------------------------------------------------------------

def _read_tags(path: Path) -> dict:
    audio = mutagen.File(path, easy=True)
    if audio is None:
        return {}
    result = {}
    for field in ("title", "artist", "albumartist", "album", "date", "genre",
                  "tracknumber", "discnumber", "comment"):
        val = audio.get(field, [])
        result[field] = str(val[0]) if val else ""
    return result


# ---------------------------------------------------------------------------
# MusicBrainz lookup
# ---------------------------------------------------------------------------

def _mb_search_recording(artist: str, title: str) -> Optional[dict]:
    try:
        res = musicbrainzngs.search_recordings(
            artist=artist, recording=title, limit=1
        )
        recordings = res.get("recording-list", [])
        if not recordings:
            return None
        return recordings[0]
    except Exception as exc:
        logger.debug("MusicBrainz search failed: %s", exc)
        return None


def _mb_enrich(tags: dict, recording: dict) -> dict:
    enriched = dict(tags)
    if not enriched.get("title") and recording.get("title"):
        enriched["title"] = recording["title"]
    releases = recording.get("release-list", [])
    if releases:
        rel = releases[0]
        if not enriched.get("album"):
            enriched["album"] = rel.get("title", "")
        if not enriched.get("date"):
            enriched["date"] = rel.get("date", "")[:4]
        enriched["musicbrainz_recording_id"] = recording.get("id", "")
        enriched["musicbrainz_release_id"] = rel.get("id", "")
    return enriched


# ---------------------------------------------------------------------------
# Last.fm genre lookup
# ---------------------------------------------------------------------------

def _lastfm_genre(artist: str, title: str) -> Optional[str]:
    api_key = config.lastfm_api_key
    if not api_key:
        return None
    try:
        import pylast
        network = pylast.LastFMNetwork(api_key=api_key, api_secret=config.lastfm_api_secret)
        track = network.get_track(artist, title)
        tags = track.get_top_tags(limit=3)
        if tags:
            return tags[0].item.get_name()
    except Exception as exc:
        logger.debug("Last.fm genre lookup failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Genius lyrics
# ---------------------------------------------------------------------------

def _fetch_lyrics(artist: str, title: str) -> Optional[str]:
    token = config.genius_token
    if not token:
        return None
    try:
        import lyricsgenius
        genius = lyricsgenius.Genius(token, verbose=False, remove_section_headers=True)
        song = genius.search_song(title, artist, get_full_info=False)
        if song:
            return song.lyrics
    except Exception as exc:
        logger.debug("Genius lyrics fetch failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# ReplayGain via ffmpeg
# ---------------------------------------------------------------------------

def _calculate_replaygain(path: Path) -> Optional[float]:
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", str(path), "-af", "replaygain", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        for line in result.stderr.splitlines():
            if "track_gain" in line.lower():
                parts = line.split("=")
                if len(parts) >= 2:
                    val = parts[-1].strip().split()[0]
                    return float(val)
    except Exception as exc:
        logger.debug("ReplayGain calculation failed: %s", exc)
    return None


def _write_replaygain_flac(path: Path, gain_db: float) -> None:
    try:
        audio = FLAC(path)
        audio["REPLAYGAIN_TRACK_GAIN"] = f"{gain_db:+.2f} dB"
        audio.save()
    except Exception as exc:
        logger.warning("Could not write ReplayGain to FLAC %s: %s", path, exc)


def _write_replaygain_mp3(path: Path, gain_db: float) -> None:
    try:
        audio = ID3(path)
        audio.add(RVA2(desc="track", channel=1, gain=gain_db, peak=1.0))
        audio.save()
    except Exception as exc:
        logger.warning("Could not write ReplayGain to MP3 %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Write enriched tags
# ---------------------------------------------------------------------------

def _write_tags_flac(path: Path, tags: dict, lyrics: Optional[str]) -> None:
    audio = FLAC(path)
    mapping = {
        "title": "TITLE",
        "artist": "ARTIST",
        "albumartist": "ALBUMARTIST",
        "album": "ALBUM",
        "date": "DATE",
        "genre": "GENRE",
        "tracknumber": "TRACKNUMBER",
        "discnumber": "DISCNUMBER",
        "musicbrainz_recording_id": "MUSICBRAINZ_TRACKID",
        "musicbrainz_release_id": "MUSICBRAINZ_ALBUMID",
    }
    for src_key, tag_key in mapping.items():
        if tags.get(src_key):
            audio[tag_key] = str(tags[src_key])
    if lyrics:
        audio["LYRICS"] = lyrics
    audio.save()


def _write_tags_mp3(path: Path, tags: dict, lyrics: Optional[str]) -> None:
    try:
        audio = ID3(path)
    except Exception:
        audio = ID3()
    _set_id3 = lambda frame, val: audio.add(frame) if val else None
    if tags.get("title"):
        audio["TIT2"] = TIT2(encoding=3, text=tags["title"])
    if tags.get("artist"):
        audio["TPE1"] = TPE1(encoding=3, text=tags["artist"])
    if tags.get("album"):
        audio["TALB"] = TALB(encoding=3, text=tags["album"])
    if tags.get("date"):
        audio["TDRC"] = TDRC(encoding=3, text=tags["date"][:4])
    if tags.get("genre"):
        audio["TCON"] = TCON(encoding=3, text=tags["genre"])
    if tags.get("tracknumber"):
        audio["TRCK"] = TRCK(encoding=3, text=str(tags["tracknumber"]))
    if lyrics:
        audio["USLT::eng"] = USLT(encoding=3, lang="eng", desc="", text=lyrics)
    if tags.get("musicbrainz_recording_id"):
        audio["TXXX:MusicBrainz Track Id"] = TXXX(
            encoding=3, desc="MusicBrainz Track Id", text=tags["musicbrainz_recording_id"]
        )
    audio.save(path)


def _write_tags_mp4(path: Path, tags: dict, lyrics: Optional[str]) -> None:
    audio = MP4(path)
    if tags.get("title"):
        audio["\xa9nam"] = [tags["title"]]
    if tags.get("artist"):
        audio["\xa9ART"] = [tags["artist"]]
    if tags.get("album"):
        audio["\xa9alb"] = [tags["album"]]
    if tags.get("date"):
        audio["\xa9day"] = [tags["date"][:4]]
    if tags.get("genre"):
        audio["\xa9gen"] = [tags["genre"]]
    if lyrics:
        audio["\xa9lyr"] = [lyrics]
    audio.save()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tag_file(path: Path) -> dict:
    """
    Enrich tags for a single audio file.
    Returns a summary dict with keys: path, artist, title, genre, has_lyrics, replaygain.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    backup = _backup_tags(path)
    _save_tag_backup(path, backup)

    tags = _read_tags(path)
    artist = tags.get("artist", "")
    title = tags.get("title", "")

    # MusicBrainz enrichment for missing fields
    needs_mb = not all([tags.get("album"), tags.get("date"), tags.get("artist"), tags.get("title")])
    if needs_mb and artist and title:
        recording = _mb_search_recording(artist, title)
        if recording:
            tags = _mb_enrich(tags, recording)
            artist = tags.get("artist", artist)
            title = tags.get("title", title)
        time.sleep(1.1)  # MusicBrainz rate limit

    # Last.fm genre
    if not tags.get("genre") and artist and title:
        genre = _lastfm_genre(artist, title)
        if genre:
            tags["genre"] = genre

    # Lyrics
    lyrics = None
    if artist and title:
        lyrics = _fetch_lyrics(artist, title)

    # ReplayGain
    gain_db = _calculate_replaygain(path)

    # Write tags
    suffix = path.suffix.lower()
    try:
        if suffix == ".flac":
            _write_tags_flac(path, tags, lyrics)
            if gain_db is not None:
                _write_replaygain_flac(path, gain_db)
        elif suffix == ".mp3":
            _write_tags_mp3(path, tags, lyrics)
            if gain_db is not None:
                _write_replaygain_mp3(path, gain_db)
        elif suffix in (".m4a", ".aac", ".mp4"):
            _write_tags_mp4(path, tags, lyrics)
    except Exception as exc:
        logger.error("Failed to write tags for %s: %s", path, exc)

    return {
        "path": str(path),
        "artist": tags.get("artist", ""),
        "title": tags.get("title", ""),
        "album": tags.get("album", ""),
        "genre": tags.get("genre", ""),
        "has_lyrics": bool(lyrics),
        "replaygain": gain_db,
    }
