"""Citizen-facing before/after evidence: what a reporter may see, per review state."""

import json
import os

from database.db import db
from models.civic_issue import CivicIssue
from models.complaint import Complaint
from models.resolution_review import ResolutionReview
from tests.helpers import JPEG_BYTES
from tests.test_resolution_workflow import (
    auth,
    create_complaint,
    submit_review,
    token,
)

# Staff-only text that must never reach a citizen response.
COMPLETION_NOTE = "Crew repaired the road and checked every reported location."
DISPOSITION_NOTE = "Repair covers this report."
REJECTION_REASON = "The photo does not show the repaired area."


def evidence(client, bearer, complaint_id):
    return client.get(f"/api/complaints/{complaint_id}/resolution-evidence", headers=auth(bearer))


def setup(client):
    citizen = token(client, "citizen@example.com", "password123")
    officer = token(client, "officer@example.com", "officer123")
    chief = token(client, "chief@example.com", "chief123")
    complaint = create_complaint(client, citizen)
    return citizen, officer, chief, complaint


def decide(client, chief, review_id, decision, reason=None):
    body = {"decision": decision}
    if reason:
        body["rejection_reason"] = reason
    return client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision", json=body, headers=auth(chief)
    )


def stored_name(review):
    db.session.expire_all()
    return db.session.get(ResolutionReview, review["id"]).image_filename


def assert_review_photo_absent(raw, review):
    """Neither the staff path nor the stored file name of a completion photo may reach a citizen."""
    assert review["image_path"] not in raw
    assert stored_name(review) not in raw


def assert_no_staff_data(response):
    raw = response.get_data(as_text=True)
    for secret in (DISPOSITION_NOTE, REJECTION_REASON, "dispositions", "rejection_reason",
                   "submitted_by", "reviewed_by", "stale_reason", "latitude", "longitude"):
        assert secret not in raw, secret


def test_no_review_shows_only_the_original_photo(client, citizen_user, officer_user, chief_officer_user):
    citizen, _, _, complaint = setup(client)
    response = evidence(client, citizen, complaint["id"])
    assert response.status_code == 200
    data = response.get_json()["evidence"]
    assert data["state"] == "none"
    assert data["before"]["image_url"].startswith("/uploads/")
    assert data["before"]["reported_at"]
    assert data["after"] is None
    assert data["work_submitted_at"] is None and data["approved_at"] is None


def test_pending_review_exposes_status_but_no_completion_evidence(
    client, citizen_user, officer_user, chief_officer_user
):
    citizen, officer, _, complaint = setup(client)
    review = submit_review(client, officer, complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]

    response = evidence(client, citizen, complaint["id"])
    data = response.get_json()["evidence"]
    assert data["state"] == "awaiting_review"
    assert data["issue_status"] == "Pending Review"
    assert data["work_submitted_at"]
    assert data["after"] is None
    assert data["approved_at"] is None
    raw = response.get_data(as_text=True)
    assert_review_photo_absent(raw, review)
    assert COMPLETION_NOTE not in raw
    assert_no_staff_data(response)


def test_stale_review_still_reads_as_awaiting_verification(client, citizen_user, officer_user, chief_officer_user):
    citizen, officer, _, complaint = setup(client)
    review = submit_review(client, officer, complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]
    create_complaint(client, citizen, latitude="20.0111", longitude="73.7901", title="Same pothole")
    assert db.session.get(ResolutionReview, review["id"]).state == "Stale"

    response = evidence(client, citizen, complaint["id"])
    data = response.get_json()["evidence"]
    assert data["state"] == "awaiting_review"
    assert data["after"] is None
    assert_review_photo_absent(response.get_data(as_text=True), review)
    assert_no_staff_data(response)


def test_rejected_review_is_returned_for_correction_without_evidence_or_reason(
    client, citizen_user, officer_user, chief_officer_user
):
    citizen, officer, chief, complaint = setup(client)
    review = submit_review(client, officer, complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]
    assert decide(client, chief, review["id"], "Rejected", REJECTION_REASON).status_code == 200

    response = evidence(client, citizen, complaint["id"])
    data = response.get_json()["evidence"]
    assert data["state"] == "returned"
    assert data["returned_at"]
    assert data["after"] is None and data["approved_at"] is None
    assert data["issue_status"] == "In Progress"
    raw = response.get_data(as_text=True)
    assert_review_photo_absent(raw, review) and COMPLETION_NOTE not in raw
    assert_no_staff_data(response)


def test_approved_review_shows_before_and_after_separately(client, citizen_user, officer_user, chief_officer_user):
    citizen, officer, chief, complaint = setup(client)
    original_url = complaint["image_url"]
    review = submit_review(client, officer, complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]
    assert decide(client, chief, review["id"], "Approved").status_code == 200

    response = evidence(client, citizen, complaint["id"])
    data = response.get_json()["evidence"]
    assert data["state"] == "approved"
    assert data["issue_status"] == "Resolved"
    assert data["before"]["image_url"] == original_url
    # The approved photo is an authenticated path, never a public /uploads URL or the staff path.
    after_path = f"/complaints/{complaint['id']}/resolution-evidence/after-image"
    assert data["after"]["image_path"] == after_path
    assert not data["after"]["image_path"].startswith("/uploads/")
    assert data["after"]["image_path"] != data["before"]["image_url"]
    assert_review_photo_absent(response.get_data(as_text=True), review)
    assert data["after"]["report"] == COMPLETION_NOTE
    assert data["work_submitted_at"] and data["approved_at"]
    assert_no_staff_data(response)

    # The complaint itself still points at the untouched original photo.
    detail = client.get(f"/api/complaints/{complaint['id']}", headers=auth(citizen)).get_json()["complaint"]
    assert detail["image_url"] == original_url
    assert set(data["after"]) == {"image_path", "report"}
    photo = client.get(f"/api/complaints{after_path[len('/complaints'):]}", headers=auth(citizen))
    assert photo.status_code == 200 and photo.data == JPEG_BYTES
    assert photo.headers["X-Content-Type-Options"] == "nosniff" and "no-store" in photo.headers["Cache-Control"]
    assert set(data) == {"complaint_id", "state", "issue_status", "before", "work_submitted_at",
                         "returned_at", "approved_at", "after"}


def test_old_approval_is_not_shown_after_the_issue_is_reopened(client, citizen_user, officer_user, chief_officer_user):
    citizen, officer, chief, complaint = setup(client)
    issue_id = complaint["civic_issue"]["id"]
    review = submit_review(client, officer, issue_id, [complaint["id"]]).get_json()["review"]
    decide(client, chief, review["id"], "Approved")
    reopened = client.put(f"/api/officers/issues/{issue_id}/status", json={"status": "In Progress"}, headers=auth(officer))
    assert reopened.status_code == 200

    data = evidence(client, citizen, complaint["id"]).get_json()["evidence"]
    assert data["state"] == "none"
    assert data["after"] is None
    assert data["before"]["image_url"]


def test_missing_completion_file_returns_the_report_without_a_broken_link(
    client, citizen_user, officer_user, chief_officer_user
):
    citizen, officer, chief, complaint = setup(client)
    review = submit_review(client, officer, complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]
    decide(client, chief, review["id"], "Approved")
    os.remove(os.path.join(client.application.config["PRIVATE_UPLOAD_FOLDER"], stored_name(review)))

    data = evidence(client, citizen, complaint["id"]).get_json()["evidence"]
    assert data["state"] == "approved"
    assert data["after"]["image_path"] is None
    assert data["after"]["report"] == COMPLETION_NOTE
    assert data["before"]["image_url"]


def test_complaint_without_an_original_photo_has_no_before_image(client, citizen_user, officer_user):
    citizen = token(client, "citizen@example.com", "password123")
    issue = CivicIssue(category="Other", latitude=20.0, longitude=73.0, report_count=1)
    db.session.add(issue)
    db.session.flush()
    complaint = Complaint(title="No photo", description="d", category="Other", latitude=20.0, longitude=73.0,
                          user_id=citizen_user_id(), issue_id=issue.id, image_filename=None)
    db.session.add(complaint)
    db.session.commit()

    data = evidence(client, citizen, complaint.id).get_json()["evidence"]
    assert data["before"]["image_url"] is None
    assert data["state"] == "none"


def citizen_user_id():
    from models.user import User
    return User.query.filter_by(email="citizen@example.com").first().id


def test_excluded_complaint_never_sees_the_issues_evidence(client, citizen_user, officer_user, chief_officer_user):
    citizen, officer, chief, complaint = setup(client)
    second = client.post("/api/auth/register", json={"name": "Second", "email": "second@example.com", "password": "password123"})
    other = second.get_json()["token"]
    excluded = create_complaint(client, other, latitude="20.0111", longitude="73.7901", title="Society light")
    assert excluded["civic_issue"]["id"] == complaint["civic_issue"]["id"]
    rejected = client.put(f"/api/complaints/{excluded['id']}/reject", json={"reason": "Private Property"}, headers=auth(officer))
    assert rejected.status_code == 200

    review = submit_review(client, officer, complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]
    assert decide(client, chief, review["id"], "Approved").status_code == 200

    assert evidence(client, citizen, complaint["id"]).get_json()["evidence"]["state"] == "approved"
    response = evidence(client, other, excluded["id"])
    data = response.get_json()["evidence"]
    assert data["state"] == "not_applicable"
    assert data["after"] is None
    assert_review_photo_absent(response.get_data(as_text=True), review)
    assert data["before"]["image_url"]


def test_access_follows_the_complaint_privacy_rules(client, citizen_user, officer_user, chief_officer_user):
    citizen, officer, chief, complaint = setup(client)
    review = submit_review(client, officer, complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]
    decide(client, chief, review["id"], "Approved")
    url = f"/api/complaints/{complaint['id']}/resolution-evidence"

    assert client.get(url).status_code == 401  # no token

    stranger = client.post("/api/auth/register", json={"name": "Stranger", "email": "stranger@example.com", "password": "password123"})
    assert client.get(url, headers=auth(stranger.get_json()["token"])).status_code == 404  # someone else's complaint

    assert client.get(url, headers=auth(chief)).status_code == 404  # same as GET /<id>: not a staff complaint viewer
    assert client.get("/api/complaints/99999/resolution-evidence", headers=auth(citizen)).status_code == 404

    staff = client.get(url, headers=auth(officer))
    assert staff.status_code == 200  # Officers/Admins may view any complaint, as elsewhere
    assert staff.get_json() == client.get(url, headers=auth(citizen)).get_json()  # and get nothing extra


def test_uploads_route_cannot_read_outside_the_upload_folder(client):
    for path in ("/uploads/../app.py", "/uploads/..%2Fapp.py", "/uploads/%2e%2e/%2e%2e/config.py"):
        assert client.get(path).status_code == 404
