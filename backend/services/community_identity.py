"""
Privacy-preserving public identities for the community feed.

A citizen appears publicly only as e.g. "Citizen #A4F29C". The handle is an
HMAC of the internal user id keyed by the server's SECRET_KEY, so:
  - it is stable (the same citizen always gets the same handle),
  - it cannot be reversed into a user id, email or name without the key,
  - it is computed server-side only; no client ever sends or chooses one.

Officers/Admins are shown with a single role label, never a name.
"""

import hashlib
import hmac

from flask import current_app

HANDLE_LENGTH = 6
OFFICIAL_LABEL = "NMC Official"


def anonymous_handle(user_id):
    secret = (current_app.config.get("SECRET_KEY") or "").encode("utf-8")
    digest = hmac.new(
        secret + b":community-handle",
        str(int(user_id)).encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"Citizen #{digest[:HANDLE_LENGTH].upper()}"


def public_author(user, viewer_id=None):
    """The ONLY shape in which an author is ever serialized publicly -
    no id, name, email, or role beyond "is this an official"."""
    is_official = bool(user and user.role in ("Officer", "Admin"))
    return {
        "handle": OFFICIAL_LABEL if is_official else anonymous_handle(user.id) if user else "Citizen",
        "is_official": is_official,
        "is_you": bool(user and viewer_id is not None and user.id == int(viewer_id)),
    }
