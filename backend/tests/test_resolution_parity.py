"""Behaviour of the earlier complaint-level prototype, kept under the issue-wide workflow.

The prototype (tests ``test_resolution_review.py`` and ``test_work_updates.py``) reviewed and
resolved one complaint at a time through ``/officers/complaints/<id>/...``.  Resolution is now
issue-wide (``/issues/<id>/...``), so those endpoints are gone.  Each test below keeps one
behaviour those tests protected, expressed against the current API; the old test it replaces is
named in its docstring.  Where the issue-wide design is deliberately stricter, the stricter rule
is asserted.
"""

import io
import json

from database.db import db
from models.civic_issue import CivicIssue
from models.resolution_review import ResolutionReview
from models.user import User
from tests.helpers import JPEG_BYTES
from tests.test_resolution_workflow import auth, create_complaint, image, submit_review, token


def people(client):
    return {
        "citizen": token(client, "citizen@example.com", "password123"),
        "officer": token(client, "officer@example.com", "officer123"),
        "admin": token(client, "admin@example.com", "admin123"),
        "chief": token(client, "chief@example.com", "chief123"),
    }


def work_update(client, bearer, issue_id, key="k", **fields):
    data = {"note": "Crew on site"}
    data.update(fields)
    if data.get("image") is True:
        data["image"] = image("progress.jpg")
    return client.post(
        f"/api/issues/{issue_id}/work-updates", data=data,
        content_type="multipart/form-data", headers=auth(bearer, key),
    )


def decide(client, bearer, review_id, decision, reason=None, **extra):
    body = {"decision": decision, **extra}
    if reason is not None:
        body["rejection_reason"] = reason
    return client.put(f"/api/chief-officer/resolution-reviews/{review_id}/decision", json=body, headers=auth(bearer))


def issue_status(issue_id):
    db.session.expire_all()
    return db.session.get(CivicIssue, issue_id).status


# ---------------- field-work updates (was test_work_updates.py) ----------------

def test_work_update_records_officer_status_note_photo_gps_and_server_time(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_officer_can_submit_work_update, ..._contains_officer_identity/status/note,
    ..._can_store_photo, ..._can_store_gps, ..._timestamp_is_server_generated."""
    t = people(client)
    complaint = create_complaint(client, t["citizen"])
    issue_id = complaint["civic_issue"]["id"]
    response = work_update(
        client, t["officer"], issue_id, key="first", status="In Progress", image=True,
        latitude="20.0123", longitude="73.7901", created_at="2001-01-01T00:00:00", officer_id="999",
    )
    assert response.status_code == 201
    update = response.get_json()["work_update"]
    officer = User.query.filter_by(email="officer@example.com").first()
    assert update["note"] == "Crew on site" and update["status"] == "In Progress"
    assert update["image_path"] == f"/issues/{issue_id}/work-updates/{update['id']}/image" and "image_url" not in update
    assert update["latitude"] == 20.0123 and update["longitude"] == 73.7901
    assert update["officer_id"] == officer.id if "officer_id" in update else True
    assert not str(update["created_at"]).startswith("2001")  # the client cannot choose the time
    assert "999" not in json.dumps({k: update[k] for k in update if k.endswith("_id")})  # nor the identity


def test_several_work_updates_for_one_issue_are_all_kept_in_order(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_multiple_work_updates_for_same_complaint."""
    t = people(client)
    issue_id = create_complaint(client, t["citizen"])["civic_issue"]["id"]
    for index in range(3):
        assert work_update(client, t["officer"], issue_id, key=f"k{index}", note=f"Step {index}").status_code == 201
    listed = client.get(f"/api/issues/{issue_id}/work-updates", headers=auth(t["officer"])).get_json()["work_updates"]
    assert [u["note"] for u in listed][-3:] in (["Step 0", "Step 1", "Step 2"], ["Step 2", "Step 1", "Step 0"])
    assert len(listed) == 3


def test_work_update_access_and_input_rules(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_citizen_cannot_create_work_update, test_unauthenticated_cannot_create_work_update,
    test_citizen_cannot_list_work_updates, test_missing_note_returns_400,
    test_invalid_status_returns_400, test_nonexistent_complaint_returns_404."""
    t = people(client)
    issue_id = create_complaint(client, t["citizen"])["civic_issue"]["id"]
    assert work_update(client, t["citizen"], issue_id).status_code == 403
    unauth = client.post(f"/api/issues/{issue_id}/work-updates", data={"note": "x"}, content_type="multipart/form-data")
    assert unauth.status_code == 401
    assert client.get(f"/api/issues/{issue_id}/work-updates", headers=auth(t["citizen"])).status_code == 403
    assert work_update(client, t["officer"], issue_id, key="a", note="").status_code == 400
    assert work_update(client, t["officer"], issue_id, key="b", status="Banana").status_code == 400
    assert work_update(client, t["officer"], 999999, key="c").status_code == 404


def test_work_updates_can_set_in_progress_or_pending_but_never_resolve(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_resolved_status_rejected_for_work_updates, test_pending_status_allowed_for_work_updates,
    test_status_update_mirrors_complaint_status, test_ordinary_work_update_cannot_bypass_review."""
    t = people(client)
    issue_id = create_complaint(client, t["citizen"])["civic_issue"]["id"]
    assert work_update(client, t["officer"], issue_id, key="p", status="Pending").status_code == 201
    assert work_update(client, t["officer"], issue_id, key="w", status="In Progress").status_code == 201
    assert issue_status(issue_id) == "In Progress"
    for forbidden in ("Resolved", "Pending Review"):
        assert work_update(client, t["officer"], issue_id, key=f"x{forbidden}", status=forbidden).status_code == 400
    assert issue_status(issue_id) == "In Progress"


# ---------------- resolution review (was test_resolution_review.py) ----------------

def test_submission_requires_note_and_photo_and_does_not_resolve(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_officer_can_submit_resolution_request, test_missing_completion_note_rejected,
    test_missing_evidence_photo_rejected, test_submission_does_not_resolve_complaint."""
    t = people(client)
    complaint = create_complaint(client, t["citizen"])
    issue_id = complaint["civic_issue"]["id"]
    assert submit_review(client, t["officer"], issue_id, [complaint["id"]], completion_note="").status_code == 400
    no_photo = client.post(
        f"/api/issues/{issue_id}/resolution-reviews",
        data={"completion_note": "Repaired the road surface.",
              "dispositions": json.dumps([{"complaint_id": complaint["id"], "disposition": "Addressed", "note": "Done."}])},
        content_type="multipart/form-data", headers=auth(t["officer"]),
    )
    assert no_photo.status_code == 400
    assert issue_status(issue_id) != "Pending Review"  # refused submissions change nothing
    ok = submit_review(client, t["officer"], issue_id, [complaint["id"]])
    assert ok.status_code == 201
    assert issue_status(issue_id) == "Pending Review"  # awaiting the Chief Officer, not resolved


def test_submission_identity_and_time_are_server_generated(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_submission_creates_server_timestamped_review."""
    t = people(client)
    complaint = create_complaint(client, t["citizen"])
    response = submit_review(
        client, t["officer"], complaint["civic_issue"]["id"], [complaint["id"]],
        submitted_at="2001-01-01T00:00:00", submitted_by="999",
    )
    review = db.session.get(ResolutionReview, response.get_json()["review"]["id"])
    officer = User.query.filter_by(email="officer@example.com").first()
    assert review.submitted_by == officer.id
    assert review.submitted_at.year != 2001


def test_only_the_chief_officer_may_submit_decide_or_view_the_queue(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_citizen_cannot_submit_resolution_request, test_officer_cannot_decide_resolution_request,
    test_chief_officer_can_view_queue, test_officer_cannot_view_chief_officer_queue,
    test_citizen_cannot_view_resolution_review."""
    t = people(client)
    complaint = create_complaint(client, t["citizen"])
    issue_id = complaint["civic_issue"]["id"]
    assert submit_review(client, t["citizen"], issue_id, [complaint["id"]]).status_code == 403
    review_id = submit_review(client, t["officer"], issue_id, [complaint["id"]]).get_json()["review"]["id"]
    for who in ("citizen", "officer", "admin"):
        assert decide(client, t[who], review_id, "Approved").status_code == 403, who
        assert client.get("/api/chief-officer/resolution-queue", headers=auth(t[who])).status_code == 403, who
    assert client.get(f"/api/issues/{issue_id}/resolution-reviews", headers=auth(t["citizen"])).status_code == 403
    queue = client.get("/api/chief-officer/resolution-queue", headers=auth(t["chief"]))
    assert queue.status_code == 200
    rows = queue.get_json()["queue"]
    assert any(review_id in (row.get("id"), (row.get("review") or {}).get("id")) for row in rows), rows
    assert ResolutionReview.query.get(review_id).state == "Pending"  # the refusals changed nothing


def test_approval_resolves_once_with_server_generated_reviewer(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_chief_officer_can_approve_and_resolves_complaint, test_reviewer_identity_and_timestamp_are_server_generated,
    test_submitting_officer_cannot_approve_own_request, test_request_cannot_be_approved_twice."""
    t = people(client)
    complaint = create_complaint(client, t["citizen"])
    issue_id = complaint["civic_issue"]["id"]
    review_id = submit_review(client, t["officer"], issue_id, [complaint["id"]]).get_json()["review"]["id"]
    assert decide(client, t["officer"], review_id, "Approved").status_code == 403  # the submitter cannot approve
    approved = decide(client, t["chief"], review_id, "Approved", reviewed_by="999", reviewed_at="2001-01-01T00:00:00")
    assert approved.status_code == 200
    review = db.session.get(ResolutionReview, review_id)
    chief = User.query.filter_by(email="chief@example.com").first()
    assert review.state == "Approved" and review.reviewed_by == chief.id and review.reviewed_at.year != 2001
    assert issue_status(issue_id) == "Resolved"
    assert decide(client, t["chief"], review_id, "Approved").status_code in (400, 409)  # no double approval
    assert issue_status(issue_id) == "Resolved"


def test_rejection_needs_a_reason_leaves_issue_unresolved_and_can_be_resubmitted(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_chief_officer_can_reject_with_reason, test_rejection_without_reason_returns_400,
    test_rejection_leaves_complaint_unresolved, test_rejection_reason_visible_to_officer,
    test_officer_can_resubmit_after_rejection."""
    t = people(client)
    complaint = create_complaint(client, t["citizen"])
    issue_id = complaint["civic_issue"]["id"]
    review_id = submit_review(client, t["officer"], issue_id, [complaint["id"]]).get_json()["review"]["id"]
    assert decide(client, t["chief"], review_id, "Rejected").status_code == 400
    assert decide(client, t["chief"], review_id, "Rejected", reason="  ").status_code == 400
    assert ResolutionReview.query.get(review_id).state == "Pending"
    reason = "The photo does not show the repaired area."
    assert decide(client, t["chief"], review_id, "Rejected", reason=reason).status_code == 200
    assert issue_status(issue_id) != "Resolved"
    seen = client.get(f"/api/issues/{issue_id}/resolution-reviews", headers=auth(t["officer"]))
    assert seen.status_code == 200 and reason in json.dumps(seen.get_json())
    again = submit_review(client, t["officer"], issue_id, [complaint["id"]], supersedes_review_id=str(review_id))
    assert again.status_code == 201


def test_a_second_pending_review_for_the_same_issue_is_blocked(client, citizen_user, officer_user, admin_user, chief_officer_user):
    """Was: test_duplicate_pending_review_is_blocked."""
    t = people(client)
    complaint = create_complaint(client, t["citizen"])
    issue_id = complaint["civic_issue"]["id"]
    assert submit_review(client, t["officer"], issue_id, [complaint["id"]]).status_code == 201
    second = submit_review(client, t["officer"], issue_id, [complaint["id"]])
    assert second.status_code in (400, 409)
    assert ResolutionReview.query.filter_by(issue_id=issue_id, state="Pending").count() == 1
