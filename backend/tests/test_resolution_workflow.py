import io
import json
from unittest.mock import patch

from database.db import db
from models.civic_issue import CivicIssue
from models.community import CivicIssueStatusChange, ImpactScoreEvent
from models.notification import Notification
from models.resolution_review import ResolutionReview
from tests.helpers import JPEG_BYTES


AI_RESULT = {
    "category": "Road Infrastructure",
    "priority": "High",
    "department": "Roads Dept",
    "visual_observation": "Pothole in the road",
    "summary": "Large pothole blocking traffic",
    "spam_flag": False,
    "spam_reason": "",
    "spam_confidence": "",
}
PENDING_SPAM_RESULT = dict(
    AI_RESULT,
    spam_flag=True,
    spam_reason="Photo needs human moderation",
    spam_confidence="Medium",
)


def token(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    return response.get_json()["token"]


def auth(value, key=None):
    headers = {"Authorization": f"Bearer {value}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


def image(name="evidence.jpg", payload=JPEG_BYTES):
    return io.BytesIO(payload), name


def create_complaint(client, citizen_token, ai_result=AI_RESULT, latitude="20.011", longitude="73.790", title="Pothole"):
    with patch("routes.complaints.analyze_complaint", return_value=ai_result):
        response = client.post(
            "/api/complaints/",
            data={
                "title": title,
                "description": ai_result["summary"],
                "latitude": latitude,
                "longitude": longitude,
                "image": image("report.jpg"),
            },
            content_type="multipart/form-data",
            headers=auth(citizen_token),
        )
    assert response.status_code == 201
    return response.get_json()["complaint"]


def submit_review(client, officer_token, issue_id, complaint_ids, **extra):
    dispositions = extra.pop("dispositions", [
        {"complaint_id": complaint_id, "disposition": "Addressed", "note": "Repair covers this report."}
        for complaint_id in complaint_ids
    ])
    data = {
        "completion_note": "Crew repaired the road and checked every reported location.",
        "dispositions": json.dumps(dispositions),
        "image": image("final.jpg"),
    }
    data.update(extra)
    return client.post(
        f"/api/issues/{issue_id}/resolution-reviews",
        data=data,
        content_type="multipart/form-data",
        headers=auth(officer_token),
    )


def promote_to_officer(client, admin_token, email, password):
    register = client.post("/api/auth/register", json={
        "name": "Second Officer", "email": email, "password": password,
    })
    user_id = register.get_json()["user"]["id"]
    response = client.put(
        f"/api/admin/users/{user_id}/role", json={"role": "Officer"}, headers=auth(admin_token)
    )
    assert response.status_code == 200
    return token(client, email, password)


def test_work_updates_validate_same_issue_gps_and_idempotency(client, citizen_user, officer_user, admin_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    admin_token = token(client, "admin@example.com", "admin123")
    first = create_complaint(client, citizen_token)
    other = create_complaint(client, citizen_token, latitude="20.050", title="Other pothole")
    issue_id = first["civic_issue"]["id"]

    cross_issue = client.post(
        f"/api/issues/{issue_id}/work-updates",
        data={"note": "Wrong complaint", "complaint_id": str(other["id"])},
        content_type="multipart/form-data",
        headers=auth(officer_token, "cross-issue"),
    )
    assert cross_issue.status_code == 400

    partial_gps = client.post(
        f"/api/issues/{issue_id}/work-updates",
        data={"note": "GPS partial", "latitude": "20.0"},
        content_type="multipart/form-data",
        headers=auth(officer_token, "partial-gps"),
    )
    assert partial_gps.status_code == 400

    payload = {"note": "Crew began work", "complaint_id": str(first["id"]), "status": "In Progress"}
    first_response = client.post(
        f"/api/issues/{issue_id}/work-updates", data=payload,
        content_type="multipart/form-data", headers=auth(officer_token, "same-key"),
    )
    assert first_response.status_code == 201
    update_id = first_response.get_json()["work_update"]["id"]

    repeat = client.post(
        f"/api/issues/{issue_id}/work-updates", data=payload,
        content_type="multipart/form-data", headers=auth(officer_token, "same-key"),
    )
    assert repeat.status_code == 200
    assert repeat.get_json()["work_update"]["id"] == update_id

    conflict = client.post(
        f"/api/issues/{issue_id}/work-updates", data={"note": "Different payload"},
        content_type="multipart/form-data", headers=auth(officer_token, "same-key"),
    )
    assert conflict.status_code == 409

    second_officer = promote_to_officer(client, admin_token, "second-officer@example.com", "second123")
    second = client.post(
        f"/api/issues/{issue_id}/work-updates", data={"note": "Second officer update"},
        content_type="multipart/form-data", headers=auth(second_officer, "same-key"),
    )
    assert second.status_code == 201


def test_review_submission_blocks_pending_moderation_and_cross_issue_dispositions(client, citizen_user, officer_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    flagged = create_complaint(client, citizen_token, PENDING_SPAM_RESULT)
    flagged_issue_id = flagged["civic_issue"]["id"]
    blocked = submit_review(client, officer_token, flagged_issue_id, [])
    assert blocked.status_code == 400
    assert "moderation" in blocked.get_json()["message"].lower()

    first = create_complaint(client, citizen_token, latitude="20.020", title="Eligible pothole")
    other = create_complaint(client, citizen_token, latitude="20.060", title="Other issue")
    response = submit_review(
        client, officer_token, first["civic_issue"]["id"], [],
        dispositions=[{
            "complaint_id": other["id"], "disposition": "Addressed", "note": "Wrong issue"}],
    )
    assert response.status_code == 400
    assert "does not belong" in response.get_json()["message"]


def test_stale_review_is_preserved_after_new_linked_complaint(client, citizen_user, officer_user, chief_officer_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    chief_token = token(client, "chief@example.com", "chief123")
    first = create_complaint(client, citizen_token)
    issue_id = first["civic_issue"]["id"]
    submitted = submit_review(client, officer_token, issue_id, [first["id"]])
    assert submitted.status_code == 201
    review_id = submitted.get_json()["review"]["id"]

    second = create_complaint(client, citizen_token, latitude="20.0111", longitude="73.7901", title="Same pothole")
    assert second["civic_issue"]["id"] == issue_id
    review = ResolutionReview.query.get(review_id)
    assert review.state == "Stale"
    assert review.stale_reason

    decision = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Approved"}, headers=auth(chief_token),
    )
    assert decision.status_code == 409


def test_only_chief_officer_can_decide_and_approval_is_issue_wide_once(client, citizen_user, officer_user, admin_user, chief_officer_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    admin_token = token(client, "admin@example.com", "admin123")
    chief_token = token(client, "chief@example.com", "chief123")
    first = create_complaint(client, citizen_token)
    issue_id = first["civic_issue"]["id"]
    submitted = submit_review(client, officer_token, issue_id, [first["id"]])
    review_id = submitted.get_json()["review"]["id"]

    assert client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Approved"}, headers=auth(admin_token),
    ).status_code == 403

    approved = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Approved"}, headers=auth(chief_token),
    )
    assert approved.status_code == 200
    complaint = client.get(f"/api/complaints/{first['id']}", headers=auth(citizen_token)).get_json()["complaint"]
    assert complaint["status"] == "Resolved"
    assert complaint["civic_issue"]["status"] == "Resolved"

    reward_events = ImpactScoreEvent.query.filter_by(event_type="ISSUE_RESOLVED").count()
    notification_count = Notification.query.filter_by(user_id=citizen_user.id).count()
    duplicate = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Approved"}, headers=auth(chief_token),
    )
    assert duplicate.status_code == 409
    assert ImpactScoreEvent.query.filter_by(event_type="ISSUE_RESOLVED").count() == reward_events
    assert Notification.query.filter_by(user_id=citizen_user.id).count() == notification_count
    assert CivicIssueStatusChange.query.filter_by(civic_issue_id=issue_id, new_status="Resolved").count() == 1


def test_rejection_and_supersession_preserve_review_history(client, citizen_user, officer_user, chief_officer_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    chief_token = token(client, "chief@example.com", "chief123")
    complaint = create_complaint(client, citizen_token)
    issue_id = complaint["civic_issue"]["id"]
    first = submit_review(client, officer_token, issue_id, [complaint["id"]])
    review_id = first.get_json()["review"]["id"]

    too_short = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Rejected", "rejection_reason": "No"}, headers=auth(chief_token),
    )
    assert too_short.status_code == 400
    rejected = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Rejected", "rejection_reason": "Please add clearer final evidence."}, headers=auth(chief_token),
    )
    assert rejected.status_code == 200
    assert ResolutionReview.query.get(review_id).state == "Rejected"

    replacement = submit_review(
        client, officer_token, issue_id, [complaint["id"]], supersedes_review_id=str(review_id)
    )
    assert replacement.status_code == 201
    assert replacement.get_json()["review"]["supersedes_review_id"] == review_id


def test_self_review_and_direct_resolution_bypass_are_blocked(client, citizen_user, officer_user, admin_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    admin_token = token(client, "admin@example.com", "admin123")
    complaint = create_complaint(client, citizen_token)
    issue_id = complaint["civic_issue"]["id"]
    review = submit_review(client, officer_token, issue_id, [complaint["id"]])
    review_id = review.get_json()["review"]["id"]

    direct_complaint = client.put(
        f"/api/complaints/{complaint['id']}/status", json={"status": "Resolved"}, headers=auth(officer_token)
    )
    direct_issue = client.put(
        f"/api/officers/issues/{issue_id}/status", json={"status": "Resolved"}, headers=auth(officer_token)
    )
    assert direct_complaint.status_code == 400
    assert direct_issue.status_code == 400

    promoted = client.put(
        f"/api/admin/users/{officer_user.id}/role", json={"role": "Chief Officer"}, headers=auth(admin_token)
    )
    assert promoted.status_code == 200
    same_user_chief_token = token(client, "officer@example.com", "officer123")
    self_review = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Approved"}, headers=auth(same_user_chief_token),
    )
    assert self_review.status_code == 403


def test_blank_coordinates_are_rejected_not_a_server_error(client, citizen_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    for extra in ({}, {"address": "Main Street"}):
        with patch("routes.complaints.analyze_complaint", return_value=AI_RESULT):
            response = client.post(
                "/api/complaints/",
                data={
                    "title": "Pothole", "description": "Large pothole",
                    "latitude": "", "longitude": "", "image": image("report.jpg"), **extra,
                },
                content_type="multipart/form-data",
                headers=auth(citizen_token),
            )
        assert response.status_code == 400


def test_returning_issue_to_field_work_withdraws_the_pending_review(
    client, citizen_user, officer_user, chief_officer_user
):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    chief_token = token(client, "chief@example.com", "chief123")
    complaint = create_complaint(client, citizen_token)
    issue_id = complaint["civic_issue"]["id"]
    review_id = submit_review(client, officer_token, issue_id, [complaint["id"]]).get_json()["review"]["id"]

    returned = client.put(
        f"/api/officers/issues/{issue_id}/status",
        json={"status": "In Progress"}, headers=auth(officer_token),
    )
    assert returned.status_code == 200

    review = ResolutionReview.query.get(review_id)
    assert review.state == "Stale"
    assert review.stale_reason
    assert client.get("/api/chief-officer/resolution-queue", headers=auth(chief_token)).get_json()["queue"] == []
    decision = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Approved"}, headers=auth(chief_token),
    )
    assert decision.status_code == 409
    assert CivicIssue.query.get(issue_id).status == "In Progress"


def test_stale_review_stays_visible_to_chief_officer_and_cannot_be_approved(
    client, citizen_user, officer_user, chief_officer_user
):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    chief_token = token(client, "chief@example.com", "chief123")
    first = create_complaint(client, citizen_token)
    issue_id = first["civic_issue"]["id"]
    review_id = submit_review(client, officer_token, issue_id, [first["id"]]).get_json()["review"]["id"]
    notifications_before = Notification.query.count()

    create_complaint(client, citizen_token, latitude="20.0111", longitude="73.7901", title="Same pothole")

    # The issue is not silently moved on: no status change, no new history row.
    assert CivicIssue.query.get(issue_id).status == "Pending Review"
    assert [(c.old_status, c.new_status) for c in CivicIssueStatusChange.query.filter_by(civic_issue_id=issue_id)] == [
        ("Pending", "Pending Review"),
    ]

    queue = client.get("/api/chief-officer/resolution-queue", headers=auth(chief_token)).get_json()
    assert queue["queue"] == []
    assert len(queue["stale"]) == 1
    entry = queue["stale"][0]
    assert entry["issue"]["id"] == issue_id
    assert entry["issue"]["status"] == "Pending Review"
    assert entry["review"]["id"] == review_id
    assert entry["review"]["state"] == "Stale"
    assert entry["review"]["stale_reason"]
    assert entry["review"]["stale_at"]
    assert len(entry["complaints"]) == 2

    decision = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Approved"}, headers=auth(chief_token),
    )
    assert decision.status_code == 409
    assert CivicIssue.query.get(issue_id).status == "Pending Review"

    # Original evidence and dispositions survive; the staff history shows the reason.
    history = client.get(f"/api/issues/{issue_id}/resolution-reviews", headers=auth(chief_token)).get_json()
    assert history["reviews"][0]["state"] == "Stale"
    assert history["reviews"][0]["stale_reason"]
    assert len(history["reviews"][0]["dispositions"]) == 1
    # Going stale itself notifies nobody about a status change.
    assert not [
        n for n in Notification.query.all()[notifications_before:]
        if "officially" in n.message or "started work" in n.message
    ]

    # Citizens and ordinary officers never see the chief queue.
    assert client.get("/api/chief-officer/resolution-queue", headers=auth(officer_token)).status_code == 403

    # Resubmitting covers both complaints and moves the review back to Pending.
    all_ids = [row["id"] for row in history["complaints"]]
    resubmitted = submit_review(client, officer_token, issue_id, all_ids, supersedes_review_id=str(review_id))
    assert resubmitted.status_code == 201
    queue = client.get("/api/chief-officer/resolution-queue", headers=auth(chief_token)).get_json()
    assert len(queue["queue"]) == 1
    assert queue["stale"] == []


def test_issue_with_only_excluded_complaints_cannot_be_submitted_for_review(
    client, citizen_user, officer_user, chief_officer_user
):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")

    spam = create_complaint(client, citizen_token, ai_result=PENDING_SPAM_RESULT)
    spam_issue = spam["civic_issue"]["id"]
    blocked = submit_review(client, officer_token, spam_issue, [])
    assert blocked.status_code == 400  # still awaiting moderation
    confirmed = client.put(
        f"/api/officers/spam/{spam['id']}/review",
        json={"decision": "Confirmed"}, headers=auth(officer_token),
    )
    assert confirmed.status_code == 200

    scope = create_complaint(client, citizen_token, latitude="20.5", longitude="73.9", title="Society light")
    scope_issue = scope["civic_issue"]["id"]
    rejected = client.put(
        f"/api/complaints/{scope['id']}/reject",
        json={"reason": "Private Property"}, headers=auth(officer_token),
    )
    assert rejected.status_code == 200

    for issue_id in (spam_issue, scope_issue):
        response = submit_review(client, officer_token, issue_id, [])
        assert response.status_code == 400
        assert "no eligible complaints" in response.get_json()["message"]
        assert ResolutionReview.query.filter_by(issue_id=issue_id).count() == 0
        assert CivicIssue.query.get(issue_id).status == "Pending"

    # The exclusion reasons stay visible to staff.
    context = client.get(f"/api/issues/{spam_issue}/resolution-reviews", headers=auth(officer_token)).get_json()
    assert context["review_checklist"] == [
        {"complaint_id": spam["id"], "eligible": False, "excluded_reason": "Confirmed spam", "blocked_reason": None},
    ]


def test_empty_review_cannot_be_approved_if_every_complaint_becomes_excluded(
    client, citizen_user, officer_user, chief_officer_user
):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    chief_token = token(client, "chief@example.com", "chief123")
    complaint = create_complaint(client, citizen_token)
    issue_id = complaint["civic_issue"]["id"]
    review_id = submit_review(client, officer_token, issue_id, [complaint["id"]]).get_json()["review"]["id"]

    # Simulate exclusion landing without a revision bump (e.g. a direct data
    # fix) so only the approval-time coverage check stands in the way.
    from database.db import db
    from models.complaint import Complaint
    Complaint.query.get(complaint["id"]).rejection_status = "Rejected"
    db.session.commit()

    decision = client.put(
        f"/api/chief-officer/resolution-reviews/{review_id}/decision",
        json={"decision": "Approved"}, headers=auth(chief_token),
    )
    assert decision.status_code == 409
    assert "no eligible complaints" in decision.get_json()["message"]
    assert CivicIssue.query.get(issue_id).status == "Pending Review"
    assert ResolutionReview.query.get(review_id).state == "Pending"


# ==========================================
# Concurrency: another request commits while approval/submission is in flight.
# A second SQLite connection stands in for the concurrent request.
# ==========================================

def _other_connection(timeout=0.2):
    import sqlite3
    return sqlite3.connect(db.engine.url.database, timeout=timeout)


def _commit_revision_bump(issue_id):
    other = _other_connection(timeout=5)
    try:
        other.execute("UPDATE civic_issues SET review_revision = review_revision + 1 WHERE id = ?", (issue_id,))
        other.commit()
    finally:
        other.close()


def _submitted_review(client, with_second_complaint=False):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    chief_token = token(client, "chief@example.com", "chief123")
    complaint = create_complaint(client, citizen_token)
    issue_id = complaint["civic_issue"]["id"]
    review_id = submit_review(client, officer_token, issue_id, [complaint["id"]]).get_json()["review"]["id"]
    return officer_token, chief_token, issue_id, review_id


def test_approval_holds_the_write_lock_before_validating_eligibility(
    client, citizen_user, officer_user, chief_officer_user
):
    import sqlite3
    from services import resolution_workflow

    _, chief_token, issue_id, review_id = _submitted_review(client)
    original = resolution_workflow.eligible_complaints
    attempts = []

    def probe(issue_id_arg):
        # Validation is running: no other connection may commit a change now.
        try:
            other = _other_connection()
            other.execute("UPDATE civic_issues SET review_revision = review_revision + 1 WHERE id = ?", (issue_id_arg,))
            other.commit()
            other.close()
            attempts.append("committed")
        except sqlite3.OperationalError:
            attempts.append("blocked")
        return original(issue_id_arg)

    with patch.object(resolution_workflow, "eligible_complaints", probe):
        decision = client.put(
            f"/api/chief-officer/resolution-reviews/{review_id}/decision",
            json={"decision": "Approved"}, headers=auth(chief_token),
        )
    assert attempts == ["blocked"]
    assert decision.status_code == 200
    assert CivicIssue.query.get(issue_id).status == "Resolved"


def test_revision_change_committed_just_before_approval_blocks_it(
    client, citizen_user, officer_user, chief_officer_user
):
    import routes.resolution_review as routes_module

    _, chief_token, issue_id, review_id = _submitted_review(client)
    real_approve = routes_module.approve_review
    rewards_before = ImpactScoreEvent.query.count()
    notices_before = Notification.query.count()

    def approve_after_concurrent_change(issue, review, chief_id):
        _commit_revision_bump(issue.id)  # lands after the route's own checks
        return real_approve(issue, review, chief_id)

    with patch.object(routes_module, "approve_review", approve_after_concurrent_change):
        decision = client.put(
            f"/api/chief-officer/resolution-reviews/{review_id}/decision",
            json={"decision": "Approved"}, headers=auth(chief_token),
        )
    assert decision.status_code == 409
    db.session.expire_all()
    assert CivicIssue.query.get(issue_id).status == "Pending Review"
    review = ResolutionReview.query.get(review_id)
    assert review.state == "Stale" and review.stale_reason and review.stale_at
    assert ImpactScoreEvent.query.count() == rewards_before
    assert Notification.query.count() == notices_before
    assert [c.new_status for c in CivicIssueStatusChange.query.filter_by(civic_issue_id=issue_id)] == ["Pending Review"]


def test_second_concurrent_approval_does_not_duplicate_side_effects(
    client, citizen_user, officer_user, chief_officer_user
):
    import routes.resolution_review as routes_module

    _, chief_token, issue_id, review_id = _submitted_review(client)
    real_approve = routes_module.approve_review
    url = f"/api/chief-officer/resolution-reviews/{review_id}/decision"
    inner = {}

    def approve_after_competing_approval(issue, review, chief_id):
        # Both requests passed the route's "still pending" check; the
        # competitor commits first.
        if not inner.get("started"):
            inner["started"] = True
            inner["response"] = client.put(url, json={"decision": "Approved"}, headers=auth(chief_token))
        return real_approve(issue, review, chief_id)

    with patch.object(routes_module, "approve_review", approve_after_competing_approval):
        outer = client.put(url, json={"decision": "Approved"}, headers=auth(chief_token))

    assert inner["response"].status_code == 200
    assert outer.status_code == 409
    db.session.expire_all()
    assert ImpactScoreEvent.query.filter_by(event_type="ISSUE_RESOLVED").count() == 1
    assert [c.new_status for c in CivicIssueStatusChange.query.filter_by(civic_issue_id=issue_id)] == [
        "Pending Review", "Resolved",
    ]
    assert Notification.query.filter(Notification.message.like("%officially marked Resolved%")).count() == 1
    assert ResolutionReview.query.get(review_id).state == "Approved"


def test_review_revision_bump_is_atomic_not_read_modify_write(app, citizen_user):
    from services.resolution_workflow import bump_review_revision

    issue = CivicIssue(category="Road Infrastructure", latitude=20.0, longitude=73.0, report_count=1)
    db.session.add(issue)
    db.session.commit()
    assert issue.review_revision == 1  # cached in this session

    other = _other_connection(timeout=5)
    other.execute("UPDATE civic_issues SET review_revision = 5 WHERE id = ?", (issue.id,))
    other.commit()
    other.close()

    bump_review_revision(issue, "Concurrent change")
    db.session.commit()
    db.session.expire_all()
    assert CivicIssue.query.get(issue.id).review_revision == 6


def test_submission_is_refused_if_issue_changed_after_eligibility_was_read(
    client, citizen_user, officer_user
):
    import os
    import routes.resolution_review as routes_module

    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    complaint = create_complaint(client, citizen_token)
    issue_id = complaint["civic_issue"]["id"]
    real_save = routes_module.save_upload
    upload_dir = client.application.config["UPLOAD_FOLDER"]
    files_before = set(os.listdir(upload_dir))

    def save_after_concurrent_change(*args, **kwargs):
        _commit_revision_bump(issue_id)  # e.g. a complaint linked meanwhile
        return real_save(*args, **kwargs)

    with patch.object(routes_module, "save_upload", save_after_concurrent_change):
        response = submit_review(client, officer_token, issue_id, [complaint["id"]])
    assert response.status_code == 409
    db.session.expire_all()
    assert ResolutionReview.query.filter_by(issue_id=issue_id).count() == 0
    assert CivicIssue.query.get(issue_id).status == "Pending"
    assert set(os.listdir(upload_dir)) == files_before


# ==========================================
# Complaint creation racing with resolution
# ==========================================

def _raw_execute(sql, params=()):
    other = _other_connection(timeout=5)
    try:
        other.execute(sql, params)
        other.commit()
    finally:
        other.close()


def _hook_after_first_match(after_match):
    """Wrap the clustering lookup so ``after_match(issue)`` runs once, after
    an open issue was chosen but before the complaint is linked to it."""
    import services.issue_clustering as clustering

    real = clustering.find_matching_issue
    state = {"fired": False}

    def wrapper(*args, **kwargs):
        issue = real(*args, **kwargs)
        if issue is not None and not state["fired"]:
            state["fired"] = True
            after_match(issue)
        return issue

    return patch.object(clustering, "find_matching_issue", wrapper)


def test_complaint_is_not_attached_to_an_issue_resolved_after_it_was_matched(
    client, citizen_user, officer_user
):
    from models.complaint import Complaint

    citizen_token = token(client, "citizen@example.com", "password123")
    first = create_complaint(client, citizen_token)
    issue_id = first["civic_issue"]["id"]
    revision_before = CivicIssue.query.get(issue_id).review_revision
    db.session.expire_all()

    def resolve_concurrently(issue):
        _raw_execute("UPDATE civic_issues SET status = 'Resolved' WHERE id = ?", (issue.id,))

    with _hook_after_first_match(resolve_concurrently):
        with patch("routes.complaints.analyze_complaint", return_value=AI_RESULT):
            response = client.post(
                "/api/complaints/",
                data={"title": "Same pothole", "description": AI_RESULT["summary"], "latitude": "20.0111",
                      "longitude": "73.7901", "image": image("report.jpg")},
                content_type="multipart/form-data", headers=auth(citizen_token),
            )

    assert response.status_code == 201
    new_complaint = response.get_json()["complaint"]
    db.session.expire_all()
    # Linked to a fresh open issue, never to the one that just resolved.
    assert new_complaint["civic_issue"]["id"] != issue_id
    assert Complaint.query.get(new_complaint["id"]).issue_id != issue_id
    resolved = CivicIssue.query.get(issue_id)
    assert resolved.status == "Resolved"
    assert resolved.report_count == 1
    assert resolved.review_revision == revision_before
    assert Complaint.query.filter_by(issue_id=issue_id).count() == 1
    assert CivicIssue.query.count() == 2
    assert CivicIssue.query.get(new_complaint["civic_issue"]["id"]).report_count == 1


def test_report_count_increment_is_not_lost_to_a_concurrent_complaint(client, citizen_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    first = create_complaint(client, citizen_token)
    issue_id = first["civic_issue"]["id"]
    db.session.expire_all()

    def another_complaint_counted(issue):
        _raw_execute("UPDATE civic_issues SET report_count = report_count + 1 WHERE id = ?", (issue.id,))

    with _hook_after_first_match(another_complaint_counted):
        with patch("routes.complaints.analyze_complaint", return_value=AI_RESULT):
            response = client.post(
                "/api/complaints/",
                data={"title": "Same pothole", "description": AI_RESULT["summary"], "latitude": "20.0111",
                      "longitude": "73.7901", "image": image("report.jpg")},
                content_type="multipart/form-data", headers=auth(citizen_token),
            )
    assert response.status_code == 201
    assert response.get_json()["complaint"]["civic_issue"]["id"] == issue_id
    db.session.expire_all()
    assert CivicIssue.query.get(issue_id).report_count == 3


def test_review_cannot_be_approved_after_a_complaint_is_linked_first(
    client, citizen_user, officer_user, chief_officer_user
):
    import routes.resolution_review as routes_module

    citizen_token = token(client, "citizen@example.com", "password123")
    _, chief_token, issue_id, review_id = _submitted_review(client)
    real_approve = routes_module.approve_review
    state = {}

    def approve_after_new_complaint(issue, review, chief_id):
        if not state.get("done"):
            state["done"] = True
            state["complaint"] = create_complaint(
                client, citizen_token, latitude="20.0111", longitude="73.7901", title="Same pothole"
            )
        return real_approve(issue, review, chief_id)

    with patch.object(routes_module, "approve_review", approve_after_new_complaint):
        decision = client.put(
            f"/api/chief-officer/resolution-reviews/{review_id}/decision",
            json={"decision": "Approved"}, headers=auth(chief_token),
        )
    assert state["complaint"]["civic_issue"]["id"] == issue_id
    assert decision.status_code == 409
    db.session.expire_all()
    assert CivicIssue.query.get(issue_id).status == "Pending Review"
    assert ResolutionReview.query.get(review_id).state == "Stale"
