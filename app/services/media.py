"""Upload validation, safe storage and FFmpeg audio extraction."""
import hashlib
import mimetypes
import shutil
import subprocess
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from .errors import NotConfigured, ServiceError, UploadError

EXTENSIONS = {
    "audio": {"mp3", "wav", "m4a", "ogg", "oga", "flac", "aac", "opus"},
    "video": {"mp4", "mov", "webm", "mkv", "avi", "m4v"},
    "photo": {"jpg", "jpeg", "png", "webp"},
    "document": {"pdf", "txt"},
}
MIME = {
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "ogg": "audio/ogg", "oga": "audio/ogg",
    "flac": "audio/flac", "aac": "audio/aac", "opus": "audio/ogg", "mp4": "video/mp4", "m4v": "video/mp4",
    "mov": "video/quicktime", "webm": "video/webm", "mkv": "video/x-matroska", "avi": "video/x-msvideo",
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    "pdf": "application/pdf", "txt": "text/plain",
}


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _signature_ok(ext: str, head: bytes) -> bool:
    """Check magic bytes so a renamed executable cannot pass as media."""
    if ext == "mp3":
        return head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    if ext == "aac":
        return len(head) > 1 and head[0] == 0xFF and (head[1] & 0xF0) == 0xF0
    if ext == "wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if ext == "avi":
        return head[:4] == b"RIFF" and head[8:12] == b"AVI "
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext in ("m4a", "mp4", "m4v", "mov"):
        return head[4:8] == b"ftyp" or head[4:8] in (b"moov", b"mdat", b"free", b"wide")
    if ext in ("ogg", "oga", "opus"):
        return head[:4] == b"OggS"
    if ext == "flac":
        return head[:4] == b"fLaC"
    if ext in ("webm", "mkv"):
        return head[:4] == b"\x1a\x45\xdf\xa3"
    if ext in ("jpg", "jpeg"):
        return head[:3] == b"\xff\xd8\xff"
    if ext == "png":
        return head[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == "pdf":
        return head[:5] == b"%PDF-"
    if ext == "txt":
        if b"\x00" in head:
            return False
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as exc:
            # a multi-byte character may be cut at the 2048-byte boundary
            return exc.start >= len(head) - 4
        return True
    return False


def validate_upload(file_storage, allowed_kinds: tuple[str, ...]):
    """Validate a werkzeug FileStorage. Returns (kind, ext, size). Raises UploadError."""
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise UploadError("No file was selected.")
    clean = secure_filename(file_storage.filename)
    if not clean or "." not in clean:
        raise UploadError("The file name is not valid. Use letters, numbers and a proper extension.")
    ext = _ext(clean)
    kind = next((k for k in allowed_kinds if ext in EXTENSIONS[k]), None)
    if kind is None:
        allowed = ", ".join(sorted(e for k in allowed_kinds for e in EXTENSIONS[k]))
        raise UploadError(f".{ext} files are not accepted here. Allowed: {allowed}.")
    stream = file_storage.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size == 0:
        raise UploadError("The file is empty.")
    limit = current_app.config["MAX_SIZE_BY_KIND"][kind]
    if size > limit:
        raise UploadError(f"The {kind} file is too large ({size // (1024*1024)} MB). Limit: {limit // (1024*1024)} MB.")
    head = stream.read(2048)
    stream.seek(0)
    if not _signature_ok(ext, head):
        raise UploadError(f"The file content does not look like a real .{ext} file.")
    return kind, ext, size


def upload_root() -> Path:
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload(file_storage, record_id: int, kind: str, ext: str):
    """Store the file under uploads/records/<id>/<uuid>.<ext>. Returns an unsaved MediaAsset."""
    from ..models import MediaAsset

    folder = upload_root() / "records" / str(int(record_id))
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    dest = (folder / stored).resolve()
    if folder.resolve() not in dest.parents:  # defence in depth against traversal
        raise UploadError("Unsafe storage path.")
    digest = hashlib.sha256()
    size = 0
    with open(dest, "wb") as fh:
        for chunk in iter(lambda: file_storage.stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
            fh.write(chunk)
    original = secure_filename(file_storage.filename)[:255] or stored
    return MediaAsset(record_id=record_id, kind=kind, original_filename=original, stored_filename=stored,
                      mime_type=MIME.get(ext) or mimetypes.guess_type(stored)[0] or "application/octet-stream",
                      size_bytes=size, sha256=digest.hexdigest())


def asset_path(asset) -> Path:
    """Resolve an asset to an absolute path, refusing anything outside the upload root."""
    root = upload_root()
    path = (root / "records" / str(asset.record_id) / asset.stored_filename).resolve()
    if root not in path.parents:
        raise ServiceError("Unsafe media path", code="PATH_TRAVERSAL")
    return path


def delete_record_files(record_id: int) -> None:
    folder = upload_root() / "records" / str(int(record_id))
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


# --- FFmpeg ------------------------------------------------------------------------
def ffmpeg_binary() -> str | None:
    return shutil.which(current_app.config["FFMPEG_PATH"])


def ffmpeg_available() -> bool:
    return ffmpeg_binary() is not None


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """Extract mono 16 kHz WAV (what speech models expect) from a video file."""
    binary = ffmpeg_binary()
    if not binary:
        raise NotConfigured(
            "FFmpeg was not found, so audio cannot be extracted from video. Install FFmpeg "
            "(Windows: `winget install Gyan.FFmpeg`), reopen PowerShell, or set FFMPEG_PATH in .env.",
            code="FFMPEG_MISSING")
    cmd = [binary, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(out_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=current_app.config["FFMPEG_TIMEOUT"])
    except subprocess.TimeoutExpired as exc:
        raise ServiceError("FFmpeg timed out while extracting audio.", code="FFMPEG_TIMEOUT", retryable=True) from exc
    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 100:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        raise ServiceError("FFmpeg could not extract audio. The file may have no audio track or be corrupt. "
                           + " | ".join(tail), code="FFMPEG_FAILED")
    return out_path


def transcode_to_mp3(src: Path, out_path: Path) -> Path:
    """Compress audio (used when a provider limits upload size)."""
    binary = ffmpeg_binary()
    if not binary:
        raise NotConfigured("FFmpeg is required to compress large audio for this provider.", code="FFMPEG_MISSING")
    cmd = [binary, "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=current_app.config["FFMPEG_TIMEOUT"])
    if proc.returncode != 0:
        raise ServiceError("FFmpeg could not compress the audio.", code="FFMPEG_FAILED")
    return out_path
