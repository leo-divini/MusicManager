"""
database.py – SQLite database models via Peewee ORM.

Tables: tracks, artists, albums, playlists, playlist_tracks, queue, sync_log.
"""

import datetime
from pathlib import Path

from peewee import (
    SqliteDatabase,
    Model,
    AutoField,
    CharField,
    IntegerField,
    FloatField,
    BooleanField,
    DateTimeField,
    TextField,
    ForeignKeyField,
)

from modules.config import config

_db_path = config.db_path
_db_path.parent.mkdir(parents=True, exist_ok=True)

db = SqliteDatabase(
    str(_db_path),
    pragmas={
        "journal_mode": "wal",
        "cache_size": -1 * 64000,
        "foreign_keys": 1,
        "synchronous": "NORMAL",
    },
)


class BaseModel(Model):
    class Meta:
        database = db


# ---------------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------------

class Artist(BaseModel):
    class Meta:
        table_name = "artists"

    id = AutoField()
    name = CharField(unique=True, index=True)
    musicbrainz_id = CharField(null=True)
    lastfm_url = CharField(null=True)
    photo_path = CharField(null=True)
    date_added = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))


# ---------------------------------------------------------------------------
# Albums
# ---------------------------------------------------------------------------

class Album(BaseModel):
    class Meta:
        table_name = "albums"

    id = AutoField()
    title = CharField(index=True)
    artist = ForeignKeyField(Artist, backref="albums", null=True, on_delete="SET NULL")
    year = IntegerField(null=True)
    genre = CharField(null=True)
    musicbrainz_id = CharField(null=True)
    cover_path = CharField(null=True)
    date_added = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------

class Track(BaseModel):
    class Meta:
        table_name = "tracks"

    id = AutoField()
    path = CharField(unique=True, index=True)
    hash_md5 = CharField(null=True, index=True)
    artist = CharField(null=True, index=True)
    album = CharField(null=True, index=True)
    title = CharField(null=True, index=True)
    year = IntegerField(null=True)
    genre = CharField(null=True)
    format = CharField(null=True)           # flac, mp3, …
    bitrate = IntegerField(null=True)       # kbps
    duration = FloatField(null=True)        # seconds
    track_number = IntegerField(null=True)
    disc_number = IntegerField(null=True)
    has_lyrics = BooleanField(default=False)
    has_cover = BooleanField(default=False)
    replaygain = FloatField(null=True)      # dB
    spotify_id = CharField(null=True)
    musicbrainz_id = CharField(null=True)
    date_added = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))
    date_modified = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

class Playlist(BaseModel):
    class Meta:
        table_name = "playlists"

    id = AutoField()
    name = CharField(unique=True, index=True)
    source = CharField(null=True)           # e.g. "spotify:playlist:37i9dQ..."
    folder_path = CharField(null=True)
    cover_path = CharField(null=True)
    date_created = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))
    date_modified = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))


class PlaylistTrack(BaseModel):
    class Meta:
        table_name = "playlist_tracks"
        indexes = (
            (("playlist", "position"), False),
        )

    id = AutoField()
    playlist = ForeignKeyField(Playlist, backref="playlist_tracks", on_delete="CASCADE")
    track = ForeignKeyField(Track, backref="playlist_tracks", null=True, on_delete="SET NULL")
    position = IntegerField()
    title = CharField(null=True)
    artist = CharField(null=True)
    origin_path = CharField(null=True)
    playlist_path = CharField(null=True)
    date_added = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))


# ---------------------------------------------------------------------------
# Download Queue
# ---------------------------------------------------------------------------

class QueueItem(BaseModel):
    class Meta:
        table_name = "queue"

    id = AutoField()
    url = CharField(null=True)
    name = CharField(null=True)
    type = CharField(
        null=True,
        choices=[("artist", "artist"), ("album", "album"), ("track", "track"), ("playlist", "playlist")],
    )
    status = CharField(
        default="queued",
        choices=[
            ("queued", "queued"),
            ("downloading", "downloading"),
            ("done", "done"),
            ("error", "error"),
        ],
    )
    progress = FloatField(default=0.0)
    error_message = TextField(null=True)
    date_added = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))
    date_modified = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))
    retries = IntegerField(default=0)


# ---------------------------------------------------------------------------
# Sync Log
# ---------------------------------------------------------------------------

class SyncLog(BaseModel):
    class Meta:
        table_name = "sync_log"

    id = AutoField()
    playlist_name = CharField(null=True, index=True)
    action = CharField()    # added, removed, reordered, error
    detail = TextField(null=True)
    timestamp = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))


# ---------------------------------------------------------------------------
# Device Export State
# ---------------------------------------------------------------------------

class DeviceExport(BaseModel):
    class Meta:
        table_name = "device_export"

    id = AutoField()
    playlist_name = CharField(index=True)
    track_path = CharField()
    mp3_hash = CharField(null=True)
    exported_at = DateTimeField(default=lambda: datetime.datetime.now(datetime.timezone.utc))


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

ALL_MODELS = [Artist, Album, Track, Playlist, PlaylistTrack, QueueItem, SyncLog, DeviceExport]


def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    with db:
        db.create_tables(ALL_MODELS, safe=True)
