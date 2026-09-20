import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from utils.time_helper import to_iso8601, utc_now


def get_token(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


def fake_image():
    return (io.BytesIO(b"fake-image-bytes"), "photo.jpg")


AI_RESULT = {
    "category": "Road Infrastructure",
    "priority": "High",
    "department": "Roads Dept",
    "visual_observation": "Pothole spotted",
    "summary": "Fix pothole",
    "spam_flag": False,
    "spam_reason": "",
    "spam_confidence": ""
}

SPAM_AI_RESULT = {
    "category": "Road Infrastructure",
    "priority": "Low",
    "department": "Roads Dept",
    "visual_observation": "Unrelated photo",
    "summary": "Mismatched report",
    "spam_flag": True,
    "spam_reason": "Photo shows an unrelated scene.",
    "spam_confidence": "High"
}


def create_complaint(client, token, ai_result=AI_RESULT, title="Pothole on Main St"):
    with patch("routes.complaints.analyze_complaint") as mock_ai:
        mock_ai.return_value = ai_result
        return client.post(
            "/api/complaints/",
            data={
                "title": title,
                "description": "Deep hole near intersection",
                "latitude": "20.011",
                "longitude": "73.790",
                "image": fake_image()
            },
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"}
        )


def parse_instant(value):
    """Mirrors how a spec-compliant client (including the browser's
    `new Date(...)`) reads the API's timestamp strings: only a value that
    carries explicit timezone info can be resolved to an unambiguous
    real-world instant."""
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"{value!r} has no timezone info - a client could misread it as local time"
    return parsed


def assert_is_recent_utc_instant(value, within_seconds=30):
    parsed = parse_instant(value)
    assert parsed.utcoffset() == timedelta(0)
    delta = abs((datetime.now(timezone.utc) - parsed).total_seconds())
    assert delta < within_seconds, f"{value!r} is not within {within_seconds}s of now (delta={delta}s)"


def test_time_helper_attaches_utc_and_is_idempotent():
    naive = datetime(2026, 9, 18, 14, 45, 0)
    once = to_iso8601(naive)
    assert once.endswith("+00:00")

    # Re-parsing and re-serializing an already-timezone-aware value must
    # represent the exact same instant - no double conversion/shift.
    twice = to_iso8601(datetime.fromisoformat(once))
    assert once == twice


def test_complaint_created_at_is_an_unambiguous_utc_instant(client, citizen_user):
    token = get_token(client, "citizen@example.com", "password123")
    create_res = create_complaint(client, token)

    created_at = create_res.get_json()["complaint"]["created_at"]
    assert_is_recent_utc_instant(created_at)

    # Same value, fetched back through the list/detail endpoints, must be
    # byte-identical - one consistent serialization path everywhere.
    complaint_id = create_res.get_json()["complaint"]["id"]
    list_created_at = client.get(
        "/api/complaints/", headers={"Authorization": f"Bearer {token}"}
    ).get_json()["complaints"][0]["created_at"]
    detail_created_at = client.get(
        f"/api/complaints/{complaint_id}", headers={"Authorization": f"Bearer {token}"}
    ).get_json()["complaint"]["created_at"]

    assert created_at == list_created_at == detail_created_at


def test_spam_review_and_notification_timestamps_are_consistent_utc_instants(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    review_res = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    reviewed_at = review_res.get_json()["complaint"]["spam_review"]["spam_reviewed_at"]
    assert_is_recent_utc_instant(reviewed_at)

    reopen_res = client.put(
        f"/api/officers/spam/{complaint_id}/reopen",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    reopened_at = reopen_res.get_json()["complaint"]["spam_review"]["spam_reopened_at"]
    assert_is_recent_utc_instant(reopened_at)
    assert parse_instant(reopened_at) >= parse_instant(reviewed_at)

    notif_res = client.get(
        "/api/notifications/", headers={"Authorization": f"Bearer {citizen_token}"}
    )
    notification_created_at = notif_res.get_json()["notifications"][0]["created_at"]
    assert_is_recent_utc_instant(notification_created_at)


def test_civic_issue_timestamps_are_unambiguous_utc_instants(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    issue_id = create_res.get_json()["complaint"]["civic_issue"]["id"]

    issues = client.get(
        "/api/officers/issues", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["issues"]
    issue = [i for i in issues if i["id"] == issue_id][0]

    assert_is_recent_utc_instant(issue["created_at"])
    assert_is_recent_utc_instant(issue["updated_at"])


def test_admin_user_created_at_is_an_unambiguous_utc_instant(client, admin_user, citizen_user):
    admin_token = get_token(client, "admin@example.com", "admin123")

    users = client.get(
        "/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"}
    ).get_json()["users"]

    for user in users:
        assert_is_recent_utc_instant(user["created_at"])


def test_utc_now_helper_returns_timezone_aware_datetime():
    value = utc_now()
    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)
