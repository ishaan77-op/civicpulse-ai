"""User-facing notification text carries no emoji, including notifications stored before this change."""

from database.db import db
from models.notification import Notification
from tests.test_resolution_workflow import auth, token
from utils.text_cleanup import strip_emoji


def test_strip_emoji_removes_pictographs_and_tidies_spacing_but_keeps_plain_symbols():
    assert strip_emoji("✅ The civic issue was resolved") == "The civic issue was resolved"
    assert strip_emoji("\U0001F6A9 Complaint Declined & Flagged — reason") == "Complaint Declined & Flagged — reason"
    assert strip_emoji("\U0001F527 NMC has started work \U0001F3DB️ now") == "NMC has started work now"
    assert strip_emoji("Rated 4★ and checked ✓") == "Rated 4★ and checked ✓"
    assert strip_emoji(None) is None and strip_emoji("") == ""


def test_stored_notifications_with_emoji_are_shown_without_it(client, citizen_user):
    db.session.add(Notification(user_id=citizen_user.id, message="✅ The civic issue you reported has been resolved."))
    db.session.add(Notification(user_id=citizen_user.id, message="\U0001F6A9 Complaint Declined & Flagged — spam"))
    db.session.commit()
    bearer = token(client, "citizen@example.com", "password123")
    messages = [n["message"] for n in client.get("/api/notifications/", headers=auth(bearer)).get_json()["notifications"]]
    assert "The civic issue you reported has been resolved." in messages
    assert "Complaint Declined & Flagged — spam" in messages
    assert all(strip_emoji(m) == m for m in messages)
