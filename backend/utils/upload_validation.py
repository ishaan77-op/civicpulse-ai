"""Validation and safe storage for complaint photo uploads."""

import os
import hashlib

from werkzeug.utils import secure_filename

# extension -> image kind detected from the file's leading bytes
ALLOWED_EXTENSIONS = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "webp": "webp",
}


class UploadError(Exception):
    """A rejected upload. `message` is safe to show to the client."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def sniff_image_kind(header):
    """Return 'jpeg' / 'png' / 'webp' from the first bytes, else None."""
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image_upload(file_storage, max_bytes):
    """Check extension, size and real image content *before* anything is
    written to disk. Returns the sanitized filename or raises UploadError.
    Leaves the stream rewound so it can be saved afterwards."""

    filename = secure_filename(file_storage.filename or "")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if extension not in ALLOWED_EXTENSIONS:
        raise UploadError("Unsupported image type. Please upload a JPG, PNG or WebP photo.")

    stream = file_storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)

    if size == 0:
        raise UploadError("The uploaded photo is empty.")

    if size > max_bytes:
        raise UploadError(
            f"The photo is too large. The maximum size is {max_bytes // (1024 * 1024)} MB.",
            413,
        )

    kind = sniff_image_kind(stream.read(12))
    stream.seek(0)

    if kind is None or kind != ALLOWED_EXTENSIONS[extension]:
        raise UploadError("The uploaded file is not a valid JPG, PNG or WebP image.")

    return filename


def save_upload(file_storage, folder, stored_name):
    """Save via a temporary file and an atomic rename, so an interrupted or
    failed write never leaves a partial file under the final name. Returns
    the final path."""
    os.makedirs(folder, exist_ok=True)
    final_path = os.path.join(folder, stored_name)
    temp_path = final_path + ".part"

    try:
        file_storage.save(temp_path)
        os.replace(temp_path, final_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    return final_path


def upload_sha256(file_storage):
    """Hash an already-validated upload while preserving its stream position."""
    stream = file_storage.stream
    stream.seek(0)
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()
