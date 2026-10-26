"""Chief Officer supervision: overview, ratings, and corrective follow-ups."""

import io
import os
import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError

from database.db import db
from models.civic_issue import CivicIssue
from models.performance import FollowUpEvent, ResolutionFollowUp, ResolutionRating
from models.resolution_review import ResolutionReview
from models.user import User
from models.ward import Ward
from services.auth_service import hash_password
from tests.helpers import JPEG_BYTES
from tests.test_resolution_workflow import create_complaint, submit_review, token


def bearer(value):
    return {"Authorization": f"Bearer {value}"}


@pytest.fixture
def people(client, citizen_user, officer_user, admin_user, chief_officer_user):
    return {
        "citizen": token(client, "citizen@example.com", "password123"),
        "officer": token(client, "officer@example.com", "officer123"),
        "admin": token(client, "admin@example.com", "admin123"),
        "chief": token(client, "chief@example.com", "chief123"),
    }


@pytest.fixture
def second_officer(app):
    user = User(name="Second Officer", email="officer2@example.com",
                password_hash=hash_password("officer456"), role="Officer")
    db.session.add(user)
    db.session.commit()
    return user


def decide(client, chief, review_id, decision, reason=None):
    body = {"decision": decision}
    if reason:
        body["rejection_reason"] = reason
    return client.put(f"/api/chief-officer/resolution-reviews/{review_id}/decision", json=body, headers=bearer(chief))


def approved_job(client, people, latitude="20.011", longitude="73.790", title="Pothole", officer_token=None):
    """A complaint whose completed work was submitted by the officer and approved."""
    complaint = create_complaint(client, people["citizen"], latitude=latitude, longitude=longitude, title=title)
    review = submit_review(client, officer_token or people["officer"], complaint["civic_issue"]["id"],
                           [complaint["id"]]).get_json()["review"]
    assert decide(client, people["chief"], review["id"], "Approved").status_code == 200
    return complaint, review


def overview(client, chief, query=""):
    return client.get(f"/api/chief-officer/overview{query}", headers=bearer(chief))


# ==========================================
# Phase 1: overview
# ==========================================

def test_overview_is_chief_officer_only(client, people):
    assert overview(client, people["chief"]).status_code == 200
    for role in ("admin", "officer", "citizen"):
        assert overview(client, people[role]).status_code == 403, role
    assert client.get("/api/chief-officer/overview").status_code == 401
    # Existing Admin analytics stay Admin-only: the Chief Officer is not let in.
    assert client.get("/api/admin/analytics", headers=bearer(people["chief"])).status_code == 403
    assert client.get("/api/admin/analytics", headers=bearer(people["admin"])).status_code == 200


def test_empty_overview_reports_zero_and_marks_unavailable_data(client, people):
    data = overview(client, people["chief"]).get_json()
    assert data["scope"] == "municipality"
    assert data["wards"]["active_total"] == 0 and data["wards"]["items"] == []
    assert data["wards"]["work_by_ward"]["available"] is False
    assert data["issues"] == {"total": 0, "by_status": {"Pending": 0, "In Progress": 0, "Pending Review": 0, "Resolved": 0}}
    assert data["complaints"]["eligible_total"] == 0
    assert data["reviews"]["pending_decision"] == 0 and data["reviews"]["stale_awaiting_resubmission"] == 0
    assert data["resolution_time"]["available"] is False and data["resolution_time"]["average_hours"] is None
    assert data["officers"]["total"] == 1 and data["officers"]["unassigned"] == 1
    assert len(data["trends"]["weeks"]) == 8
    assert "overdue" in data["definitions"]  # explained, not computed
    assert "sla" not in str(data).lower().replace("no approved sla policy exists", "")


def test_overview_counts_issues_and_complaints_separately_with_pending_review_apart(client, people, second_officer):
    approved_job(client, people, title="A")  # issue 1: Resolved
    create_complaint(client, people["citizen"], latitude="20.050", longitude="73.850", title="B")  # issue 2: Pending
    c = create_complaint(client, people["citizen"], latitude="20.090", longitude="73.900", title="C")  # issue 3
    pending = submit_review(client, people["officer"], c["civic_issue"]["id"], [c["id"]]).get_json()["review"]
    # A second complaint joins issue 3, so the same issue has 2 complaints but is 1 issue.
    create_complaint(client, people["citizen"], latitude="20.0901", longitude="73.9001", title="C again")

    data = overview(client, people["chief"]).get_json()
    assert data["issues"]["total"] == 3
    assert data["issues"]["by_status"] == {"Pending": 1, "In Progress": 0, "Pending Review": 1, "Resolved": 1}
    assert data["complaints"]["eligible_total"] == 4  # not the same number as issues
    assert data["complaints"]["by_status"] == {"Pending": 3, "In Progress": 0, "Resolved": 1}
    assert data["complaints"]["eligible_without_issue_link"] == 0

    reviews = data["reviews"]
    # Issue 3's review went stale when the second complaint arrived: it is
    # awaiting the officer, is not actionable by the Chief, and is not "rejected".
    assert reviews["pending_decision"] == 0
    assert reviews["stale_awaiting_resubmission"] == 1 and reviews["stale_total"] == 1
    assert reviews["approved"] == 1 and reviews["rejected"] == 0 and reviews["superseded"] == 0
    assert reviews["submitted"] == 2
    assert db.session.get(ResolutionReview, pending["id"]).state == "Stale"


def test_overview_distinguishes_rejected_from_stale_and_counts_resubmissions(client, people):
    a = create_complaint(client, people["citizen"], title="A")
    first = submit_review(client, people["officer"], a["civic_issue"]["id"], [a["id"]]).get_json()["review"]
    assert decide(client, people["chief"], first["id"], "Rejected", "The photo does not show the repair.").status_code == 200
    second = submit_review(client, people["officer"], a["civic_issue"]["id"], [a["id"]],
                           supersedes_review_id=str(first["id"])).get_json()["review"]
    reviews = overview(client, people["chief"]).get_json()["reviews"]
    assert reviews["rejected"] == 1 and reviews["resubmissions"] == 1
    assert reviews["pending_decision"] == 1 and reviews["stale_total"] == 0
    assert second["supersedes_review_id"] == first["id"]


def test_resolution_time_uses_approved_reviews_and_excludes_legacy_resolutions(client, people):
    approved_job(client, people)
    legacy = CivicIssue(category="Other", latitude=20.2, longitude=73.9, report_count=1, status="Resolved")
    db.session.add(legacy)
    db.session.commit()  # "resolved" with no approved review and no history, like old data

    data = overview(client, people["chief"]).get_json()["resolution_time"]
    assert data["available"] is True and data["sample_size"] == 1
    assert data["average_hours"] >= 0 and data["median_hours"] >= 0
    assert data["excluded_resolved_without_approved_review"] == 1
    # Generic updated_at is never the source: touching the issue changes nothing.
    db.session.execute(db.text("UPDATE civic_issues SET updated_at = '2000-01-01'"))
    db.session.commit()
    assert overview(client, people["chief"]).get_json()["resolution_time"]["average_hours"] == data["average_hours"]


def test_overview_wards_officers_and_filters(client, people, second_officer, officer_user):
    admin = people["admin"]
    ward_a = client.post("/api/admin/wards", json={"name": "Ward A", "code": "A"}, headers=bearer(admin)).get_json()["ward"]
    ward_b = client.post("/api/admin/wards", json={"name": "Ward B"}, headers=bearer(admin)).get_json()["ward"]
    inactive = client.post("/api/admin/wards", json={"name": "Old ward"}, headers=bearer(admin)).get_json()["ward"]
    client.put(f"/api/admin/wards/{inactive['id']}/deactivate", headers=bearer(admin))
    client.post(f"/api/admin/wards/{ward_a['id']}/assignments", json={"officer_id": officer_user.id}, headers=bearer(admin))
    client.post(f"/api/admin/wards/{ward_b['id']}/assignments", json={"officer_id": officer_user.id}, headers=bearer(admin))
    approved_job(client, people)

    data = overview(client, people["chief"]).get_json()
    assert data["wards"]["active_total"] == 2
    assert [w["name"] for w in data["wards"]["items"]] == ["Ward A", "Ward B"]
    assert [o["id"] for o in data["wards"]["items"][0]["officers"]] == [officer_user.id]
    assert data["officers"]["total"] == 2 and data["officers"]["assigned_to_a_ward"] == 1
    by_id = {o["id"]: o for o in data["officers"]["items"]}
    assert by_id[officer_user.id]["assignment_status"] == "Assigned" and by_id[officer_user.id]["ward_ids"] == [ward_a["id"], ward_b["id"]]
    assert by_id[second_officer.id]["assignment_status"] == "Unassigned"
    assert by_id[officer_user.id]["reviews_submitted"] == 1 and by_id[officer_user.id]["reviews_approved"] == 1
    assert by_id[second_officer.id]["reviews_submitted"] == 0

    only_a = overview(client, people["chief"], f"?ward_id={ward_a['id']}").get_json()
    assert [w["id"] for w in only_a["wards"]["items"]] == [ward_a["id"]]
    assert [o["id"] for o in only_a["officers"]["items"]] == [officer_user.id]
    assert only_a["issues"]["total"] == data["issues"]["total"]  # issues are not ward-filterable

    only_second = overview(client, people["chief"], f"?officer_id={second_officer.id}").get_json()
    assert [o["id"] for o in only_second["officers"]["items"]] == [second_officer.id]
    assert only_second["reviews"]["submitted"] == 0 and only_second["reviews"]["approved"] == 0
    assert overview(client, people["chief"], f"?officer_id={officer_user.id}").get_json()["reviews"]["approved"] == 1

    assert overview(client, people["chief"], "?ward_id=9999").status_code == 404
    assert overview(client, people["chief"], "?officer_id=999").status_code == 404
    assert overview(client, people["chief"], "?ward_id=abc").status_code == 400


def test_overview_date_filters_apply_to_events_not_current_state(client, people):
    c = create_complaint(client, people["citizen"])
    submit_review(client, people["officer"], c["civic_issue"]["id"], [c["id"]])
    future = overview(client, people["chief"], "?from=2999-01-01").get_json()
    assert future["reviews"]["submitted"] == 0
    assert future["reviews"]["pending_decision"] == 1  # current state ignores the window
    assert overview(client, people["chief"], "?from=2000-01-01&to=2999-12-31").get_json()["reviews"]["submitted"] == 1
    for bad in ("?from=yesterday", "?to=2026-13-40", "?from=2026-02-01&to=2026-01-01"):
        assert overview(client, people["chief"], bad).status_code == 400, bad
    weeks = overview(client, people["chief"]).get_json()["trends"]["weeks"]
    assert sum(w["reviews_submitted"] for w in weeks) == 1


# ==========================================
# Phase 2: ratings
# ==========================================

SECRET = "SECRET-EXPLANATION-do-not-leak"


def rate(client, chief, review_id, stars, explanation=None, revises=None, **extra):
    body = {"stars": stars, **extra}
    if explanation is not None:
        body["explanation"] = explanation
    if revises is not None:
        body["revises_rating_id"] = revises
    return client.post(f"/api/chief-officer/resolution-reviews/{review_id}/rating", json=body, headers=bearer(chief))


def snapshot():
    from models.complaint import Complaint
    from models.community import ImpactScoreEvent
    from models.notification import Notification
    db.session.expire_all()
    return {
        "issues": [(i.id, i.status, i.review_revision) for i in CivicIssue.query.order_by(CivicIssue.id)],
        "reviews": [(r.id, r.state, r.reviewed_by, r.rejection_reason) for r in ResolutionReview.query.order_by(ResolutionReview.id)],
        "complaints": [(c.id, c.status) for c in Complaint.query.order_by(Complaint.id)],
        # Citizens' notifications must never change; staff ones are asserted separately.
        "notifications": Notification.query.join(User, User.id == Notification.user_id).filter(User.role == "Citizen").count(),
        "staff_notifications": Notification.query.join(User, User.id == Notification.user_id).filter(User.role != "Citizen").count(),
        "rewards": ImpactScoreEvent.query.count(),
        "users": [(u.id, u.role, u.is_suspended) for u in User.query.order_by(User.id)],
    }


def test_only_a_chief_officer_can_rate(client, people):
    _, review = approved_job(client, people)
    for role in ("citizen", "officer", "admin"):
        assert rate(client, people[role], review["id"], 5).status_code == 403, role
    assert client.post(f"/api/chief-officer/resolution-reviews/{review['id']}/rating", json={"stars": 5}).status_code == 401
    assert ResolutionRating.query.count() == 0
    assert rate(client, people["chief"], review["id"], 5).status_code == 201
    assert rate(client, people["chief"], 99999, 5).status_code == 404


def test_only_approved_work_can_be_rated(client, people):
    pending_c = create_complaint(client, people["citizen"], title="Pending", latitude="20.1", longitude="73.7")
    pending = submit_review(client, people["officer"], pending_c["civic_issue"]["id"], [pending_c["id"]]).get_json()["review"]
    rejected_c = create_complaint(client, people["citizen"], title="Rejected", latitude="20.2", longitude="73.8")
    rejected = submit_review(client, people["officer"], rejected_c["civic_issue"]["id"], [rejected_c["id"]]).get_json()["review"]
    decide(client, people["chief"], rejected["id"], "Rejected", "The photo does not show the repair.")
    stale_c = create_complaint(client, people["citizen"], title="Stale", latitude="20.3", longitude="73.9")
    stale = submit_review(client, people["officer"], stale_c["civic_issue"]["id"], [stale_c["id"]]).get_json()["review"]
    create_complaint(client, people["citizen"], title="Stale again", latitude="20.3001", longitude="73.9001")
    superseded = submit_review(client, people["officer"], rejected_c["civic_issue"]["id"], [rejected_c["id"]],
                               supersedes_review_id=str(rejected["id"])).get_json()
    for review_id in (pending["id"], rejected["id"], stale["id"]):
        response = rate(client, people["chief"], review_id, 4)
        assert response.status_code == 409 and "approved" in response.get_json()["message"], review_id
    assert ResolutionRating.query.count() == 0
    assert superseded["review"]["state"] == "Pending"


def test_rating_validation(client, people):
    _, review = approved_job(client, people)
    for stars in (0, 6, -1, "5", True, 3.5, None):
        assert rate(client, people["chief"], review["id"], stars, "text").status_code == 400, stars
    for explanation in (None, "", "   ", 5):
        body = {"stars": 1}
        if explanation is not None:
            body["explanation"] = explanation
        response = client.post(f"/api/chief-officer/resolution-reviews/{review['id']}/rating", json=body, headers=bearer(people["chief"]))
        assert response.status_code == 400, explanation
    assert rate(client, people["chief"], review["id"], 2, "x" * 2001).status_code == 400
    assert client.post(f"/api/chief-officer/resolution-reviews/{review['id']}/rating", data="nope", headers=bearer(people["chief"])).status_code == 400
    assert ResolutionRating.query.count() == 0
    created = rate(client, people["chief"], review["id"], 4)  # 3-5 stars need no explanation
    assert created.status_code == 201 and created.get_json()["follow_up"] is None


def test_rated_officer_comes_from_the_work_record_not_the_client(client, people, second_officer):
    second = token(client, "officer2@example.com", "officer456")
    _, review = approved_job(client, people, officer_token=second)
    response = rate(client, people["chief"], review["id"], 5, rated_officer_id=1, rated_by=1, role="Admin", needs_follow_up=True)
    assert response.status_code == 201
    rating = db.session.get(ResolutionRating, response.get_json()["rating"]["id"])
    assert rating.rated_officer_id == second_officer.id
    assert rating.rated_by == User.query.filter_by(email="chief@example.com").first().id
    assert rating.needs_follow_up is False


def test_rating_changes_nothing_else(client, people):
    _, review = approved_job(client, people)
    before = snapshot()
    assert rate(client, people["chief"], review["id"], 1, SECRET).status_code == 201  # even a low rating
    after = snapshot()
    # Only the rated Officer is told; nothing else changes (no issue/review/complaint/user change,
    # no citizen notification, no reward, no penalty).
    assert after.pop("staff_notifications") == before.pop("staff_notifications") + 1
    assert after == before


def test_rating_revisions_preserve_history(client, people):
    _, review = approved_job(client, people)
    chief = people["chief"]
    first = rate(client, chief, review["id"], 4, "Good work").get_json()["rating"]
    again = rate(client, chief, review["id"], 5)  # no revision pointer
    assert again.status_code == 409 and f"revision of rating {first['id']}" in again.get_json()["message"]
    assert rate(client, chief, review["id"], 5, revises=first["id"]).status_code == 400  # a revision needs a reason
    assert rate(client, chief, review["id"], 5, "Reviewed again", revises=999).status_code == 409
    second = rate(client, chief, review["id"], 5, "Re-checked the site", revises=first["id"])
    assert second.status_code == 201
    stale_pointer = rate(client, chief, review["id"], 3, "late", revises=first["id"])
    assert stale_pointer.status_code == 409 and "already been revised" in stale_pointer.get_json()["message"]

    history = client.get(f"/api/chief-officer/resolution-reviews/{review['id']}/ratings", headers=bearer(chief)).get_json()["ratings"]
    assert [(r["stars"], r["is_effective"]) for r in history] == [(4, False), (5, True)]
    assert history[0]["explanation"] == "Good work" and history[1]["supersedes_rating_id"] == first["id"]
    assert [r["created_at"] for r in history] == sorted(r["created_at"] for r in history)
    effective = client.get("/api/chief-officer/ratings", headers=bearer(chief)).get_json()["ratings"]
    assert [r["id"] for r in effective] == [second.get_json()["rating"]["id"]]
    everything = client.get("/api/chief-officer/ratings?history=true", headers=bearer(chief)).get_json()["ratings"]
    assert len(everything) == 2
    assert client.get("/api/chief-officer/ratings?stars=4&history=true", headers=bearer(chief)).get_json()["ratings"][0]["id"] == first["id"]
    assert client.get("/api/chief-officer/ratings", headers=bearer(people["officer"])).status_code == 403
    assert client.get(f"/api/chief-officer/resolution-reviews/{review['id']}/ratings", headers=bearer(people["admin"])).status_code == 403


def test_database_blocks_editing_deleting_and_invalid_ratings(client, people, officer_user, citizen_user):
    _, review = approved_job(client, people)
    rating = rate(client, people["chief"], review["id"], 4, "ok").get_json()["rating"]
    chief_id = User.query.filter_by(role="Chief Officer").first().id
    for statement, params in [
        ("UPDATE resolution_ratings SET stars = 5 WHERE id = :r", {"r": rating["id"]}),
        ("UPDATE resolution_ratings SET explanation = 'edited' WHERE id = :r", {"r": rating["id"]}),
        ("DELETE FROM resolution_ratings WHERE id = :r", {"r": rating["id"]}),
    ]:
        with pytest.raises(IntegrityError):
            db.session.execute(db.text(statement), params)
        db.session.rollback()

    insert = ("INSERT INTO resolution_ratings (resolution_review_id, rated_officer_id, rated_by, stars, explanation, "
              "needs_follow_up, supersedes_rating_id, created_at) VALUES (:rv, :ro, :rb, :st, :ex, :nf, :sp, CURRENT_TIMESTAMP)")
    base = {"rv": review["id"], "ro": officer_user.id, "rb": chief_id, "st": 4, "ex": "ok", "nf": 0, "sp": None}
    bad_cases = [
        {"st": 6, "nf": 0}, {"st": 0, "nf": 1, "ex": "x"},                      # outside 1-5
        {"st": 1, "nf": 1, "ex": None}, {"st": 2, "nf": 1, "ex": "   "},        # low needs explanation
        {"st": 4, "nf": 1},                                                      # flag must match stars
        {"rb": officer_user.id},                                                 # only a Chief Officer rates
        {"ro": citizen_user.id},                                                 # only the work's submitter
    ]
    for override in bad_cases:
        with pytest.raises(IntegrityError):
            db.session.execute(db.text(insert), {**base, **override})
        db.session.rollback()
    # Duplicate original, and a second revision of the same rating, are refused by unique indexes.
    with pytest.raises(IntegrityError):
        db.session.execute(db.text(insert), base)
    db.session.rollback()
    db.session.execute(db.text(insert), {**base, "sp": rating["id"]})
    db.session.commit()
    with pytest.raises(IntegrityError):
        db.session.execute(db.text(insert), {**base, "sp": rating["id"], "st": 3})
    db.session.rollback()
    assert ResolutionRating.query.count() == 2

    # A review that is not approved cannot be rated even by direct SQL.
    c = create_complaint(client, people["citizen"], title="Pending", latitude="20.7", longitude="73.7")
    pending = submit_review(client, people["officer"], c["civic_issue"]["id"], [c["id"]]).get_json()["review"]
    with pytest.raises(IntegrityError):
        db.session.execute(db.text(insert), {**base, "rv": pending["id"]})
    db.session.rollback()


def test_duplicate_and_concurrent_ratings_are_safe(client, people):
    import services.performance as perf
    from unittest.mock import patch

    _, review = approved_job(client, people)
    first = rate(client, people["chief"], review["id"], 1, SECRET)
    assert first.status_code == 201
    assert rate(client, people["chief"], review["id"], 1, SECRET).status_code == 409  # a double click
    assert ResolutionRating.query.count() == 1 and ResolutionFollowUp.query.count() == 1

    # A request that read "no rating yet" before another committed one hits the
    # unique index instead of creating a second original.
    with patch.object(perf, "latest_rating", lambda review_id: None):
        raced = rate(client, people["chief"], review["id"], 2, "again")
    assert raced.status_code == 409
    assert ResolutionRating.query.count() == 1 and ResolutionFollowUp.query.count() == 1

    # While a rating is being checked, a competing writer is locked out.
    _, other = approved_job(client, people, latitude="20.5", longitude="73.5", title="Other")
    real_lock = perf._lock_approved_review
    outcome = []

    def lock_then_compete(review_id):
        locked = real_lock(review_id)
        try:
            conn = sqlite3.connect(db.engine.url.database, timeout=0.2)
            conn.execute("UPDATE users SET name = name")
            conn.commit()
            outcome.append("committed")
        except sqlite3.OperationalError:
            outcome.append("blocked")
        return locked

    with patch.object(perf, "_lock_approved_review", lock_then_compete):
        assert rate(client, people["chief"], other["id"], 5).status_code == 201
    assert outcome == ["blocked"]


def test_officers_see_only_their_own_ratings(client, people, second_officer, officer_user):
    second = token(client, "officer2@example.com", "officer456")
    _, mine = approved_job(client, people)
    _, theirs = approved_job(client, people, latitude="20.5", longitude="73.5", title="Theirs", officer_token=second)
    rate(client, people["chief"], mine["id"], 2, SECRET)
    rate(client, people["chief"], theirs["id"], 5, "Other officer's private praise")

    own = client.get("/api/officers/me/ratings", headers=bearer(people["officer"]))
    assert own.status_code == 200
    items = own.get_json()["ratings"]
    assert [r["stars"] for r in items] == [2] and items[0]["explanation"] == SECRET
    assert "Other officer" not in own.get_data(as_text=True)
    assert "rated_by" not in items[0] and "rated_officer" not in items[0]  # no staff identities
    assert items[0]["follow_up"] is None  # not assigned to them yet

    other = client.get("/api/officers/me/ratings", headers=bearer(second)).get_json()["ratings"]
    assert [r["stars"] for r in other] == [5] and SECRET not in str(other)
    for role in ("citizen", "chief", "admin"):
        assert client.get("/api/officers/me/ratings", headers=bearer(people[role])).status_code == 403, role
    assert client.get("/api/officers/me/ratings").status_code == 401


def test_chief_can_list_approved_work_with_rating_state(client, people, second_officer):
    _, rated = approved_job(client, people)
    _, unrated = approved_job(client, people, latitude="20.5", longitude="73.5", title="Unrated")
    rate(client, people["chief"], rated["id"], 1, SECRET)
    everything = client.get("/api/chief-officer/approved-work", headers=bearer(people["chief"])).get_json()["approved_work"]
    by_id = {w["resolution_review_id"]: w for w in everything}
    assert by_id[rated["id"]]["rating"]["stars"] == 1 and by_id[rated["id"]]["follow_up"]["status"] == "Awaiting Assignment"
    assert by_id[unrated["id"]]["rating"] is None and by_id[unrated["id"]]["follow_up"] is None
    assert [w["resolution_review_id"] for w in client.get("/api/chief-officer/approved-work?rated=false", headers=bearer(people["chief"])).get_json()["approved_work"]] == [unrated["id"]]
    assert client.get(f"/api/chief-officer/approved-work?officer_id={second_officer.id}", headers=bearer(people["chief"])).get_json()["approved_work"] == []
    assert client.get("/api/chief-officer/approved-work", headers=bearer(people["officer"])).status_code == 403


def test_citizen_facing_endpoints_never_expose_ratings_or_follow_ups(client, people):
    complaint, review = approved_job(client, people)
    rate(client, people["chief"], review["id"], 1, SECRET)
    issue_id = complaint["civic_issue"]["id"]
    for url in (
        f"/api/complaints/{complaint['id']}",
        f"/api/complaints/{complaint['id']}/resolution-evidence",
        "/api/complaints/",
        f"/api/community/issues/{issue_id}",
        "/api/community/feed",
        "/api/notifications/",
    ):
        response = client.get(url, headers=bearer(people["citizen"]))
        raw = response.get_data(as_text=True)
        assert response.status_code == 200, url
        assert SECRET not in raw, url
        for word in ("stars", "follow_up", "rated_officer", "needs_follow_up"):
            assert word not in raw, (url, word)


# ==========================================
# Phase 3: corrective follow-ups
# ==========================================

def correction(client, officer_token, follow_up_id, note="Re-laid the surface", image=True):
    data = {"note": note} if note is not None else {}
    if image:
        data["image"] = (io.BytesIO(JPEG_BYTES), "fix.jpg")
    return client.post(f"/api/officers/me/follow-ups/{follow_up_id}/submit-correction", data=data,
                       content_type="multipart/form-data", headers=bearer(officer_token))


def assign(client, chief, follow_up_id, officer_id, reason=None):
    body = {"officer_id": officer_id}
    if reason:
        body["reason"] = reason
    return client.put(f"/api/chief-officer/follow-ups/{follow_up_id}/assign", json=body, headers=bearer(chief))


def verify(client, chief, follow_up_id, decision, note=None):
    body = {"decision": decision}
    if note:
        body["note"] = note
    return client.put(f"/api/chief-officer/follow-ups/{follow_up_id}/verify", json=body, headers=bearer(chief))


def low_rated_job(client, people, stars=2, **kwargs):
    complaint, review = approved_job(client, people, **kwargs)
    response = rate(client, people["chief"], review["id"], stars, "Work was incomplete")
    assert response.status_code == 201
    return complaint, review, response.get_json()["follow_up"]


def listing(folder):
    """File names in a folder; a folder that does not exist yet is empty."""
    return set(os.listdir(folder)) if os.path.isdir(folder) else set()


def event_types(follow_up_id):
    db.session.expire_all()
    return [e.event_type for e in FollowUpEvent.query.filter_by(follow_up_id=follow_up_id).order_by(FollowUpEvent.id)]


def test_only_one_or_two_star_ratings_open_exactly_one_follow_up(client, people):
    for index, stars in enumerate((1, 2)):
        _, review, follow_up = low_rated_job(client, people, stars=stars, latitude=f"20.{index + 1}0", longitude="73.7",
                                             title=f"Low {stars}")
        assert follow_up["status"] == "Awaiting Assignment" and follow_up["assigned_officer"] is None
        assert ResolutionFollowUp.query.filter_by(resolution_review_id=review["id"]).count() == 1
        assert event_types(follow_up["id"]) == ["Created"]
    _, fine = approved_job(client, people, latitude="20.60", longitude="73.6", title="Fine")
    assert rate(client, people["chief"], fine["id"], 3).get_json()["follow_up"] is None
    assert ResolutionFollowUp.query.count() == 2


def test_revising_a_low_rating_never_opens_a_second_case(client, people):
    _, review, follow_up = low_rated_job(client, people, stars=1)
    again = rate(client, people["chief"], review["id"], 2, "Still poor", revises=1)
    assert again.status_code == 201 and again.get_json()["follow_up"]["id"] == follow_up["id"]
    assert ResolutionFollowUp.query.count() == 1 and event_types(follow_up["id"]) == ["Created"]


def test_a_rating_revision_never_moves_closes_or_deletes_a_follow_up(client, people, officer_user):
    _, review, follow_up = low_rated_job(client, people, stars=1)
    fid, chief = follow_up["id"], people["chief"]

    # Raising the rating leaves an unstarted case exactly as it was.
    raised = rate(client, chief, review["id"], 4, "Re-inspected: acceptable", revises=1)
    assert raised.get_json()["follow_up"]["status"] == "Awaiting Assignment"
    # Lowering it again does not open a second case.
    lowered = rate(client, chief, review["id"], 2, "Second inspection found defects", revises=raised.get_json()["rating"]["id"])
    assert lowered.get_json()["follow_up"]["id"] == fid
    assert ResolutionFollowUp.query.count() == 1 and event_types(fid) == ["Created"]

    # Same once work has started, and after the case is closed.
    assert assign(client, chief, fid, officer_user.id).status_code == 200
    kept = rate(client, chief, review["id"], 5, "Changed my mind", revises=lowered.get_json()["rating"]["id"])
    assert kept.get_json()["follow_up"]["status"] == "Assigned"
    correction(client, people["officer"], fid)
    assert verify(client, chief, fid, "Close").status_code == 200
    again = rate(client, chief, review["id"], 1, "Found new problems", revises=kept.get_json()["rating"]["id"])
    assert again.status_code == 201 and again.get_json()["follow_up"]["status"] == "Closed"
    assert ResolutionFollowUp.query.count() == 1
    assert [r.stars for r in ResolutionRating.query.order_by(ResolutionRating.id)] == [1, 4, 2, 5, 1]  # all history kept


def test_assignment_requires_an_eligible_officer_and_keeps_history(client, people, officer_user, second_officer,
                                                                   citizen_user, admin_user, chief_officer_user):
    _, _, follow_up = low_rated_job(client, people)
    chief, fid = people["chief"], follow_up["id"]
    for target in (citizen_user, admin_user, chief_officer_user):
        refused = assign(client, chief, fid, target.id)
        assert refused.status_code == 400 and "Officer role" in refused.get_json()["message"], target.role
    assert assign(client, chief, fid, 99999).status_code == 404
    for bad in ("1", None, True, 1.5):
        assert client.put(f"/api/chief-officer/follow-ups/{fid}/assign", json={"officer_id": bad}, headers=bearer(chief)).status_code == 400
    second_officer.is_suspended = True
    db.session.commit()
    assert assign(client, chief, fid, second_officer.id).status_code == 400
    second_officer.is_suspended = False
    db.session.commit()

    first = assign(client, chief, fid, officer_user.id, "Original crew")
    assert first.status_code == 200 and first.get_json()["follow_up"]["status"] == "Assigned"
    assert assign(client, chief, fid, officer_user.id).status_code == 409  # already theirs
    moved = assign(client, chief, fid, second_officer.id, "Needs a different crew")
    assert moved.status_code == 200 and moved.get_json()["follow_up"]["assigned_officer"]["id"] == second_officer.id
    events = moved.get_json()["follow_up"]["events"]
    assert [e["event_type"] for e in events] == ["Created", "Assigned", "Reassigned"]
    assert events[1]["officer"]["id"] == officer_user.id and events[2]["officer"]["id"] == second_officer.id
    assert events[1]["note"] == "Original crew"  # earlier assignment preserved
    assert assign(client, chief, 9999, officer_user.id).status_code == 404


def test_role_boundaries_on_follow_up_endpoints(client, people, officer_user):
    _, _, follow_up = low_rated_job(client, people)
    fid = follow_up["id"]
    for role in ("officer", "citizen", "admin"):
        for method, url, body in (
            ("get", "/api/chief-officer/follow-ups", None),
            ("get", f"/api/chief-officer/follow-ups/{fid}", None),
            ("put", f"/api/chief-officer/follow-ups/{fid}/assign", {"officer_id": officer_user.id}),
            ("put", f"/api/chief-officer/follow-ups/{fid}/verify", {"decision": "Close"}),
        ):
            assert getattr(client, method)(url, json=body, headers=bearer(people[role])).status_code == 403, (role, url)
    for role in ("citizen", "chief", "admin"):
        assert client.get("/api/officers/me/follow-ups", headers=bearer(people[role])).status_code == 403, role
        assert correction(client, people[role], fid).status_code == 403, role
    assert client.get("/api/chief-officer/follow-ups").status_code == 401
    assert ResolutionFollowUp.query.first().status == "Awaiting Assignment"


def test_officer_sees_and_corrects_only_their_own_follow_up(client, people, officer_user, second_officer):
    second = token(client, "officer2@example.com", "officer456")
    _, _, follow_up = low_rated_job(client, people)
    fid = follow_up["id"]
    assign(client, people["chief"], fid, officer_user.id, "Please redo the edge")

    mine = client.get("/api/officers/me/follow-ups", headers=bearer(people["officer"])).get_json()["follow_ups"]
    assert [f["id"] for f in mine] == [fid]
    assert mine[0]["rating"] == {"stars": 2, "explanation": "Work was incomplete"}
    assert "actor" not in mine[0]["events"][0] and mine[0]["events"][0]["actor_role"] == "Chief Officer"
    assert client.get("/api/officers/me/follow-ups", headers=bearer(second)).get_json()["follow_ups"] == []
    assert correction(client, second, fid).status_code == 404  # another officer's case
    assert correction(client, people["officer"], 9999).status_code == 404
    assert ResolutionFollowUp.query.first().status == "Assigned"


def test_correction_submission_validation_and_idempotency(client, people, officer_user):
    _, _, follow_up = low_rated_job(client, people)
    fid, officer = follow_up["id"], people["officer"]
    upload_dir = client.application.config["PRIVATE_UPLOAD_FOLDER"]
    assert correction(client, officer, fid).status_code == 404  # not their case until assigned
    assign(client, people["chief"], fid, officer_user.id)

    before_files = listing(upload_dir)
    assert correction(client, officer, fid, note="   ").status_code == 400
    assert correction(client, officer, fid, note=None).status_code == 400
    bad = client.post(f"/api/officers/me/follow-ups/{fid}/submit-correction",
                      data={"note": "x", "image": (io.BytesIO(b"not an image"), "x.jpg")},
                      content_type="multipart/form-data", headers=bearer(officer))
    assert bad.status_code == 400
    assert listing(upload_dir) == before_files and ResolutionFollowUp.query.first().status == "Assigned"

    ok = correction(client, officer, fid, note="Re-laid the surface")
    assert ok.status_code == 200 and ok.get_json()["follow_up"]["status"] == "Correction Submitted"
    last = ok.get_json()["follow_up"]["events"][-1]
    assert last["event_type"] == "CorrectionSubmitted" and last["note"] == "Re-laid the surface"
    # No public URL for staff evidence; only the authenticated, API-relative path.
    assert "image_url" not in last
    assert last["image_path"] == f"/officers/me/follow-ups/{fid}/events/{last['id']}/image"
    files_after_first = listing(upload_dir)
    added = files_after_first - before_files  # the folder is shared by the whole test session
    assert len(added) == 1
    assert listing(client.application.config["UPLOAD_FOLDER"]).isdisjoint(added)  # not in the public folder
    again = correction(client, officer, fid)  # a repeated click
    assert again.status_code == 409
    assert event_types(fid).count("CorrectionSubmitted") == 1 and listing(upload_dir) == files_after_first
    assert correction(client, officer, fid, note="note only", image=False).status_code == 409  # still only one submission


def test_lost_race_on_correction_cleans_up_its_upload(client, people, officer_user):
    import services.performance as perf
    from unittest.mock import patch

    _, _, follow_up = low_rated_job(client, people)
    fid = follow_up["id"]
    assign(client, people["chief"], fid, officer_user.id)
    upload_dir = client.application.config["PRIVATE_UPLOAD_FOLDER"]
    before = listing(upload_dir)
    real = perf._transition

    def lose_the_race(follow_up_id, expected_status, expected_officer_id, **changes):
        # Another request submits first, so this one's compare-and-swap finds a different status.
        db.session.execute(db.text("UPDATE resolution_follow_ups SET status = 'Correction Submitted' WHERE id = :i"), {"i": follow_up_id})
        return real(follow_up_id, expected_status, expected_officer_id, **changes)

    with patch.object(perf, "_transition", lose_the_race):
        response = correction(client, people["officer"], fid)
    assert response.status_code == 409
    assert listing(upload_dir) == before
    assert event_types(fid) == ["Created", "Assigned"]


def test_only_a_chief_officer_verifies_and_the_issue_is_untouched(client, people, officer_user):
    complaint, review, follow_up = low_rated_job(client, people)
    fid, chief = follow_up["id"], people["chief"]
    assign(client, chief, fid, officer_user.id)
    assert verify(client, chief, fid, "Close").status_code == 409  # nothing submitted yet
    correction(client, people["officer"], fid)
    before = snapshot()

    assert verify(client, chief, fid, "Maybe").status_code == 400
    assert verify(client, chief, fid, "Return").status_code == 400  # a reason is required
    returned = verify(client, chief, fid, "Return", "The edge is still rough")
    assert returned.status_code == 200 and returned.get_json()["follow_up"]["status"] == "Assigned"
    assert verify(client, chief, fid, "Close").status_code == 409  # returned: needs a new submission

    correction(client, people["officer"], fid, note="Smoothed the edge", image=False)
    closed = verify(client, chief, fid, "Close", "Checked on site")
    assert closed.status_code == 200
    body = closed.get_json()["follow_up"]
    assert body["status"] == "Closed" and body["closed_at"]
    assert [e["event_type"] for e in body["events"]] == [
        "Created", "Assigned", "CorrectionSubmitted", "CorrectionReturned", "CorrectionSubmitted", "Closed"]
    assert body["events"][-1]["note"] == "Checked on site"

    again = verify(client, chief, fid, "Close")  # repeated closure
    assert again.status_code == 409 and event_types(fid).count("Closed") == 1
    assert assign(client, chief, fid, officer_user.id).status_code == 409  # closed cases are final

    after = snapshot()
    # No issue/review/user change, no penalty, no new notification or reward (events aside).
    for key in ("issues", "reviews", "complaints", "notifications", "rewards", "users"):
        assert after[key] == before[key], key  # incl. citizens' notifications and the Officer's account
    # Staff only: the Officer hears the return and the closure, the Chief Officer hears the resubmission.
    assert after["staff_notifications"] == before["staff_notifications"] + 3
    assert db.session.get(CivicIssue, complaint["civic_issue"]["id"]).status == "Resolved"
    assert db.session.get(ResolutionReview, review["id"]).state == "Approved"


def test_chief_can_filter_follow_ups_and_read_the_trail(client, people, officer_user, second_officer):
    _, _, first = low_rated_job(client, people, title="One")
    _, _, second = low_rated_job(client, people, latitude="20.6", longitude="73.6", title="Two")
    assign(client, people["chief"], second["id"], officer_user.id)
    listing = client.get("/api/chief-officer/follow-ups", headers=bearer(people["chief"])).get_json()["follow_ups"]
    assert {f["id"] for f in listing} == {first["id"], second["id"]}
    waiting = client.get("/api/chief-officer/follow-ups?status=Awaiting%20Assignment", headers=bearer(people["chief"])).get_json()["follow_ups"]
    assert [f["id"] for f in waiting] == [first["id"]]
    mine = client.get(f"/api/chief-officer/follow-ups?assigned_officer_id={officer_user.id}", headers=bearer(people["chief"])).get_json()["follow_ups"]
    assert [f["id"] for f in mine] == [second["id"]]
    assert client.get("/api/chief-officer/follow-ups?status=Bogus", headers=bearer(people["chief"])).status_code == 400
    detail = client.get(f"/api/chief-officer/follow-ups/{second['id']}", headers=bearer(people["chief"])).get_json()["follow_up"]
    assert [e["event_type"] for e in detail["events"]] == ["Created", "Assigned"]
    assert detail["events"][0]["actor"]["name"] and detail["rated_officer"]["id"] == officer_user.id
    assert client.get("/api/chief-officer/follow-ups/9999", headers=bearer(people["chief"])).status_code == 404


def test_overview_reports_follow_up_and_rating_figures(client, people, officer_user):
    _, _, follow_up = low_rated_job(client, people, stars=1)
    assign(client, people["chief"], follow_up["id"], officer_user.id)
    _, fine = approved_job(client, people, latitude="20.6", longitude="73.6", title="Fine")
    rate(client, people["chief"], fine["id"], 5)
    _, unrated = approved_job(client, people, latitude="20.7", longitude="73.7", title="Unrated")

    data = overview(client, people["chief"]).get_json()
    assert data["follow_ups"]["total"] == 1 and data["follow_ups"]["by_status"]["Assigned"] == 1
    assert data["ratings"]["effective_total"] == 2 and data["ratings"]["low_total"] == 1
    assert data["ratings"]["by_stars"] == {"1": 1, "2": 0, "3": 0, "4": 0, "5": 1}
    assert data["ratings"]["approved_not_yet_rated"] == 1
    me = next(o for o in data["officers"]["items"] if o["id"] == officer_user.id)
    assert me["ratings_received"] == 2 and me["low_ratings_received"] == 1 and me["open_corrections_assigned"] == 1
    assert not any("average" in key for key in data["ratings"])  # no officer score is computed


def test_follow_up_tables_are_protected_in_the_database(client, people, officer_user):
    _, _, follow_up = low_rated_job(client, people)
    fid = follow_up["id"]
    assign(client, people["chief"], fid, officer_user.id)
    event_id = FollowUpEvent.query.filter_by(follow_up_id=fid).first().id
    forbidden = [
        ("UPDATE resolution_follow_up_events SET note = 'edited' WHERE id = :e", {"e": event_id}),
        ("DELETE FROM resolution_follow_up_events WHERE id = :e", {"e": event_id}),
        ("DELETE FROM resolution_follow_ups WHERE id = :f", {"f": fid}),
        ("UPDATE resolution_follow_ups SET status = 'Bogus' WHERE id = :f", {"f": fid}),
        ("UPDATE resolution_follow_ups SET resolution_review_id = 999 WHERE id = :f", {"f": fid}),
        ("UPDATE resolution_follow_ups SET issue_id = 999 WHERE id = :f", {"f": fid}),
        ("INSERT INTO resolution_follow_up_events (follow_up_id, event_type, to_status, actor_id, created_at) "
         "VALUES (:f, 'Bogus', 'Assigned', 1, CURRENT_TIMESTAMP)", {"f": fid}),
        ("INSERT INTO resolution_follow_up_events (follow_up_id, event_type, to_status, actor_id, created_at) "
         "VALUES (:f, 'Assigned', 'Bogus', 1, CURRENT_TIMESTAMP)", {"f": fid}),
    ]
    for statement, params in forbidden:
        with pytest.raises(IntegrityError):
            db.session.execute(db.text(statement), params)
        db.session.rollback()
    assert ResolutionFollowUp.query.count() == 1


def test_performance_migration_is_rerunnable_on_an_existing_database():
    import tempfile
    from app import app as flask_app, migrate_performance_schema

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, role VARCHAR(20));"
            "CREATE TABLE resolution_reviews (id INTEGER PRIMARY KEY, state VARCHAR(20), submitted_by INTEGER, issue_id INTEGER);"
            "INSERT INTO users VALUES (1, 'Chief Officer'), (2, 'Officer');"
            "INSERT INTO resolution_reviews VALUES (1, 'Approved', 2, 1);"
            "CREATE TABLE resolution_ratings (id INTEGER PRIMARY KEY, resolution_review_id INTEGER, rated_officer_id INTEGER, "
            "rated_by INTEGER, stars INTEGER, explanation TEXT, needs_follow_up BOOLEAN, supersedes_rating_id INTEGER, created_at DATETIME);"
            "INSERT INTO resolution_ratings VALUES (1, 1, 2, 1, 4, NULL, 0, NULL, '2026-01-01');"
        )
        conn.commit()
        conn.close()
        previous = flask_app.config["SQLALCHEMY_DATABASE_URI"]
        flask_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{path}"
        try:
            migrate_performance_schema()
            migrate_performance_schema()
        finally:
            flask_app.config["SQLALCHEMY_DATABASE_URI"] = previous
        conn = sqlite3.connect(path)
        assert conn.execute("SELECT id, stars FROM resolution_ratings").fetchall() == [(1, 4)]  # preserved
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert {"resolution_ratings_stars_range", "resolution_ratings_immutable_update", "resolution_ratings_approved_only"} <= triggers
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE resolution_ratings SET stars = 1")
        conn.close()
    finally:
        os.remove(path)


# ==========================================
# Notifications
# ==========================================

def notes_for(user_id):
    from models.notification import Notification
    db.session.expire_all()
    return [n.message for n in Notification.query.filter_by(user_id=user_id).order_by(Notification.id)]


def test_rating_notifies_only_the_rated_officer_without_leaking_the_explanation(client, people, officer_user, second_officer):
    chief_id = User.query.filter_by(role="Chief Officer").first().id
    citizen_id = User.query.filter_by(role="Citizen").first().id
    _, review = approved_job(client, people)
    before = {uid: len(notes_for(uid)) for uid in (chief_id, citizen_id, second_officer.id, officer_user.id)}

    first = rate(client, people["chief"], review["id"], 2, SECRET)
    assert first.status_code == 201
    mine = notes_for(officer_user.id)[before[officer_user.id]:]
    assert len(mine) == 1 and "2-star" in mine[0] and "received" in mine[0]
    assert SECRET not in mine[0]
    revised = rate(client, people["chief"], review["id"], 4, "Re-inspected", revises=first.get_json()["rating"]["id"])
    assert revised.status_code == 201
    mine = notes_for(officer_user.id)[before[officer_user.id]:]
    assert len(mine) == 2 and "updated to a 4-star" in mine[1]
    for uid in (chief_id, citizen_id, second_officer.id):
        assert len(notes_for(uid)) == before[uid], uid  # nobody else is told

    assert rate(client, people["chief"], review["id"], 4, "again").status_code == 409  # a retry
    assert len(notes_for(officer_user.id)) == before[officer_user.id] + 2  # no duplicate


def test_follow_up_lifecycle_notifies_the_right_people_once(client, people, officer_user, second_officer):
    second = token(client, "officer2@example.com", "officer456")
    chief_id = User.query.filter_by(role="Chief Officer").first().id
    _, _, follow_up = low_rated_job(client, people)
    fid, chief = follow_up["id"], people["chief"]
    base = {uid: len(notes_for(uid)) for uid in (officer_user.id, second_officer.id, chief_id)}
    delta = lambda uid: notes_for(uid)[base[uid]:]  # noqa: E731

    assert assign(client, chief, fid, officer_user.id, "Fix the edge").status_code == 200
    assert len(delta(officer_user.id)) == 1 and "assigned to you" in delta(officer_user.id)[0]
    assert "Fix the edge" not in delta(officer_user.id)[0]  # instructions are read in the app
    assert assign(client, chief, fid, officer_user.id).status_code == 409
    assert len(delta(officer_user.id)) == 1  # the rejected retry sent nothing

    assert assign(client, chief, fid, second_officer.id).status_code == 200
    assert "reassigned to another Officer" in delta(officer_user.id)[-1] and len(delta(officer_user.id)) == 2
    assert len(delta(second_officer.id)) == 1 and "assigned to you" in delta(second_officer.id)[0]

    assert correction(client, second, fid).status_code == 200
    assert correction(client, second, fid).status_code == 409
    assert len(delta(chief_id)) == 1 and "awaits your verification" in delta(chief_id)[0]  # once, to the assigning Chief

    assert verify(client, chief, fid, "Return", "Edge still rough").status_code == 200
    assert "returned" in delta(second_officer.id)[-1] and "Edge still rough" not in delta(second_officer.id)[-1]
    assert correction(client, second, fid, image=False).status_code == 200
    assert verify(client, chief, fid, "Close").status_code == 200
    assert verify(client, chief, fid, "Close").status_code == 409
    closing = [m for m in delta(second_officer.id) if "verified" in m]
    assert len(closing) == 1 and "closed" in closing[0]
    assert len(delta(officer_user.id)) == 2  # the previous assignee hears nothing more


def test_correction_notification_falls_back_to_every_chief_officer(client, people, officer_user):
    other = User(name="Second Chief", email="chief2@example.com", password_hash=hash_password("chief456"), role="Chief Officer")
    db.session.add(other)
    db.session.commit()
    _, _, follow_up = low_rated_job(client, people)
    assign(client, people["chief"], follow_up["id"], officer_user.id)
    first_chief = User.query.filter_by(email="chief@example.com").first()
    first_chief.role = "Citizen"  # the assigner is no longer a Chief Officer
    db.session.commit()
    before = len(notes_for(other.id))
    assert correction(client, people["officer"], follow_up["id"]).status_code == 200
    assert len(notes_for(other.id)) == before + 1


def test_staff_read_their_own_notifications_only(client, people, officer_user, second_officer):
    second = token(client, "officer2@example.com", "officer456")
    _, _, follow_up = low_rated_job(client, people)
    assign(client, people["chief"], follow_up["id"], officer_user.id)
    mine = client.get("/api/notifications/", headers=bearer(people["officer"])).get_json()["notifications"]
    assert any("assigned to you" in n["message"] for n in mine)
    assert client.get("/api/notifications/", headers=bearer(second)).get_json()["notifications"] == []
    citizen = client.get("/api/notifications/", headers=bearer(people["citizen"])).get_json()["notifications"]
    assert not any(word in str(citizen) for word in ("star", "follow-up", "correction"))


# ==========================================
# Pagination
# ==========================================

def test_lists_are_paginated_with_totals(client, people, officer_user):
    for index in range(3):
        _, review, _ = low_rated_job(client, people, stars=2, latitude=f"20.{index + 1}0", longitude="73.7", title=f"Job {index}")
    chief = people["chief"]
    for url, key in (("/api/chief-officer/ratings", "ratings"), ("/api/chief-officer/follow-ups", "follow_ups"),
                     ("/api/chief-officer/approved-work", "approved_work")):
        page = client.get(f"{url}?limit=2&offset=0", headers=bearer(chief)).get_json()
        rest = client.get(f"{url}?limit=2&offset=2", headers=bearer(chief)).get_json()
        assert page["total"] == 3 and page["limit"] == 2 and page["offset"] == 0 and len(page[key]) == 2, url
        assert len(rest[key]) == 1 and rest["offset"] == 2, url
        ids = [row.get("id", row.get("resolution_review_id")) for row in page[key] + rest[key]]
        assert len(set(ids)) == 3, url  # no overlap between pages
        for bad in ("?limit=abc", "?offset=x"):
            assert client.get(f"{url}{bad}", headers=bearer(chief)).status_code == 400, (url, bad)
        assert len(client.get(f"{url}?limit=0", headers=bearer(chief)).get_json()[key]) == 1  # clamped to the minimum
    mine = client.get("/api/officers/me/ratings?limit=2", headers=bearer(people["officer"])).get_json()
    assert mine["total"] == 3 and len(mine["ratings"]) == 2
    assert client.get("/api/officers/me/follow-ups?status=Bogus", headers=bearer(people["officer"])).status_code == 400
    assert client.get("/api/officers/me/follow-ups", headers=bearer(people["officer"])).get_json()["total"] == 0


def test_follow_up_filters_by_stars_and_rated_officer(client, people, officer_user, second_officer):
    second = token(client, "officer2@example.com", "officer456")
    _, _, one_star = low_rated_job(client, people, stars=1, title="One")
    _, _, two_star = low_rated_job(client, people, stars=2, latitude="20.6", longitude="73.6", title="Two")
    chief = people["chief"]
    only_one = client.get("/api/chief-officer/follow-ups?stars=1", headers=bearer(chief)).get_json()["follow_ups"]
    assert [f["id"] for f in only_one] == [one_star["id"]]
    by_officer = client.get(f"/api/chief-officer/follow-ups?rated_officer_id={officer_user.id}", headers=bearer(chief)).get_json()
    assert by_officer["total"] == 2
    assert client.get(f"/api/chief-officer/follow-ups?rated_officer_id={second_officer.id}", headers=bearer(chief)).get_json()["total"] == 0
    assert second  # fixture used to prove a second officer exists with no work


# ==========================================
# Ward and Officer directory views
# ==========================================

def test_ward_detail_is_chief_only_read_only_and_shows_history_without_admin_notes(client, people, officer_user, second_officer):
    admin = people["admin"]
    ward = client.post("/api/admin/wards", json={"name": "Ward A", "code": "A"}, headers=bearer(admin)).get_json()["ward"]
    first = client.post(f"/api/admin/wards/{ward['id']}/assignments", json={"officer_id": officer_user.id, "reason": "ADMIN-PRIVATE-REASON"},
                        headers=bearer(admin)).get_json()["assignment"]
    client.put(f"/api/admin/wards/{ward['id']}/assignments/{first['id']}/end", json={"reason": "ADMIN-END-REASON"}, headers=bearer(admin))
    client.post(f"/api/admin/wards/{ward['id']}/assignments", json={"officer_id": second_officer.id}, headers=bearer(admin))
    approved_job(client, people)

    response = client.get(f"/api/chief-officer/wards/{ward['id']}", headers=bearer(people["chief"]))
    assert response.status_code == 200
    data = response.get_json()
    assert [(a["officer"]["id"], a["is_active"]) for a in data["assignments"]] == [(second_officer.id, True), (officer_user.id, False)]
    assert data["assignments"][1]["ended_at"]
    assert list(data["active_officer_activity"]) == [str(second_officer.id)]  # only currently assigned Officers
    assert data["active_officer_activity"][str(second_officer.id)]["reviews_submitted"] == 0
    raw = response.get_data(as_text=True)
    assert "ADMIN-PRIVATE-REASON" not in raw and "ADMIN-END-REASON" not in raw and "assigned_by" not in raw
    assert "not work done in this ward" in data["note"]

    assert client.get("/api/chief-officer/wards/9999", headers=bearer(people["chief"])).status_code == 404
    for role in ("admin", "officer", "citizen"):
        assert client.get(f"/api/chief-officer/wards/{ward['id']}", headers=bearer(people[role])).status_code == 403, role
    assert client.get(f"/api/chief-officer/wards/{ward['id']}").status_code == 401


def test_officer_detail_separates_submissions_from_unique_issues(client, people, officer_user, second_officer):
    complaint = create_complaint(client, people["citizen"], title="Repeat job")
    issue_id = complaint["civic_issue"]["id"]
    first = submit_review(client, people["officer"], issue_id, [complaint["id"]]).get_json()["review"]
    decide(client, people["chief"], first["id"], "Rejected", "The photo does not show the repair.")
    second = submit_review(client, people["officer"], issue_id, [complaint["id"]],
                           supersedes_review_id=str(first["id"])).get_json()["review"]
    decide(client, people["chief"], second["id"], "Approved")
    for note in ("Day 1", "Day 2", "Day 3"):
        client.post(f"/api/issues/{issue_id}/work-updates", data={"note": note, "status": "In Progress"},
                    headers={**bearer(people["officer"]), "Idempotency-Key": f"key-{note}"})
    rate(client, people["chief"], second["id"], 2, "Needs a redo")

    response = client.get(f"/api/chief-officer/officers/{officer_user.id}", headers=bearer(people["chief"]))
    assert response.status_code == 200
    data = response.get_json()
    work = data["work"]
    assert work["review_submissions"] == 2 and work["issues_with_review_submissions"] == 1  # two submissions, one issue
    assert work["work_updates"] == 3 and work["issues_with_work_updates"] == 1
    assert work["approved"] == 1 and work["rejected"] == 1 and work["superseded"] == 0 and work["stale_total"] >= 0
    assert "not unique issues" in work["note"]
    assert data["ratings"]["by_stars"]["2"] == 1 and data["follow_ups"]["on_this_officers_work"]["Awaiting Assignment"] == 1
    assert not any("average" in key or "rank" in key for key in data["ratings"])
    assert {"id", "name", "email", "is_suspended", "role"} == set(data["officer"])  # no password hash etc.
    submissions = data["submissions"]
    assert submissions["total"] == 2 and [s["state"] for s in submissions["items"]] == ["Approved", "Rejected"]
    assert submissions["items"][0]["rating"]["stars"] == 2 and submissions["items"][0]["follow_up"]["status"] == "Awaiting Assignment"

    only_rejected = client.get(f"/api/chief-officer/officers/{officer_user.id}?state=Rejected", headers=bearer(people["chief"])).get_json()
    assert only_rejected["submissions"]["total"] == 1
    paged = client.get(f"/api/chief-officer/officers/{officer_user.id}?limit=1&offset=1", headers=bearer(people["chief"])).get_json()
    assert [s["state"] for s in paged["submissions"]["items"]] == ["Rejected"]
    idle = client.get(f"/api/chief-officer/officers/{second_officer.id}", headers=bearer(people["chief"])).get_json()
    assert idle["work"]["review_submissions"] == 0 and idle["submissions"]["items"] == []

    assert client.get("/api/chief-officer/officers/9999", headers=bearer(people["chief"])).status_code == 404
    citizen_id = User.query.filter_by(role="Citizen").first().id
    assert client.get(f"/api/chief-officer/officers/{citizen_id}", headers=bearer(people["chief"])).status_code == 404  # only Officers
    assert client.get(f"/api/chief-officer/officers/{officer_user.id}?state=Bogus", headers=bearer(people["chief"])).status_code == 400
    for role in ("admin", "officer", "citizen"):
        assert client.get(f"/api/chief-officer/officers/{officer_user.id}", headers=bearer(people[role])).status_code == 403, role


def test_overview_separates_work_submissions_from_unique_issues(client, people):
    c = create_complaint(client, people["citizen"])
    for note in ("a", "b"):
        client.post(f"/api/issues/{c['civic_issue']['id']}/work-updates", data={"note": note, "status": "In Progress"},
                    headers={**bearer(people["officer"]), "Idempotency-Key": f"k-{note}"})
    work = overview(client, people["chief"]).get_json()["work"]
    assert work["work_updates"] == 2 and work["issues_with_work_updates"] == 1
    assert work["review_submissions"] == 0 and work["issues_with_review_submissions"] == 0


def test_officer_follow_up_detail_shows_own_work_context_only(client, people, officer_user, second_officer):
    second = token(client, "officer2@example.com", "officer456")
    _, review, follow_up = low_rated_job(client, people)
    fid = follow_up["id"]
    assign(client, people["chief"], fid, officer_user.id, "Please redo the edge")
    response = client.get(f"/api/officers/me/follow-ups/{fid}", headers=bearer(people["officer"]))
    assert response.status_code == 200
    data = response.get_json()["follow_up"]
    assert data["work"]["by_this_officer"] is True and data["work"]["completion_note"] and data["work"]["image_url"].startswith("/uploads/")
    assert data["events"][1]["note"] == "Please redo the edge" and "actor" not in data["events"][1]
    assert client.get(f"/api/officers/me/follow-ups/{fid}", headers=bearer(second)).status_code == 404
    for role in ("chief", "admin", "citizen"):
        assert client.get(f"/api/officers/me/follow-ups/{fid}", headers=bearer(people[role])).status_code == 403, role
    assert client.get("/api/officers/me/follow-ups/9999", headers=bearer(people["officer"])).status_code == 404


def test_approved_work_listing_carries_the_evidence_being_rated(client, people):
    complaint, review = approved_job(client, people)
    item = client.get("/api/chief-officer/approved-work", headers=bearer(people["chief"])).get_json()["approved_work"][0]
    assert item["evidence"]["completion_note"] == review["completion_note"]
    assert item["evidence"]["image_url"] == review["image_url"] and item["evidence"]["dispositions"] == 1


def test_officers_open_corrections_sort_ahead_of_closed_ones_across_pages(client, people, officer_user):
    """An old open correction must not sink onto a later page behind newer closed cases."""
    first = low_rated_job(client, people, latitude="20.10", longitude="73.7", title="old open")[2]
    later = [low_rated_job(client, people, latitude=f"20.{n}0", longitude="73.7", title=f"closed {n}")[2] for n in (3, 5)]
    chief, officer = people["chief"], people["officer"]
    for follow_up in [first, *later]:
        assert assign(client, chief, follow_up["id"], officer_user.id).status_code == 200
    for follow_up in later:  # newer cases are completed and closed after the old one was assigned
        assert correction(client, officer, follow_up["id"]).status_code in (200, 201)
        assert verify(client, chief, follow_up["id"], "Close").status_code == 200

    page = client.get("/api/officers/me/follow-ups?limit=1", headers=bearer(officer)).get_json()
    assert page["total"] == 3
    assert [f["id"] for f in page["follow_ups"]] == [first["id"]]
    assert page["follow_ups"][0]["status"] == "Assigned"


# ==========================================
# Staff-only correction evidence
# ==========================================

def evidence_case(client, people, officer_user):
    """A follow-up assigned to the officer who submitted a correction with a photo."""
    _, _, follow_up = low_rated_job(client, people)
    fid = follow_up["id"]
    assert assign(client, people["chief"], fid, officer_user.id).status_code == 200
    assert correction(client, people["officer"], fid).status_code == 200
    events = client.get(f"/api/chief-officer/follow-ups/{fid}", headers=bearer(people["chief"])).get_json()["follow_up"]["events"]
    event = next(e for e in events if e["event_type"] == "CorrectionSubmitted")
    return fid, event


def image_url(fid, event_id, who="chief"):
    prefix = "/api/chief-officer" if who == "chief" else "/api/officers/me"
    return f"{prefix}/follow-ups/{fid}/events/{event_id}/image"


def test_correction_photo_is_served_only_to_the_assigned_officer_and_chief(client, people, officer_user, second_officer):
    fid, event = evidence_case(client, people, officer_user)
    eid = event["id"]
    second = token_for(client, "officer2@example.com", "officer456")

    chief = client.get(image_url(fid, eid), headers=bearer(people["chief"]))
    assert chief.status_code == 200 and chief.data == JPEG_BYTES
    assert chief.headers["Content-Type"] == "image/jpeg"
    assert chief.headers["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in chief.headers["Cache-Control"] and "private" in chief.headers["Cache-Control"]

    mine = client.get(image_url(fid, eid, "officer"), headers=bearer(people["officer"]))
    assert mine.status_code == 200 and mine.data == JPEG_BYTES and mine.headers["X-Content-Type-Options"] == "nosniff"

    # Anonymous, Citizen and Admin are refused on both routes without any file bytes.
    for who in ("chief", "officer"):
        assert client.get(image_url(fid, eid, who)).status_code == 401
        for role in ("citizen", "admin"):
            response = client.get(image_url(fid, eid, who), headers=bearer(people[role]))
            assert response.status_code == 403 and JPEG_BYTES not in response.data, (who, role)
    # An Officer cannot use the Chief route, nor the Chief the Officer route.
    assert client.get(image_url(fid, eid), headers=bearer(people["officer"])).status_code == 403
    assert client.get(image_url(fid, eid, "officer"), headers=bearer(people["chief"])).status_code == 403
    # An unrelated Officer gets the same 404 as for a record that does not exist.
    unrelated = client.get(image_url(fid, eid, "officer"), headers=bearer(second))
    missing = client.get(image_url(fid, 99999, "officer"), headers=bearer(people["officer"]))
    assert unrelated.status_code == 404 and missing.status_code == 404
    assert unrelated.get_json() == missing.get_json() and JPEG_BYTES not in unrelated.data


def test_previous_assignee_loses_access_to_the_photo_after_reassignment(client, people, officer_user, second_officer):
    _, _, follow_up = low_rated_job(client, people)
    fid = follow_up["id"]
    second = token_for(client, "officer2@example.com", "officer456")
    assert assign(client, people["chief"], fid, officer_user.id).status_code == 200
    assert assign(client, people["chief"], fid, second_officer.id).status_code == 200  # reassigned before any correction
    assert correction(client, second, fid).status_code == 200
    events = client.get(f"/api/chief-officer/follow-ups/{fid}", headers=bearer(people["chief"])).get_json()["follow_up"]["events"]
    eid = next(e["id"] for e in events if e["event_type"] == "CorrectionSubmitted")
    assert client.get(image_url(fid, eid, "officer"), headers=bearer(second)).status_code == 200
    assert client.get(image_url(fid, eid, "officer"), headers=bearer(people["officer"])).status_code == 404  # no longer assigned


def test_photo_must_belong_to_the_follow_up_in_the_url_and_be_a_correction(client, people, officer_user):
    fid, event = evidence_case(client, people, officer_user)
    other_fid, other_event = evidence_case_other(client, people, officer_user)
    assert client.get(image_url(fid, other_event["id"]), headers=bearer(people["chief"])).status_code == 404  # event of another case
    assert client.get(image_url(other_fid, event["id"]), headers=bearer(people["chief"])).status_code == 404
    created = FollowUpEvent.query.filter_by(follow_up_id=fid, event_type="Created").first()
    assigned = FollowUpEvent.query.filter_by(follow_up_id=fid, event_type="Assigned").first()
    for other_type in (created, assigned):  # events with no photo, or not a correction
        assert client.get(image_url(fid, other_type.id), headers=bearer(people["chief"])).status_code == 404
    assert client.get(image_url(99999, event["id"]), headers=bearer(people["chief"])).status_code == 404


def evidence_case_other(client, people, officer_user):
    _, _, follow_up = low_rated_job(client, people, latitude="21.50", longitude="74.1", title="second job")
    fid = follow_up["id"]
    assert assign(client, people["chief"], fid, officer_user.id).status_code == 200
    assert correction(client, people["officer"], fid).status_code == 200
    events = client.get(f"/api/chief-officer/follow-ups/{fid}", headers=bearer(people["chief"])).get_json()["follow_up"]["events"]
    return fid, next(e for e in events if e["event_type"] == "CorrectionSubmitted")


def test_a_tampered_or_unsafe_stored_filename_is_never_served(client, people, officer_user, tmp_path):
    fid, event = evidence_case(client, people, officer_user)
    outside = tmp_path / "secret.png"
    outside.write_bytes(JPEG_BYTES + b"-OUTSIDE")
    original = db.session.get(FollowUpEvent, event["id"]).image_filename
    folder = client.application.config["PRIVATE_UPLOAD_FOLDER"]
    db_path = client.application.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    # Even if a stored row were corrupted, only a plain image file name inside the
    # private folder is ever read. (The immutability trigger is dropped on this
    # throw-away test database only, to simulate the corruption.)
    hostile = ["../" + outside.name, str(outside), "..\\secret.png", ".hidden.jpg", "x.html", "x.svg", "dir/../" + original, "missing.png"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TRIGGER IF EXISTS resolution_follow_up_events_immutable_update")
        for name in hostile:
            conn.execute("UPDATE resolution_follow_up_events SET image_filename = ? WHERE id = ?", (name, event["id"]))
            conn.commit()
            db.session.expire_all()
            response = client.get(image_url(fid, event["id"]), headers=bearer(people["chief"]))
            assert response.status_code == 404 and b"-OUTSIDE" not in response.data, name
    finally:
        conn.close()
    assert os.path.isfile(os.path.join(folder, original))  # the real photo was never touched


def test_correction_photos_are_not_reachable_through_the_public_uploads_route(client, people, officer_user):
    fid, event = evidence_case(client, people, officer_user)
    name = db.session.get(FollowUpEvent, event["id"]).image_filename
    private = client.application.config["PRIVATE_UPLOAD_FOLDER"]
    assert os.path.isfile(os.path.join(private, name))
    assert not os.path.exists(os.path.join(client.application.config["UPLOAD_FOLDER"], name))
    assert client.get(f"/uploads/{name}").status_code == 404
    assert client.get(f"/uploads/../{os.path.basename(private)}/{name}").status_code == 404
    # The stored file name never reaches a client, and no /uploads URL is offered for it.
    for who, base in (("chief", "chief-officer"), ("officer", "officers/me")):
        raw = client.get(f"/api/{base}/follow-ups/{fid}", headers=bearer(people[who])).get_data(as_text=True)
        assert name not in raw and f'"image_path": "/{base}/follow-ups/{fid}/events/{event["id"]}/image"' in raw.replace('":"', '": "')


def test_reading_correction_photos_changes_no_state_or_notifications(client, people, officer_user):
    from models.notification import Notification

    fid, event = evidence_case(client, people, officer_user)

    def snapshot():
        db.session.expire_all()
        follow_up = db.session.get(ResolutionFollowUp, fid)
        return (follow_up.status, follow_up.assigned_officer_id, follow_up.issue.status,
                FollowUpEvent.query.count(), ResolutionRating.query.count(), Notification.query.count(),
                follow_up.updated_at)

    before = snapshot()
    for _ in range(2):
        assert client.get(image_url(fid, event["id"]), headers=bearer(people["chief"])).status_code == 200
        assert client.get(image_url(fid, event["id"], "officer"), headers=bearer(people["officer"])).status_code == 200
        assert client.get(image_url(fid, event["id"]), headers=bearer(people["citizen"])).status_code == 403
    assert snapshot() == before


def token_for(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password}).get_json()["token"]
