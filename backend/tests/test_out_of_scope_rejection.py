import io
from unittest.mock import patch

from models.complaint import Complaint


def get_token(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


def fake_image():
    return (io.BytesIO(b"fake-image-bytes"), "photo.jpg")


NON_SPAM_AI_RESULT = {
    "category": "Road Infrastructure",
    "priority": "High",
    "department": "Roads Dept",
    "visual_observation": "A private compound wall, not a public road.",
    "summary": "Complaint about a private premises",
    "spam_flag": False,
    "spam_reason": "",
    "spam_confidence": ""
}


def create_complaint(client, token, title="Pothole inside private society", latitude="20.011", longitude="73.790"):
    with patch("routes.complaints.analyze_complaint") as mock_ai:
        mock_ai.return_value = NON_SPAM_AI_RESULT
        return client.post(
            "/api/complaints/",
            data={
                "title": title,
                "description": "Issue reported inside a gated private society",
                "latitude": latitude,
                "longitude": longitude,
                "image": fake_image()
            },
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"}
        )


def test_officer_rejects_complaint_as_out_of_scope(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    reject_res = client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Private Society / Apartment"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert reject_res.status_code == 200
    body = reject_res.get_json()["complaint"]
    assert body["rejection"]["reason"] == "Private Society / Apartment"
    assert body["rejection"]["status"] == "Rejected - Out of Scope"

    # Reviewer and timestamp are saved (audit trail).
    stored = Complaint.query.get(complaint_id)
    assert stored.rejection_status == "Rejected"
    assert stored.rejection_reason == "Private Society / Apartment"
    assert stored.rejected_by == officer_user.id
    assert stored.rejected_at is not None

    # The complaint remains in the database (not deleted).
    assert stored is not None

    # It disappears from the active officer/admin work queue...
    officer_complaints = client.get(
        "/api/officers/complaints", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert all(c["id"] != complaint_id for c in officer_complaints)

    # ...and from the heatmap...
    heatmap_points = client.get(
        "/api/officers/heatmap", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["points"]
    assert all(p["latitude"] != stored.latitude or p["longitude"] != stored.longitude for p in heatmap_points)

    # ...but is still visible in the dedicated rejected/historical queue.
    rejected_queue = client.get(
        "/api/officers/complaints?rejection_status=Rejected",
        headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in rejected_queue)


def test_reject_requires_a_valid_reason(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    empty_res = client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": ""},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert empty_res.status_code == 400

    invalid_res = client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Because I said so"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert invalid_res.status_code == 400


def test_reject_other_reason_requires_explanation(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    no_explanation_res = client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Other"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert no_explanation_res.status_code == 400

    with_explanation_res = client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Other", "explanation": "It's a school playground, not municipal land"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert with_explanation_res.status_code == 200
    assert with_explanation_res.get_json()["complaint"]["rejection"]["explanation"] == (
        "It's a school playground, not municipal land"
    )


def test_cannot_reject_an_already_rejected_complaint(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Private Property"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    second_res = client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Outside NMC Jurisdiction"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert second_res.status_code == 400


def test_out_of_scope_rejection_does_not_touch_spam_state(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Private Property"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    assert citizen_user.spam_count == 0
    assert citizen_user.is_suspended is False

    stored = Complaint.query.get(complaint_id)
    assert stored.spam_review_status == "NotFlagged"

    # Never appears in the spam moderation queues at any status.
    for status in ("Pending", "Confirmed", "Rejected"):
        spam_list = client.get(
            f"/api/officers/spam?status={status}",
            headers={"Authorization": f"Bearer {officer_token}"}
        ).get_json()["complaints"]
        assert all(c["id"] != complaint_id for c in spam_list)


def test_out_of_scope_rejection_decrements_civic_issue_report_count_only_for_itself(
    client, citizen_user, officer_user
):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    client.post("/api/auth/register", json={
        "name": "Second Citizen",
        "email": "second@example.com",
        "password": "password123"
    })
    second_token = get_token(client, "second@example.com", "password123")

    # Same category/location/summary so both land on the same CivicIssue.
    legit_res = create_complaint(client, citizen_token, title="Pothole here", latitude="20.0110", longitude="73.7900")
    out_of_scope_res = create_complaint(
        client, second_token, title="Pothole here too", latitude="20.0111", longitude="73.7901"
    )

    issue_id = legit_res.get_json()["complaint"]["civic_issue"]["id"]
    assert out_of_scope_res.get_json()["complaint"]["civic_issue"]["id"] == issue_id

    issues_before = client.get(
        "/api/officers/issues", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["issues"]
    assert [i for i in issues_before if i["id"] == issue_id][0]["report_count"] == 2

    out_of_scope_id = out_of_scope_res.get_json()["complaint"]["id"]
    client.put(
        f"/api/complaints/{out_of_scope_id}/reject",
        json={"reason": "Private Society / Apartment"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    issues_after = client.get(
        "/api/officers/issues", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["issues"]
    assert [i for i in issues_after if i["id"] == issue_id][0]["report_count"] == 1


def test_citizen_sees_rejection_status_and_reason_but_cannot_reject(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Not a Municipal Responsibility"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    detail_res = client.get(
        f"/api/complaints/{complaint_id}",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    rejection = detail_res.get_json()["complaint"]["rejection"]
    assert rejection["reason"] == "Not a Municipal Responsibility"
    assert rejection["status"] == "Rejected - Out of Scope"

    # Still shows up in the citizen's own complaint list (not deleted/hidden).
    my_complaints = client.get(
        "/api/complaints/", headers={"Authorization": f"Bearer {citizen_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in my_complaints)

    # Citizen cannot call the rejection endpoint themselves - the backend
    # enforces this by role, not just by hiding a button.
    second_create = create_complaint(client, citizen_token, title="Another private issue")
    second_id = second_create.get_json()["complaint"]["id"]
    forbidden_res = client.put(
        f"/api/complaints/{second_id}/reject",
        json={"reason": "Private Property"},
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert forbidden_res.status_code == 403


def test_reopen_restores_active_queue_and_preserves_audit_trail(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Private Property"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    reopen_res = client.put(
        f"/api/complaints/{complaint_id}/reopen-rejection",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert reopen_res.status_code == 200
    assert reopen_res.get_json()["complaint"]["rejection"] is None

    # Back in the active officer/admin queue.
    officer_complaints = client.get(
        "/api/officers/complaints", headers={"Authorization": f"Bearer {officer_token}"}
    ).get_json()["complaints"]
    assert any(c["id"] == complaint_id for c in officer_complaints)

    # Previous decision is not silently erased - preserved for audit.
    stored = Complaint.query.get(complaint_id)
    assert stored.rejection_status == "NotRejected"
    assert stored.rejection_reason == "Private Property"
    assert stored.rejected_by == officer_user.id
    assert stored.rejected_at is not None
    assert stored.rejection_reopened_by == officer_user.id
    assert stored.rejection_reopened_at is not None


def test_cannot_reopen_a_complaint_that_was_never_rejected(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    reopen_res = client.put(
        f"/api/complaints/{complaint_id}/reopen-rejection",
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert reopen_res.status_code == 400


def test_citizen_cannot_reopen_a_rejected_complaint(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    create_res = create_complaint(client, citizen_token)
    complaint_id = create_res.get_json()["complaint"]["id"]

    client.put(
        f"/api/complaints/{complaint_id}/reject",
        json={"reason": "Private Property"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )

    forbidden_res = client.put(
        f"/api/complaints/{complaint_id}/reopen-rejection",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert forbidden_res.status_code == 403
