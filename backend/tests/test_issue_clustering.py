import io
from unittest.mock import patch


def get_token(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


def fake_image():
    return (io.BytesIO(b"fake-image-bytes"), "photo.jpg")


POTHOLE_AI_RESULT = {
    "category": "Road Infrastructure",
    "priority": "High",
    "department": "Roads Dept",
    "visual_observation": "A large pothole in the middle of a paved road.",
    "summary": "Large pothole blocking traffic on the main road.",
    "spam_flag": False,
    "spam_reason": "",
    "spam_confidence": ""
}

STREETLIGHT_AI_RESULT = {
    "category": "Street Lighting",
    "priority": "Medium",
    "department": "Electrical Dept",
    "visual_observation": "A streetlight pole that is not lit at night.",
    "summary": "Streetlight has been out for several nights.",
    "spam_flag": False,
    "spam_reason": "",
    "spam_confidence": ""
}


def submit_complaint(client, token, ai_result, latitude, longitude, title):
    with patch("routes.complaints.analyze_complaint") as mock_ai:
        mock_ai.return_value = ai_result
        return client.post(
            "/api/complaints/",
            data={
                "title": title,
                "description": ai_result["summary"],
                "latitude": str(latitude),
                "longitude": str(longitude),
                "image": fake_image()
            },
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"}
        )


def register_citizen(client, email, name="Another Citizen"):
    client.post("/api/auth/register", json={
        "name": name,
        "email": email,
        "password": "password123"
    })
    return get_token(client, email, "password123")


def test_nearby_same_category_similar_reports_share_one_issue(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    other_token = register_citizen(client, "second@example.com")

    first_res = submit_complaint(client, citizen_token, POTHOLE_AI_RESULT, 20.0110, 73.7903, "Big pothole")
    second_res = submit_complaint(client, other_token, POTHOLE_AI_RESULT, 20.0111, 73.7904, "Huge pothole here too")

    first_issue_id = first_res.get_json()["complaint"]["civic_issue"]["id"]
    second_issue_id = second_res.get_json()["complaint"]["civic_issue"]["id"]

    assert first_issue_id == second_issue_id

    officer_token = get_token(client, "officer@example.com", "officer123")
    issues_res = client.get("/api/officers/issues", headers={"Authorization": f"Bearer {officer_token}"})
    issues = issues_res.get_json()["issues"]
    matching = [i for i in issues if i["id"] == first_issue_id][0]
    assert matching["report_count"] == 2


def test_different_category_creates_a_separate_issue(client, citizen_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")

    pothole_res = submit_complaint(client, citizen_token, POTHOLE_AI_RESULT, 20.0110, 73.7903, "Big pothole")
    light_res = submit_complaint(client, citizen_token, STREETLIGHT_AI_RESULT, 20.0110, 73.7903, "Dark street")

    pothole_issue = pothole_res.get_json()["complaint"]["civic_issue"]["id"]
    light_issue = light_res.get_json()["complaint"]["civic_issue"]["id"]

    assert pothole_issue != light_issue


def test_far_away_same_category_creates_a_separate_issue(client, citizen_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")

    near_res = submit_complaint(client, citizen_token, POTHOLE_AI_RESULT, 20.0110, 73.7903, "Big pothole")
    # ~1km away - well outside the ~150m match radius.
    far_res = submit_complaint(client, citizen_token, POTHOLE_AI_RESULT, 20.0200, 73.7903, "Big pothole elsewhere")

    near_issue = near_res.get_json()["complaint"]["civic_issue"]["id"]
    far_issue = far_res.get_json()["complaint"]["civic_issue"]["id"]

    assert near_issue != far_issue


def test_duplicate_reports_never_affect_spam_count(client, citizen_user, officer_user, admin_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    other_token = register_citizen(client, "third@example.com", "Third Citizen")

    submit_complaint(client, citizen_token, POTHOLE_AI_RESULT, 20.0110, 73.7903, "Big pothole")
    submit_complaint(client, other_token, POTHOLE_AI_RESULT, 20.0111, 73.7904, "Same big pothole")
    submit_complaint(client, citizen_token, POTHOLE_AI_RESULT, 20.0112, 73.7905, "Pothole again")

    officer_token = get_token(client, "officer@example.com", "officer123")

    # Non-flagged, corroborating reports must never create moderation work...
    spam_res = client.get("/api/officers/spam", headers={"Authorization": f"Bearer {officer_token}"})
    assert spam_res.get_json()["complaints"] == []

    # ...and must never touch any citizen's spam_count.
    admin_token = get_token(client, "admin@example.com", "admin123")
    users_res = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    for user in users_res.get_json()["users"]:
        assert user["spam_count"] == 0
        assert user["is_suspended"] is False


def test_confirming_clustered_complaint_as_spam_decrements_report_count(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    other_token = register_citizen(client, "fourth@example.com", "Fourth Citizen")

    spam_result = dict(POTHOLE_AI_RESULT, spam_flag=True, spam_reason="Unrelated photo", spam_confidence="High")

    legit_res = submit_complaint(client, other_token, POTHOLE_AI_RESULT, 20.0110, 73.7903, "Big pothole")
    spam_res = submit_complaint(client, citizen_token, spam_result, 20.0111, 73.7904, "Also a pothole (fake)")

    issue_id = legit_res.get_json()["complaint"]["civic_issue"]["id"]
    assert spam_res.get_json()["complaint"]["civic_issue"]["id"] == issue_id

    officer_token = get_token(client, "officer@example.com", "officer123")
    issues_before = client.get("/api/officers/issues", headers={"Authorization": f"Bearer {officer_token}"}).get_json()["issues"]
    assert [i for i in issues_before if i["id"] == issue_id][0]["report_count"] == 2

    spam_complaint_id = spam_res.get_json()["complaint"]["id"]
    client.put(
        f"/api/officers/spam/{spam_complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    issues_after = client.get("/api/officers/issues", headers={"Authorization": f"Bearer {officer_token}"}).get_json()["issues"]
    assert [i for i in issues_after if i["id"] == issue_id][0]["report_count"] == 1


def test_reopening_a_confirmed_spam_clustered_complaint_restores_report_count(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    other_token = register_citizen(client, "fifth@example.com", "Fifth Citizen")

    spam_result = dict(POTHOLE_AI_RESULT, spam_flag=True, spam_reason="Unrelated photo", spam_confidence="High")

    legit_res = submit_complaint(client, other_token, POTHOLE_AI_RESULT, 20.0110, 73.7903, "Big pothole")
    spam_res = submit_complaint(client, citizen_token, spam_result, 20.0111, 73.7904, "Also a pothole (fake)")

    issue_id = legit_res.get_json()["complaint"]["civic_issue"]["id"]
    spam_complaint_id = spam_res.get_json()["complaint"]["id"]

    officer_token = get_token(client, "officer@example.com", "officer123")
    client.put(
        f"/api/officers/spam/{spam_complaint_id}/review",
        json={"decision": "Confirmed"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    issues_after_confirm = client.get("/api/officers/issues", headers={"Authorization": f"Bearer {officer_token}"}).get_json()["issues"]
    assert [i for i in issues_after_confirm if i["id"] == issue_id][0]["report_count"] == 1

    client.put(
        f"/api/officers/spam/{spam_complaint_id}/reopen",
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    issues_after_reopen = client.get("/api/officers/issues", headers={"Authorization": f"Bearer {officer_token}"}).get_json()["issues"]
    assert [i for i in issues_after_reopen if i["id"] == issue_id][0]["report_count"] == 2


def test_issue_status_update_does_not_overwrite_individual_complaint_status(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = submit_complaint(client, citizen_token, POTHOLE_AI_RESULT, 20.0110, 73.7903, "Big pothole")
    complaint = create_res.get_json()["complaint"]
    issue_id = complaint["civic_issue"]["id"]
    assert complaint["status"] == "Pending"

    status_res = client.put(
        f"/api/officers/issues/{issue_id}/status",
        json={"status": "In Progress"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert status_res.status_code == 200
    assert status_res.get_json()["issue"]["status"] == "In Progress"

    # The individual complaint's own status is untouched...
    complaint_res = client.get(
        f"/api/complaints/{complaint['id']}",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    updated_complaint = complaint_res.get_json()["complaint"]
    assert updated_complaint["status"] == "Pending"

    # ...but the citizen can still see the linked issue's real status.
    assert updated_complaint["civic_issue"]["status"] == "In Progress"


def test_citizen_cannot_access_issue_cluster_endpoints(client, citizen_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")

    list_res = client.get("/api/officers/issues", headers={"Authorization": f"Bearer {citizen_token}"})
    assert list_res.status_code == 403

    status_res = client.put(
        "/api/officers/issues/1/status",
        json={"status": "In Progress"},
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert status_res.status_code == 403
