import io
from unittest.mock import patch

from models.notification import Notification


def get_token(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


def fake_image():
    return (io.BytesIO(b"fake-image-bytes"), "photo.jpg")


SPAM_AI_RESULT = {
    "category": "Road Infrastructure",
    "priority": "Low",
    "department": "Roads Dept",
    "visual_observation": "Person standing on a hill, unrelated to a pothole claim",
    "summary": "Mismatched report",
    "spam_flag": True,
    "spam_reason": "Photo shows an unrelated scene with no visible pothole.",
    "spam_confidence": "High"
}


def create_flagged_complaint(client, token, title="Pothole on Main St"):
    with patch("routes.complaints.analyze_complaint") as mock_ai:
        mock_ai.return_value = SPAM_AI_RESULT
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


def test_no_notification_from_ai_flag_alone(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")

    create_flagged_complaint(client, citizen_token)

    notif_res = client.get(
        "/api/notifications/",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert notif_res.status_code == 200
    assert notif_res.get_json()["notifications"] == []


def test_no_notification_on_rejected_decision(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_flagged_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Rejected"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    notif_res = client.get(
        "/api/notifications/",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert notif_res.get_json()["notifications"] == []


def test_notification_created_on_confirmed_spam(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_flagged_complaint(client, citizen_token, title="Very large pothole")
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    notif_res = client.get(
        "/api/notifications/",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    notifications = notif_res.get_json()["notifications"]
    assert len(notifications) == 1

    notification = notifications[0]
    assert notification["complaint_id"] == complaint_id
    assert "Very large pothole" in notification["message"]
    assert "1/5" in notification["message"]
    assert notification["is_read"] is False

    # No raw AI internals leaked to the citizen via the notification.
    assert "High" not in notification["message"]
    assert SPAM_AI_RESULT["spam_reason"] not in notification["message"]


def test_notification_mentions_suspension_at_five_confirmed(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    for i in range(5):
        create_res = create_flagged_complaint(client, citizen_token, title=f"Spammy report {i}")
        complaint_id = create_res.get_json()["complaint"]["id"]
        client.put(
            f"/api/officers/spam/{complaint_id}/review",
            json={"decision": "Confirmed"},
            headers={"Authorization": f"Bearer {officer_token}"}
        )

    # The already-issued citizen token is now revoked (suspended account) -
    # confirm that separately, and check the last notification's wording
    # via a direct model query since the citizen can no longer fetch it.
    notif_res = client.get(
        "/api/notifications/",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert notif_res.status_code == 401

    latest_notification = Notification.query.filter_by(
        user_id=citizen_user.id
    ).order_by(Notification.id.desc()).first()

    assert latest_notification is not None
    assert "5/5" in latest_notification.message
    assert "suspended" in latest_notification.message.lower()


def test_citizen_can_only_read_own_notifications(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_flagged_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    notif_res = client.get(
        "/api/notifications/",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    notification_id = notif_res.get_json()["notifications"][0]["id"]

    # Register a second, unrelated citizen and confirm they cannot read
    # or mark someone else's notification.
    client.post("/api/auth/register", json={
        "name": "Other Citizen",
        "email": "other@example.com",
        "password": "password123"
    })
    other_token = get_token(client, "other@example.com", "password123")

    other_list_res = client.get(
        "/api/notifications/",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    assert other_list_res.get_json()["notifications"] == []

    other_read_res = client.put(
        f"/api/notifications/{notification_id}/read",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    assert other_read_res.status_code == 404


def test_mark_notification_as_read(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_flagged_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    notif_res = client.get(
        "/api/notifications/",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    notification_id = notif_res.get_json()["notifications"][0]["id"]

    read_res = client.put(
        f"/api/notifications/{notification_id}/read",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert read_res.status_code == 200
    assert read_res.get_json()["notification"]["is_read"] is True

    unread_res = client.get(
        "/api/notifications/?unread_only=true",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert unread_res.get_json()["notifications"] == []
