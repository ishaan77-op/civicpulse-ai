"""
Tests for Feature 2: Chief Officer Review & Final Resolution Verification.

Covers all 18 required test scenarios from the spec:
 1.  An authorized Officer can submit a valid resolution request.
 2.  Missing completion note is rejected (400).
 3.  Missing final evidence photo is rejected (400).
 4.  Submission creates a server-timestamped review request.
 5.  Submission does NOT mark the complaint Resolved.
 6.  A Citizen cannot submit a resolution request (403).
 7.  An unauthorized user cannot review a request (403).
 8.  An authorized Chief Officer can approve a valid request.
 9.  Approval changes the complaint status to Resolved.
10.  Reviewer identity and timestamp come from the server/authenticated session.
11.  The submitting Officer cannot approve their own request (403).
12.  A Chief Officer can reject a request with a reason.
13.  Rejection leaves the complaint unresolved.
14.  The rejection reason is visible to the Officer via GET.
15.  The Officer can submit corrected evidence after rejection.
16.  A request cannot be approved twice (400).
17.  Ordinary work updates cannot bypass the review process.
18.  Existing complaint and work-update tests remain passing (verified by
     running the full pytest suite after these tests).
"""
import io
from datetime import datetime

from database.db import db
from models.complaint import Complaint
from models.resolution_review import ResolutionReview
from models.civic_issue import CivicIssue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_token(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


def fake_image(name="evidence.jpg"):
    return (io.BytesIO(b"fake-evidence-bytes"), name)


def _make_complaint(app, citizen_user):
    """Create a minimal complaint row directly in the DB."""
    with app.app_context():
        issue = CivicIssue(
            category="Road Infrastructure",
            latitude=20.0,
            longitude=73.8,
            location_label="Test Rd",
            ai_summary="Test issue",
        )
        db.session.add(issue)
        db.session.flush()

        c = Complaint(
            title="Pothole on Test Rd",
            description="Big hole",
            category="Road Infrastructure",
            location="Test Rd",
            latitude=20.0,
            longitude=73.8,
            user_id=citizen_user.id,
            issue_id=issue.id,
        )
        db.session.add(c)
        db.session.commit()
        return c.id


def _submit_review(client, complaint_id, officer_token, **kwargs):
    """Helper to POST a resolution review, returning the response."""
    data = {
        "completion_note": kwargs.get("completion_note", "All work completed."),
        "image": kwargs.get("image", fake_image()),
    }
    if "latitude" in kwargs:
        data["latitude"] = str(kwargs["latitude"])
    if "longitude" in kwargs:
        data["longitude"] = str(kwargs["longitude"])
    if kwargs.get("no_image"):
        data.pop("image", None)
    if kwargs.get("no_note"):
        data.pop("completion_note", None)
    return client.post(
        f"/api/officers/complaints/{complaint_id}/resolution-review",
        data=data,
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {officer_token}"},
    )


def _decide(client, review_id, chief_token, decision, rejection_note=None):
    """Helper to PUT a decision on a resolution review."""
    body = {"decision": decision}
    if rejection_note:
        body["rejection_note"] = rejection_note
    return client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decide",
        json=body,
        headers={"Authorization": f"Bearer {chief_token}"},
    )


# ---------------------------------------------------------------------------
# Test 1: Officer can submit a valid resolution request
# ---------------------------------------------------------------------------

def test_officer_can_submit_resolution_request(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    token = get_token(client, "officer@example.com", "officer123")

    res = _submit_review(client, complaint_id, token)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["review"]["id"] is not None
    assert body["review"]["completion_note"] == "All work completed."


# ---------------------------------------------------------------------------
# Test 2: Missing completion note is rejected
# ---------------------------------------------------------------------------

def test_missing_completion_note_rejected(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    token = get_token(client, "officer@example.com", "officer123")

    res = _submit_review(client, complaint_id, token, no_note=True)
    assert res.status_code == 400
    assert "completion note" in res.get_json()["message"].lower()


# ---------------------------------------------------------------------------
# Test 3: Missing final evidence photo is rejected
# ---------------------------------------------------------------------------

def test_missing_evidence_photo_rejected(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    token = get_token(client, "officer@example.com", "officer123")

    res = _submit_review(client, complaint_id, token, no_image=True)
    assert res.status_code == 400
    assert "photo" in res.get_json()["message"].lower()


# ---------------------------------------------------------------------------
# Test 4: Submission creates a server-timestamped review request
# ---------------------------------------------------------------------------

def test_submission_creates_server_timestamped_review(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    token = get_token(client, "officer@example.com", "officer123")

    res = _submit_review(client, complaint_id, token)
    assert res.status_code == 201
    ts = res.get_json()["review"]["submitted_at"]
    assert ts is not None
    parsed = datetime.fromisoformat(ts)
    assert parsed is not None

    with app.app_context():
        rv = ResolutionReview.query.get(res.get_json()["review"]["id"])
        assert rv is not None
        assert rv.submitted_at is not None


# ---------------------------------------------------------------------------
# Test 5: Submission does NOT mark the complaint Resolved
# ---------------------------------------------------------------------------

def test_submission_does_not_resolve_complaint(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    token = get_token(client, "officer@example.com", "officer123")

    res = _submit_review(client, complaint_id, token)
    assert res.status_code == 201

    complaint_status = res.get_json()["complaint"]["status"]
    assert complaint_status == "Pending Review"
    assert complaint_status != "Resolved"

    with app.app_context():
        c = Complaint.query.get(complaint_id)
        assert c.status != "Resolved"
        assert c.status == "Pending Review"


# ---------------------------------------------------------------------------
# Test 6: A Citizen cannot submit a resolution request
# ---------------------------------------------------------------------------

def test_citizen_cannot_submit_resolution_request(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    citizen_token = get_token(client, "citizen@example.com", "password123")

    data = {
        "completion_note": "Citizen trying to resolve.",
        "image": fake_image(),
    }
    res = client.post(
        f"/api/officers/complaints/{complaint_id}/resolution-review",
        data=data,
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Test 7: An unauthorized user cannot review a request (non-Chief-Officer)
# ---------------------------------------------------------------------------

def test_officer_cannot_decide_resolution_request(client, app, citizen_user, officer_user, chief_officer_user):
    """A plain Officer must not be able to approve/reject a resolution review."""
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")

    submit_res = _submit_review(client, complaint_id, officer_token)
    assert submit_res.status_code == 201
    review_id = submit_res.get_json()["review"]["id"]

    # Attempt decision with an Officer token (not Chief Officer)
    decide_res = _decide(client, review_id, officer_token, "Approved")
    assert decide_res.status_code == 403


# ---------------------------------------------------------------------------
# Test 8 & 9: Chief Officer can approve; approval resolves the complaint
# ---------------------------------------------------------------------------

def test_chief_officer_can_approve_and_resolves_complaint(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    submit_res = _submit_review(client, complaint_id, officer_token)
    assert submit_res.status_code == 201
    review_id = submit_res.get_json()["review"]["id"]

    # Test 8: Chief Officer can approve
    decide_res = _decide(client, review_id, chief_token, "Approved")
    assert decide_res.status_code == 200, decide_res.get_json()
    body = decide_res.get_json()

    # Test 9: Complaint is now Resolved
    assert body["complaint"]["status"] == "Resolved"
    assert body["review"]["decision"] == "Approved"

    with app.app_context():
        c = Complaint.query.get(complaint_id)
        assert c.status == "Resolved"


# ---------------------------------------------------------------------------
# Test 10: Reviewer identity and timestamp come from the server
# ---------------------------------------------------------------------------

def test_reviewer_identity_and_timestamp_are_server_generated(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    submit_res = _submit_review(client, complaint_id, officer_token)
    review_id = submit_res.get_json()["review"]["id"]

    decide_res = _decide(client, review_id, chief_token, "Approved")
    assert decide_res.status_code == 200
    review = decide_res.get_json()["review"]

    # reviewed_by must match chief_officer_user.id (set from JWT, not body)
    assert review["reviewed_by"] == chief_officer_user.id
    assert review["reviewer_name"] == chief_officer_user.name

    # reviewed_at must be a valid timestamp
    assert review["reviewed_at"] is not None
    parsed = datetime.fromisoformat(review["reviewed_at"])
    assert parsed is not None


# ---------------------------------------------------------------------------
# Test 11: Submitting Officer cannot approve their own request
# ---------------------------------------------------------------------------

def test_submitting_officer_cannot_approve_own_request(client, app, citizen_user, officer_user, chief_officer_user):
    """The submitting officer must not be able to approve their own request,
    even if they hold Chief Officer privileges."""
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")

    # Use the chief_officer_user (a separate user) to submit, then try to
    # approve with the same user — simulate by creating a second chief officer.
    with app.app_context():
        from models.user import User
        from services.auth_service import hash_password
        self_reviewer = User(
            name="Self Reviewing Chief",
            email="selfreview@example.com",
            password_hash=hash_password("selfreview123"),
            role="Chief Officer",
        )
        db.session.add(self_reviewer)
        db.session.commit()
        self_reviewer_id = self_reviewer.id

    self_token = get_token(client, "selfreview@example.com", "selfreview123")

    # Submit the review as self_reviewer (a Chief Officer submitting as if Officer;
    # Chief Officer is not Officer role, so we do it as the officer_user)
    submit_res = _submit_review(client, complaint_id, officer_token)
    assert submit_res.status_code == 201
    review_id = submit_res.get_json()["review"]["id"]

    # Force-update the review's submitted_by to match self_reviewer to simulate
    # "same user submitted and is trying to approve"
    with app.app_context():
        rv = ResolutionReview.query.get(review_id)
        rv.submitted_by = self_reviewer_id
        db.session.commit()

    # Now self_reviewer tries to approve their own submission
    decide_res = _decide(client, review_id, self_token, "Approved")
    assert decide_res.status_code == 403


# ---------------------------------------------------------------------------
# Test 12: Chief Officer can reject with a reason
# ---------------------------------------------------------------------------

def test_chief_officer_can_reject_with_reason(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    submit_res = _submit_review(client, complaint_id, officer_token)
    assert submit_res.status_code == 201
    review_id = submit_res.get_json()["review"]["id"]

    decide_res = _decide(client, review_id, chief_token, "Rejected",
                         rejection_note="Evidence photo is insufficient. Please retake.")
    assert decide_res.status_code == 200
    body = decide_res.get_json()
    assert body["review"]["decision"] == "Rejected"
    assert body["review"]["rejection_note"] == "Evidence photo is insufficient. Please retake."


# ---------------------------------------------------------------------------
# Test 13: Rejection leaves the complaint unresolved
# ---------------------------------------------------------------------------

def test_rejection_leaves_complaint_unresolved(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    _submit_review(client, complaint_id, officer_token)
    review_id = ResolutionReview.query.filter_by(complaint_id=complaint_id).first().id

    decide_res = _decide(client, review_id, chief_token, "Rejected",
                         rejection_note="Not enough evidence.")
    assert decide_res.status_code == 200
    assert decide_res.get_json()["complaint"]["status"] != "Resolved"
    assert decide_res.get_json()["complaint"]["status"] == "In Progress"

    with app.app_context():
        c = Complaint.query.get(complaint_id)
        assert c.status == "In Progress"
        assert c.status != "Resolved"


# ---------------------------------------------------------------------------
# Test 14: Rejection reason is visible to the Officer via GET
# ---------------------------------------------------------------------------

def test_rejection_reason_visible_to_officer(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    _submit_review(client, complaint_id, officer_token)
    review_id = ResolutionReview.query.filter_by(complaint_id=complaint_id).first().id
    _decide(client, review_id, chief_token, "Rejected", rejection_note="Blurry photo.")

    get_res = client.get(
        f"/api/officers/complaints/{complaint_id}/resolution-review",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert get_res.status_code == 200
    review = get_res.get_json()["review"]
    assert review["decision"] == "Rejected"
    assert review["rejection_note"] == "Blurry photo."


# ---------------------------------------------------------------------------
# Test 15: Officer can submit corrected evidence after rejection
# ---------------------------------------------------------------------------

def test_officer_can_resubmit_after_rejection(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    # Initial submission
    res1 = _submit_review(client, complaint_id, officer_token)
    assert res1.status_code == 201
    review_id1 = res1.get_json()["review"]["id"]

    # Chief Officer rejects
    _decide(client, review_id1, chief_token, "Rejected", rejection_note="Retake photo.")

    # Officer re-submits corrected evidence
    res2 = _submit_review(client, complaint_id, officer_token,
                          completion_note="Corrected evidence provided.")
    assert res2.status_code == 201, res2.get_json()
    review_id2 = res2.get_json()["review"]["id"]
    assert review_id2 != review_id1
    assert res2.get_json()["review"]["completion_note"] == "Corrected evidence provided."


# ---------------------------------------------------------------------------
# Test 16: A request cannot be approved twice
# ---------------------------------------------------------------------------

def test_request_cannot_be_approved_twice(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    submit_res = _submit_review(client, complaint_id, officer_token)
    review_id = submit_res.get_json()["review"]["id"]

    # First approval
    res1 = _decide(client, review_id, chief_token, "Approved")
    assert res1.status_code == 200

    # Second approval on the same review — must be blocked
    res2 = _decide(client, review_id, chief_token, "Approved")
    assert res2.status_code == 400
    assert "already been decided" in res2.get_json()["message"].lower()


# ---------------------------------------------------------------------------
# Test 17: Ordinary work updates cannot bypass the review process
# ---------------------------------------------------------------------------

def test_ordinary_work_update_cannot_bypass_review(client, app, citizen_user, officer_user, chief_officer_user):
    """After a resolution review is submitted (status='Pending Review'),
    a plain work update with status='Resolved' must still be rejected.
    The complaint can only reach 'Resolved' via Chief Officer approval."""
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")

    # Advance complaint to Pending Review
    _submit_review(client, complaint_id, officer_token)

    # Attempt ordinary work update with Resolved — must be rejected
    res = client.post(
        f"/api/officers/complaints/{complaint_id}/work-updates",
        data={"status": "Resolved", "note": "Trying to bypass review."},
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["message"] == "Invalid status"
    assert "Resolved" not in body["allowed_statuses"]


# ---------------------------------------------------------------------------
# Test: Rejection requires a rejection_note
# ---------------------------------------------------------------------------

def test_rejection_without_reason_returns_400(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    _submit_review(client, complaint_id, officer_token)
    review_id = ResolutionReview.query.filter_by(complaint_id=complaint_id).first().id

    res = _decide(client, review_id, chief_token, "Rejected")  # no rejection_note
    assert res.status_code == 400
    assert "rejection note" in res.get_json()["message"].lower()


# ---------------------------------------------------------------------------
# Test: Chief Officer queue returns pending reviews
# ---------------------------------------------------------------------------

def test_chief_officer_can_view_queue(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")
    chief_token = get_token(client, "chief@example.com", "chief123")

    _submit_review(client, complaint_id, officer_token)

    res = client.get(
        "/api/chief-officer/resolution-queue",
        headers={"Authorization": f"Bearer {chief_token}"},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["total"] >= 1
    assert any(item["review"]["complaint_id"] == complaint_id for item in body["queue"])


# ---------------------------------------------------------------------------
# Test: Officer cannot view Chief Officer queue
# ---------------------------------------------------------------------------

def test_officer_cannot_view_chief_officer_queue(client, app, citizen_user, officer_user, chief_officer_user):
    officer_token = get_token(client, "officer@example.com", "officer123")
    res = client.get(
        "/api/chief-officer/resolution-queue",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Test: Citizen cannot view resolution review GET endpoint
# ---------------------------------------------------------------------------

def test_citizen_cannot_view_resolution_review(client, app, citizen_user, officer_user, chief_officer_user):
    complaint_id = _make_complaint(app, citizen_user)
    citizen_token = get_token(client, "citizen@example.com", "password123")

    res = client.get(
        f"/api/officers/complaints/{complaint_id}/resolution-review",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Test: Duplicate pending review is blocked
# ---------------------------------------------------------------------------

def test_duplicate_pending_review_is_blocked(client, app, citizen_user, officer_user, chief_officer_user):
    """An Officer must not be able to submit a second resolution request while
    the first is still pending Chief Officer review."""
    complaint_id = _make_complaint(app, citizen_user)
    officer_token = get_token(client, "officer@example.com", "officer123")

    res1 = _submit_review(client, complaint_id, officer_token)
    assert res1.status_code == 201

    res2 = _submit_review(client, complaint_id, officer_token)
    assert res2.status_code == 400
    assert "already pending" in res2.get_json()["message"].lower()
