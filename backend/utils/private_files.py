"""Serving staff-only images.

Private photos (field-work updates, completion evidence, correction photos) are never reachable
through the public ``/uploads`` route.  They are read only through authenticated endpoints, and the
file name always comes from a database row, never from the request.

New uploads are written to ``PRIVATE_UPLOAD_FOLDER``.  Files uploaded before this change still sit in
the public ``UPLOAD_FOLDER``; the endpoints can read them from there (``legacy_folder``) so nothing
breaks, while ``/uploads`` itself refuses to serve any file that a private record refers to.
"""

import os

from flask import jsonify, send_from_directory

IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def locate_image(filename, private_folder, legacy_folder=None):
    """Return ``(folder, mimetype)`` for a usable stored image, or ``None``.

    A usable name is a bare file name (no directory parts, not hidden) with an image extension that
    exists in the private folder, or else in the legacy public folder.
    """
    if not filename or filename != os.path.basename(filename) or filename.startswith("."):
        return None
    mimetype = IMAGE_TYPES.get(os.path.splitext(filename)[1].lower())
    if not mimetype:
        return None
    for folder in (private_folder, legacy_folder):
        if folder and os.path.isfile(os.path.join(folder, filename)):
            return folder, mimetype
    return None


def send_private_image(filename, private_folder, legacy_folder=None, not_found="Evidence not found"):
    """Send a stored image with no-store caching and nosniff, or the same 404 for every failure."""
    found = locate_image(filename, private_folder, legacy_folder)
    if not found:
        return jsonify({"message": not_found}), 404
    folder, mimetype = found
    response = send_from_directory(folder, filename, mimetype=mimetype, conditional=False)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response
