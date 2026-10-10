"""Storage for evidence videos and call recordings.

Pictures stay small and live inside the case record. Videos and recordings are bigger, so they are kept here:
- In memory by default (lost on restart; fine for a rehearsal).
- In a Cloud Storage bucket when MEDIA_BUCKET is set (kept; use this for the live demo).
Only metadata goes into the database.
"""
import os
import threading
import time

from .config import Config

MAX_UPLOAD = 15 * 1024 * 1024     # one citizen video
MAX_RECORDING = 40 * 1024 * 1024  # one call recording
ALLOWED_UPLOAD = ("video/mp4", "video/webm", "video/quicktime", "video/3gpp", "image/jpeg", "image/png", "image/webp", "audio/webm", "audio/mpeg", "audio/mp4")

_lock = threading.Lock()
_mem = {}       # key -> bytes
_pending = {}   # upload id -> {"mime", "data", "at"}


def _bucket():
    name = os.environ.get("MEDIA_BUCKET", "")
    if not name:
        return None
    from google.cloud import storage  # imported only when a bucket is configured

    return storage.Client(project=Config.GCP_PROJECT).bucket(name)


def put(key, data, mime):
    b = _bucket()
    if b is not None:
        blob = b.blob(key)
        blob.upload_from_string(data, content_type=mime)
        return "gcs"
    with _lock:
        _mem[key] = data
    return "memory"


def get(key, storage):
    if storage == "gcs":
        b = _bucket()
        return b.blob(key).download_as_bytes() if b is not None else b""
    with _lock:
        return _mem.get(key, b"")


def append(key, chunk, storage):
    """Add a recording chunk. Recordings are small enough to rebuild the whole object each time."""
    data = get(key, storage) + chunk
    if len(data) > MAX_RECORDING:
        return None
    put(key, data, "video/webm")
    return len(data)


def stash_upload(upload_id, mime, data):
    with _lock:
        cutoff = time.time() - 3600
        for k in [k for k, v in _pending.items() if v["at"] < cutoff]:
            del _pending[k]
        _pending[upload_id] = {"mime": mime, "data": data, "at": time.time()}


def take_upload(upload_id):
    with _lock:
        return _pending.pop(upload_id, None)
