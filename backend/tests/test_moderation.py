import io
from unittest.mock import patch


def get_token(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


def fake_image():
    return (io.BytesIO(b"fake-image-bytes"), "photo.jpg")


def create_complaint(client, token, ai_result, title="Pothole on Main St"):
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


NON_SPAM_AI_RESULT = {
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
    "visual_observation": "Person standing on a hill, unrelated to a pothole claim",
    "summary": "Mismatched report",
    "spam_flag": True,
    "spam_reason": "Photo shows an unrelated scene with no visible pothole.",
    "spam_confidence": "High"
}


def test_ai_failure_does_not_create_spam_incident(client, citizen_user):
    token = get_token(client, "citizen@example.com", "password123")

    with patch("routes.complaints.analyze_complaint") as mock_ai:
        mock_ai.side_effect = Exception("Gemini API is down")
        create_res = client.post(
            "/api/complaints/",
            data={
                "title": "Pothole on Main St",
                "description": "Deep hole near intersection",
                "latitude": "20.011",
                "longitude": "73.790",
                "image": fake_image()
            },
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"}
        )

    assert create_res.status_code == 500
    assert create_res.get_json()["message"] == "AI analysis failed"

    # No complaint was created, and the citizen is not touched.
    get_res = client.get("/api/complaints/", headers={"Authorization": f"Bearer {token}"})
    assert get_res.get_json()["complaints"] == []
    assert citizen_user.spam_count == 0
    assert citizen_user.is_suspended is False


def test_non_flagged_complaint_is_not_in_spam_queue_and_hides_spam_fields_from_citizen(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, NON_SPAM_AI_RESULT)
    assert create_res.status_code == 201
    assert "spam_review" not in create_res.get_json()["complaint"]

    spam_res = client.get("/api/officers/spam", headers={"Authorization": f"Bearer {officer_token}"})
    assert spam_res.status_code == 200
    assert spam_res.get_json()["complaints"] == []


def test_flagged_complaint_appears_in_spam_queue_with_reason_and_hides_from_citizen(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    assert create_res.status_code == 201

    # Citizen never sees the internal spam moderation fields.
    citizen_complaint = create_res.get_json()["complaint"]
    assert "spam_review" not in citizen_complaint

    get_own_res = client.get(
        f"/api/complaints/{citizen_complaint['id']}",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert "spam_review" not in get_own_res.get_json()["complaint"]

    # Officer/Admin moderation view sees the full detail.
    spam_res = client.get("/api/officers/spam", headers={"Authorization": f"Bearer {officer_token}"})
    assert spam_res.status_code == 200
    flagged = spam_res.get_json()["complaints"]
    assert len(flagged) == 1
    assert flagged[0]["spam_review"]["spam_review_status"] == "Pending"
    assert flagged[0]["spam_review"]["ai_spam_reason"] == SPAM_AI_RESULT["spam_reason"]
    assert flagged[0]["spam_review"]["ai_spam_confidence"] == "High"


def test_citizen_cannot_access_spam_list_or_review_endpoint(client, citizen_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    list_res = client.get("/api/officers/spam", headers={"Authorization": f"Bearer {citizen_token}"})
    assert list_res.status_code == 403

    review_res = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert review_res.status_code == 403


def test_officer_confirming_spam_increments_user_spam_count(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    review_res = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert review_res.status_code == 200
    body = review_res.get_json()
    assert body["complaint"]["spam_review"]["spam_review_status"] == "Confirmed"
    assert body["reported_user"]["spam_count"] == 1
    assert body["reported_user"]["is_suspended"] is False


def test_officer_rejecting_spam_does_not_increment_user_spam_count(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    review_res = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Rejected"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert review_res.status_code == 200
    body = review_res.get_json()
    assert body["complaint"]["spam_review"]["spam_review_status"] == "Rejected"
    assert body["reported_user"]["spam_count"] == 0
    assert body["reported_user"]["is_suspended"] is False


def test_cannot_review_an_already_reviewed_complaint(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    first_review = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Rejected"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert first_review.status_code == 200

    second_review = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert second_review.status_code == 400


def test_cannot_reopen_a_report_that_has_not_been_reviewed_yet(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    reopen_res = client.put(
        f"/api/officers/spam/{complaint_id}/reopen",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert reopen_res.status_code == 400


def test_reopening_a_mistaken_not_spam_decision_allows_correcting_to_confirmed(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    # Officer accidentally clicks "Not Spam".
    client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Rejected"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    my_complaints = client.get(
        "/api/complaints/", headers={"Authorization": f"Bearer {citizen_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in my_complaints)

    # Reopen puts it back in the Pending review queue - no punishment yet.
    reopen_res = client.put(
        f"/api/officers/spam/{complaint_id}/reopen",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert reopen_res.status_code == 200
    assert reopen_res.get_json()["complaint"]["spam_review"]["spam_review_status"] == "Pending"
    assert citizen_user.spam_count == 0

    pending = client.get(
        "/api/officers/spam", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in pending)

    # Now the officer can correct the mistake.
    confirm_res = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert confirm_res.status_code == 200
    assert confirm_res.get_json()["reported_user"]["spam_count"] == 1

    my_complaints_after = client.get(
        "/api/complaints/", headers={"Authorization": f"Bearer {citizen_token}"}
    ).get_json()["complaints"]
    assert all(c["id"] != complaint_id for c in my_complaints_after)


def test_reopening_a_confirmed_spam_decision_reverses_its_effects(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT, title="Wrongly confirmed pothole")
    complaint_id = create_res.get_json()["complaint"]["id"]

    confirm_res = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert confirm_res.get_json()["reported_user"]["spam_count"] == 1

    reopen_res = client.put(
        f"/api/officers/spam/{complaint_id}/reopen",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert reopen_res.status_code == 200
    body = reopen_res.get_json()
    assert body["complaint"]["spam_review"]["spam_review_status"] == "Pending"
    assert body["reported_user"]["spam_count"] == 0
    assert body["reported_user"]["is_suspended"] is False

    # The original AI analysis/evidence and the fact it was once reviewed
    # are never erased by reopening.
    spam_review = body["complaint"]["spam_review"]
    assert spam_review["ai_spam_flag"] is True
    assert spam_review["ai_spam_reason"] == SPAM_AI_RESULT["spam_reason"]
    assert spam_review["ai_spam_confidence"] == "High"
    assert spam_review["spam_reviewed_by"] is not None
    assert spam_review["spam_reviewed_at"] is not None
    assert spam_review["spam_reopened_by"] is not None
    assert spam_review["spam_reopened_at"] is not None

    # Restored to the citizen's active complaints and the officer queue.
    my_complaints = client.get(
        "/api/complaints/", headers={"Authorization": f"Bearer {citizen_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in my_complaints)

    officer_complaints = client.get(
        "/api/officers/complaints", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in officer_complaints)


def test_reopen_then_reconfirm_does_not_double_count_spam(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    client.put(
        f"/api/officers/spam/{complaint_id}/reopen",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    second_confirm = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    assert second_confirm.status_code == 200
    assert second_confirm.get_json()["reported_user"]["spam_count"] == 1
    assert citizen_user.spam_count == 1


def test_reopening_a_confirmed_spam_lifts_suspension_when_it_drops_the_count_below_threshold(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    complaint_ids = []
    for i in range(5):
        create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT, title=f"Spammy report {i}")
        complaint_id = create_res.get_json()["complaint"]["id"]
        complaint_ids.append(complaint_id)
        client.put(
            f"/api/officers/spam/{complaint_id}/review",
            json={"decision": "Confirmed"},
            headers={"Authorization": f"Bearer {officer_token}"}
        )

    assert citizen_user.spam_count == 5
    assert citizen_user.is_suspended is True

    reopen_res = client.put(
        f"/api/officers/spam/{complaint_ids[0]}/reopen",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert reopen_res.status_code == 200
    body = reopen_res.get_json()
    assert body["reported_user"]["spam_count"] == 4
    assert body["reported_user"]["is_suspended"] is False


def test_five_confirmed_spam_incidents_suspends_the_account(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    for i in range(5):
        create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT, title=f"Spammy report {i}")
        complaint_id = create_res.get_json()["complaint"]["id"]

        review_res = client.put(
            f"/api/officers/spam/{complaint_id}/review",
            json={"decision": "Confirmed"},
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert review_res.status_code == 200
        reported_user = review_res.get_json()["reported_user"]
        assert reported_user["spam_count"] == i + 1

        if i < 4:
            assert reported_user["is_suspended"] is False
        else:
            assert reported_user["is_suspended"] is True


def test_suspended_user_cannot_login(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    for i in range(5):
        create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT, title=f"Spammy report {i}")
        complaint_id = create_res.get_json()["complaint"]["id"]
        client.put(
            f"/api/officers/spam/{complaint_id}/review",
            json={"decision": "Confirmed"},
            headers={"Authorization": f"Bearer {officer_token}"}
        )

    login_res = client.post("/api/auth/login", json={
        "email": "citizen@example.com",
        "password": "password123"
    })
    assert login_res.status_code == 403
    assert "suspended" in login_res.get_json()["message"].lower()
    assert "token" not in login_res.get_json()


def test_ai_flag_alone_keeps_complaint_active_and_spam_count_unchanged(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT)
    complaint_id = create_res.get_json()["complaint"]["id"]

    # AI flagging alone must not remove the complaint from any active view,
    # and must not touch the reporting citizen's spam_count.
    my_complaints = client.get(
        "/api/complaints/", headers={"Authorization": f"Bearer {citizen_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in my_complaints)

    officer_complaints = client.get(
        "/api/officers/complaints", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in officer_complaints)

    assert citizen_user.spam_count == 0
    assert citizen_user.is_suspended is False


def test_confirmed_spam_removed_from_active_operational_views(client, citizen_user, officer_user, admin_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")
    admin_token = get_token(client, "admin@example.com", "admin123")

    create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT, title="Fake pothole report")
    complaint_id = create_res.get_json()["complaint"]["id"]

    review_res = client.put(
        f"/api/officers/spam/{complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert review_res.status_code == 200

    # Gone from the citizen's own active complaints...
    my_complaints = client.get(
        "/api/complaints/", headers={"Authorization": f"Bearer {citizen_token}"}
    ).get_json()["complaints"]
    assert my_complaints == []

    # ...and from the officer/admin work queue...
    officer_complaints = client.get(
        "/api/officers/complaints", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert all(c["id"] != complaint_id for c in officer_complaints)

    # ...and from the heatmap...
    heatmap_points = client.get(
        "/api/officers/heatmap", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["points"]
    assert len(heatmap_points) == 0

    # ...and its Low/High/Critical priority no longer affects admin analytics.
    analytics = client.get(
        "/api/admin/analytics", headers={"Authorization": f"Bearer {admin_token}"}
    ).get_json()
    assert analytics["summary"]["total_complaints"] == 0
    assert analytics["breakdown"]["priorities"] == {}

    # But the moderation/audit trail is preserved, not deleted - an
    # Officer/Admin can still see it (and its AI spam reason) via the
    # Confirmed spam history view.
    spam_history = client.get(
        "/api/officers/spam?status=Confirmed", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert len(spam_history) == 1
    assert spam_history[0]["id"] == complaint_id
    assert spam_history[0]["spam_review"]["ai_spam_reason"] == SPAM_AI_RESULT["spam_reason"]
    assert spam_history[0]["spam_review"]["spam_reviewed_by"] is not None
    assert spam_history[0]["spam_review"]["spam_reviewed_at"] is not None

    # And it's no longer in the pending queue.
    pending = client.get(
        "/api/officers/spam", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert pending == []


def test_suspended_user_existing_token_loses_access(client, citizen_user, officer_user):
    # Token issued while the account is still in good standing.
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    for i in range(5):
        create_res = create_complaint(client, citizen_token, SPAM_AI_RESULT, title=f"Spammy report {i}")
        complaint_id = create_res.get_json()["complaint"]["id"]
        client.put(
            f"/api/officers/spam/{complaint_id}/review",
            json={"decision": "Confirmed"},
            headers={"Authorization": f"Bearer {officer_token}"}
        )

    # The same pre-suspension token must now be rejected on any protected route.
    protected_res = client.get(
        "/api/complaints/",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert protected_res.status_code == 401
