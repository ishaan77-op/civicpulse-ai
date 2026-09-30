import io
import json
from unittest.mock import patch

from database.db import db
from models.community import ImpactScoreEvent, IssueComment
from models.notification import Notification
from services import impact_score_service as impact


def get_token(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


POTHOLE_AI_RESULT = {
    "category": "Road Infrastructure",
    "priority": "High",
    "department": "Roads Dept",
    "visual_observation": "A large pothole in the middle of a paved road.",
    "summary": "Large pothole blocking traffic on the main road.",
    "spam_flag": False,
    "spam_reason": "",
    "spam_confidence": "",
}

STREETLIGHT_AI_RESULT = {
    "category": "Street Lighting",
    "priority": "Low",
    "department": "Electrical Dept",
    "visual_observation": "A streetlight pole that is not lit.",
    "summary": "Streetlight has been out for several nights.",
    "spam_flag": False,
    "spam_reason": "",
    "spam_confidence": "",
}

SPAM_AI_RESULT = {
    **POTHOLE_AI_RESULT,
    "spam_flag": True,
    "spam_reason": "Image shows a selfie, not a road.",
    "spam_confidence": "High",
}


def submit_complaint(client, token, ai_result=POTHOLE_AI_RESULT, latitude=20.0110, longitude=73.7903,
                     title="Big pothole", description=None):
    with patch("routes.complaints.analyze_complaint") as mock_ai:
        mock_ai.return_value = ai_result
        res = client.post(
            "/api/complaints/",
            data={
                "title": title,
                "description": description or ai_result["summary"],
                "latitude": str(latitude),
                "longitude": str(longitude),
                "address": "College Road, Nashik, Maharashtra",
                "image": (io.BytesIO(b"fake-image-bytes"), "photo.jpg"),
            },
            content_type="multipart/form-data",
            headers=auth(token),
        )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["complaint"]


def register_citizen(client, email, name="Another Citizen"):
    client.post("/api/auth/register", json={"name": name, "email": email, "password": "password123"})
    return get_token(client, email, "password123")


def score(client, token):
    return client.get("/api/community/me/impact", headers=auth(token)).get_json()["impact_score"]


def create_public_issue(client):
    token = get_token(client, "citizen@example.com", "password123")
    complaint = submit_complaint(client, token)
    return token, complaint["civic_issue"]["id"]


# ==========================================
# Support
# ==========================================

def test_support_once_duplicate_blocked_and_count_accurate(client, citizen_user):
    reporter_token, issue_id = create_public_issue(client)
    other = register_citizen(client, "second@example.com")

    first = client.post(f"/api/community/issues/{issue_id}/support", headers=auth(other))
    assert first.status_code == 201
    assert first.get_json()["community"]["supporters"] == 1

    for _ in range(3):
        again = client.post(f"/api/community/issues/{issue_id}/support", headers=auth(other))
        assert again.status_code == 200
        assert again.get_json()["community"]["supporters"] == 1

    client.post(f"/api/community/issues/{issue_id}/support", headers=auth(reporter_token))
    detail = client.get(f"/api/community/issues/{issue_id}", headers=auth(other)).get_json()["issue"]
    assert detail["community"]["supporters"] == 2
    assert detail["viewer"]["supported"] is True


def test_remove_support_and_toggle_cannot_farm_points(client, citizen_user):
    _, issue_id = create_public_issue(client)
    other = register_citizen(client, "second@example.com")

    client.post(f"/api/community/issues/{issue_id}/support", headers=auth(other))
    assert score(client, other) == impact.WEIGHTS["ISSUE_SUPPORT"]

    removed = client.delete(f"/api/community/issues/{issue_id}/support", headers=auth(other))
    assert removed.status_code == 200
    assert removed.get_json()["community"]["supporters"] == 0
    assert removed.get_json()["community"]["viewer"]["supported"] is False

    for _ in range(3):
        client.post(f"/api/community/issues/{issue_id}/support", headers=auth(other))
        client.delete(f"/api/community/issues/{issue_id}/support", headers=auth(other))

    assert score(client, other) == impact.WEIGHTS["ISSUE_SUPPORT"]


def test_client_supplied_counts_and_user_ids_are_ignored(client, citizen_user):
    _, issue_id = create_public_issue(client)
    other = register_citizen(client, "second@example.com")

    res = client.post(
        f"/api/community/issues/{issue_id}/support",
        json={"user_id": 999, "supporters": 500, "points": 1000, "impact_score": 1000},
        headers=auth(other),
    )
    assert res.get_json()["community"]["supporters"] == 1
    assert score(client, other) == impact.WEIGHTS["ISSUE_SUPPORT"]


def test_cannot_support_resolved_issue(client, citizen_user, officer_user):
    _, issue_id = create_public_issue(client)
    officer = get_token(client, "officer@example.com", "officer123")
    client.put(f"/api/officers/issues/{issue_id}/status", json={"status": "Resolved"}, headers=auth(officer))
    other = register_citizen(client, "second@example.com")

    res = client.post(f"/api/community/issues/{issue_id}/support", headers=auth(other))
    assert res.status_code == 400


# ==========================================
# Comments
# ==========================================

def test_create_and_list_comment_is_anonymous(client, citizen_user):
    reporter_token, issue_id = create_public_issue(client)

    res = client.post(
        f"/api/community/issues/{issue_id}/comments",
        json={"content": "Still present today, it got bigger after the rain."},
        headers=auth(reporter_token),
    )
    assert res.status_code == 201

    other = register_citizen(client, "second@example.com")
    listing = client.get(f"/api/community/issues/{issue_id}/comments", headers=auth(other))
    body = listing.get_json()
    assert body["total"] == 1
    comment = body["comments"][0]
    assert comment["author"]["handle"].startswith("Citizen #")
    assert comment["author"]["is_you"] is False
    assert comment["can_edit"] is False

    raw = json.dumps(body)
    assert "citizen@example.com" not in raw
    assert "Test Citizen" not in raw
    assert "user_id" not in raw


def test_anonymous_handle_is_stable(client, citizen_user):
    token, issue_id = create_public_issue(client)
    first = client.post(f"/api/community/issues/{issue_id}/comments", json={"content": "First observation"},
                        headers=auth(token)).get_json()["comment"]
    second = client.post(f"/api/community/issues/{issue_id}/comments", json={"content": "Second observation"},
                         headers=auth(token)).get_json()["comment"]
    me = client.get("/api/community/me/impact", headers=auth(token)).get_json()
    assert first["author"]["handle"] == second["author"]["handle"] == me["handle"]


def test_empty_and_oversized_comments_rejected(client, citizen_user):
    token, issue_id = create_public_issue(client)
    for content in ["", "   ", "\n\n", None]:
        res = client.post(f"/api/community/issues/{issue_id}/comments", json={"content": content}, headers=auth(token))
        assert res.status_code == 400
    res = client.post(f"/api/community/issues/{issue_id}/comments", json={"content": "x" * 1001}, headers=auth(token))
    assert res.status_code == 400


def test_comment_html_is_stored_as_plain_text(client, citizen_user):
    token, issue_id = create_public_issue(client)
    payload = "<script>alert('x')</script> still here"
    client.post(f"/api/community/issues/{issue_id}/comments", json={"content": payload}, headers=auth(token))
    listing = client.get(f"/api/community/issues/{issue_id}/comments", headers=auth(token))
    assert listing.mimetype == "application/json"
    # Returned verbatim as data; the React client renders it as text, never HTML.
    assert listing.get_json()["comments"][0]["content"] == payload


def test_only_author_can_edit_or_delete_comment(client, citizen_user):
    token, issue_id = create_public_issue(client)
    comment_id = client.post(f"/api/community/issues/{issue_id}/comments", json={"content": "Original text"},
                             headers=auth(token)).get_json()["comment"]["id"]
    other = register_citizen(client, "second@example.com")

    assert client.put(f"/api/community/comments/{comment_id}", json={"content": "hijacked"},
                      headers=auth(other)).status_code == 404
    assert client.delete(f"/api/community/comments/{comment_id}", headers=auth(other)).status_code == 404

    edited = client.put(f"/api/community/comments/{comment_id}", json={"content": "Corrected text"}, headers=auth(token))
    assert edited.status_code == 200
    assert edited.get_json()["comment"]["edited"] is True

    assert client.delete(f"/api/community/comments/{comment_id}", headers=auth(token)).status_code == 200
    listing = client.get(f"/api/community/issues/{issue_id}/comments", headers=auth(token)).get_json()
    assert listing["total"] == 0


def test_comment_rate_limit_and_duplicate_blocked(client, citizen_user):
    token, issue_id = create_public_issue(client)
    url = f"/api/community/issues/{issue_id}/comments"

    assert client.post(url, json={"content": "Same comment"}, headers=auth(token)).status_code == 201
    assert client.post(url, json={"content": "Same comment"}, headers=auth(token)).status_code == 409

    for i in range(4):
        assert client.post(url, json={"content": f"Update number {i}"}, headers=auth(token)).status_code == 201
    assert client.post(url, json={"content": "One too many"}, headers=auth(token)).status_code == 429


def test_comment_requires_authentication(client, citizen_user):
    _, issue_id = create_public_issue(client)
    res = client.post(f"/api/community/issues/{issue_id}/comments", json={"content": "anonymous drive-by"})
    assert res.status_code == 401


def test_comment_points_once_per_issue(client, citizen_user):
    token, issue_id = create_public_issue(client)
    before = score(client, token)
    url = f"/api/community/issues/{issue_id}/comments"
    client.post(url, json={"content": "Still present this morning near the bus stop."}, headers=auth(token))
    client.post(url, json={"content": "Still present this evening, cars swerving around it."}, headers=auth(token))
    client.post(url, json={"content": "ok"}, headers=auth(token))
    assert score(client, token) == before + impact.WEIGHTS["CONSTRUCTIVE_COMMENT"]


# ==========================================
# Moderation
# ==========================================

def test_report_and_moderate_comment(client, citizen_user, officer_user):
    token, issue_id = create_public_issue(client)
    before = score(client, token)
    comment_id = client.post(
        f"/api/community/issues/{issue_id}/comments",
        json={"content": "A long enough comment to earn a constructive point."},
        headers=auth(token),
    ).get_json()["comment"]["id"]
    assert score(client, token) == before + 1

    other = register_citizen(client, "second@example.com")
    assert client.post(f"/api/community/comments/{comment_id}/report", json={"reason": "abusive"},
                       headers=auth(other)).status_code == 200

    # Citizens can't moderate.
    assert client.get("/api/community/moderation/comments", headers=auth(other)).status_code == 403
    assert client.put(f"/api/community/moderation/comments/{comment_id}", json={"decision": "Remove", "reason": "x"},
                      headers=auth(other)).status_code == 403

    officer = get_token(client, "officer@example.com", "officer123")
    queue = client.get("/api/community/moderation/comments", headers=auth(officer)).get_json()
    assert queue["total"] == 1
    assert queue["comments"][0]["moderation"]["flag_source"] == "Citizen report"

    # Removal needs a reason (auditable).
    assert client.put(f"/api/community/moderation/comments/{comment_id}", json={"decision": "Remove"},
                      headers=auth(officer)).status_code == 400
    assert client.put(f"/api/community/moderation/comments/{comment_id}",
                      json={"decision": "Remove", "reason": "Abusive language"},
                      headers=auth(officer)).status_code == 200

    assert client.get(f"/api/community/issues/{issue_id}/comments", headers=auth(other)).get_json()["total"] == 0
    assert score(client, token) == before  # the comment's point was withdrawn

    stored = db.session.get(IssueComment, comment_id)
    assert stored.moderated_by == officer_user.id
    assert stored.moderation_reason == "Abusive language"


def test_link_comment_is_flagged_for_review_but_not_hidden(client, citizen_user):
    token, issue_id = create_public_issue(client)
    client.post(f"/api/community/issues/{issue_id}/comments",
                json={"content": "cheap deals at http://spam.example"}, headers=auth(token))
    listing = client.get(f"/api/community/issues/{issue_id}/comments", headers=auth(token)).get_json()
    assert listing["total"] == 1
    assert db.session.query(IssueComment).first().moderation_status == "Flagged"


# ==========================================
# Verification
# ==========================================

def test_verify_change_and_count_accuracy(client, citizen_user):
    _, issue_id = create_public_issue(client)
    other = register_citizen(client, "second@example.com")
    url = f"/api/community/issues/{issue_id}/verify"

    first = client.post(url, json={"verification_type": "STILL_EXISTS"}, headers=auth(other))
    assert first.status_code == 201
    assert first.get_json()["community"]["verification"]["still_exists"] == 1

    duplicate = client.post(url, json={"verification_type": "STILL_EXISTS"}, headers=auth(other))
    assert duplicate.status_code == 200
    assert duplicate.get_json()["community"]["verification"]["still_exists"] == 1

    changed = client.post(url, json={"verification_type": "RESOLVED"}, headers=auth(other)).get_json()
    assert changed["community"]["verification"] == {"still_exists": 0, "resolved": 1, "not_sure": 0}
    assert changed["community"]["viewer"]["verification"] == "RESOLVED"

    # Verification points are once per issue no matter how often it changes.
    assert score(client, other) == impact.WEIGHTS["ISSUE_VERIFICATION"]


def test_invalid_verification_rejected(client, citizen_user):
    token, issue_id = create_public_issue(client)
    res = client.post(f"/api/community/issues/{issue_id}/verify", json={"verification_type": "OFFICIALLY_CLOSED"},
                      headers=auth(token))
    assert res.status_code == 400


def test_community_verification_never_changes_official_status(client, citizen_user):
    _, issue_id = create_public_issue(client)
    for i in range(5):
        voter = register_citizen(client, f"voter{i}@example.com")
        client.post(f"/api/community/issues/{issue_id}/verify", json={"verification_type": "RESOLVED"},
                    headers=auth(voter))
    detail = client.get(f"/api/community/issues/{issue_id}", headers=auth(voter)).get_json()["issue"]
    assert detail["official"]["status"] == "Pending"
    assert detail["community"]["verification"]["resolved"] == 5


# ==========================================
# Impact score
# ==========================================

def test_valid_complaint_scores_once_per_issue(client, citizen_user):
    token = get_token(client, "citizen@example.com", "password123")
    submit_complaint(client, token)
    assert score(client, token) == impact.WEIGHTS["VALID_COMPLAINT"]

    # A duplicate report of the same issue by the same citizen earns nothing.
    submit_complaint(client, token, title="Pothole again")
    assert score(client, token) == impact.WEIGHTS["VALID_COMPLAINT"]


def test_corroborating_report_earns_evidence_points_and_notification(client, citizen_user):
    first = get_token(client, "citizen@example.com", "password123")
    submit_complaint(client, first)
    second = register_citizen(client, "second@example.com")
    submit_complaint(client, second, latitude=20.0111, longitude=73.7904)

    assert score(client, second) == impact.WEIGHTS["VALID_COMPLAINT"] + impact.WEIGHTS["USEFUL_EVIDENCE"]
    notifications = client.get("/api/notifications/", headers=auth(second)).get_json()["notifications"]
    assert len(notifications) == 1
    assert "grouped with an existing civic issue" in notifications[0]["message"]


def test_ai_flag_alone_never_scores_or_penalizes(client, citizen_user):
    token = get_token(client, "citizen@example.com", "password123")
    submit_complaint(client, token, ai_result=SPAM_AI_RESULT)
    assert score(client, token) == 0


def test_confirmed_spam_penalty_and_reopen_reversal(client, citizen_user, officer_user):
    token = get_token(client, "citizen@example.com", "password123")
    complaint = submit_complaint(client, token, ai_result=SPAM_AI_RESULT)
    officer = get_token(client, "officer@example.com", "officer123")

    client.put(f"/api/officers/spam/{complaint['id']}/review", json={"decision": "Confirmed"}, headers=auth(officer))
    assert score(client, token) == impact.WEIGHTS["CONFIRMED_SPAM"]

    client.put(f"/api/officers/spam/{complaint['id']}/reopen", headers=auth(officer))
    assert score(client, token) == 0

    # Human reviewer now says it was genuine -> valid complaint points.
    client.put(f"/api/officers/spam/{complaint['id']}/review", json={"decision": "Rejected"}, headers=auth(officer))
    assert score(client, token) == impact.WEIGHTS["VALID_COMPLAINT"]

    # Reopened and confirmed after all: penalty applies once, and the
    # complaint's own award is withdrawn.
    client.put(f"/api/officers/spam/{complaint['id']}/reopen", headers=auth(officer))
    client.put(f"/api/officers/spam/{complaint['id']}/review", json={"decision": "Confirmed"}, headers=auth(officer))
    assert score(client, token) == impact.WEIGHTS["CONFIRMED_SPAM"]

    types = [e.event_type for e in ImpactScoreEvent.query.order_by(ImpactScoreEvent.id).all()]
    assert types.count("CONFIRMED_SPAM") == 2
    assert "CONFIRMED_SPAM_REVERSED" in types
    assert "VALID_COMPLAINT_REVOKED" in types


def test_resolution_reward_once_and_notifications(client, citizen_user, officer_user):
    token, issue_id = create_public_issue(client)
    supporter = register_citizen(client, "second@example.com")
    client.post(f"/api/community/issues/{issue_id}/support", headers=auth(supporter))
    officer = get_token(client, "officer@example.com", "officer123")
    before = score(client, token)

    url = f"/api/officers/issues/{issue_id}/status"
    client.put(url, json={"status": "Resolved"}, headers=auth(officer))
    client.put(url, json={"status": "Resolved"}, headers=auth(officer))  # no-op re-save
    client.put(url, json={"status": "In Progress"}, headers=auth(officer))
    client.put(url, json={"status": "Resolved"}, headers=auth(officer))

    assert score(client, token) == before + impact.WEIGHTS["ISSUE_RESOLVED"]
    # Supporting doesn't make you the reporter of a resolved issue.
    assert score(client, supporter) == impact.WEIGHTS["ISSUE_SUPPORT"]

    reporter_notes = Notification.query.filter_by(user_id=citizen_user.id).all()
    assert len(reporter_notes) == 3  # Resolved, In Progress, Resolved - not the no-op
    supporter_notes = client.get("/api/notifications/", headers=auth(supporter)).get_json()["notifications"]
    assert len(supporter_notes) == 3

    timeline = client.get(f"/api/community/issues/{issue_id}", headers=auth(token)).get_json()["issue"]["timeline"]
    official = [e for e in timeline if e["kind"] == "official"]
    assert [e["label"] for e in official] == [
        "Official status changed to Resolved",
        "Official status changed to In Progress",
        "Official status changed to Resolved",
    ]


def test_daily_cap_limits_support_points(client, citizen_user, monkeypatch):
    monkeypatch.setitem(impact.DAILY_CAPS, "ISSUE_SUPPORT", 2)
    token = get_token(client, "citizen@example.com", "password123")
    issue_ids = []
    for i in range(3):
        c = submit_complaint(client, token, ai_result=STREETLIGHT_AI_RESULT,
                             latitude=20.0 + i * 0.05, longitude=73.7 + i * 0.05, title=f"Light {i}")
        issue_ids.append(c["civic_issue"]["id"])
    voter = register_citizen(client, "second@example.com")
    for issue_id in issue_ids:
        assert client.post(f"/api/community/issues/{issue_id}/support", headers=auth(voter)).status_code == 201
    assert score(client, voter) == 2


def test_impact_endpoints_are_private_to_self(client, citizen_user):
    token = get_token(client, "citizen@example.com", "password123")
    submit_complaint(client, token)
    me = client.get("/api/community/me/impact", headers=auth(token)).get_json()
    assert me["stats"]["issues_reported"] == 1
    assert "email" not in json.dumps(me)
    activity = client.get("/api/community/me/activity", headers=auth(token)).get_json()["events"]
    assert activity[0]["event_type"] == "VALID_COMPLAINT"
    # No endpoint accepts another user's id.
    assert client.get("/api/community/users/1/impact", headers=auth(token)).status_code == 404


# ==========================================
# Feed
# ==========================================

def test_feed_hides_spam_and_out_of_scope_and_is_privacy_safe(client, citizen_user, officer_user):
    token = get_token(client, "citizen@example.com", "password123")
    genuine = submit_complaint(client, token, title="My house number 42 is next to it")
    submit_complaint(client, token, ai_result={**SPAM_AI_RESULT, "category": "Drainage"},
                     latitude=20.05, longitude=73.75, title="Pending spam")
    out_of_scope = submit_complaint(client, token, ai_result=STREETLIGHT_AI_RESULT,
                                    latitude=20.08, longitude=73.72, title="Society light")
    officer = get_token(client, "officer@example.com", "officer123")
    client.put(f"/api/complaints/{out_of_scope['id']}/reject", json={"reason": "Private Property"},
               headers=auth(officer))

    feed = client.get("/api/community/feed", headers=auth(token)).get_json()
    assert [i["id"] for i in feed["issues"]] == [genuine["civic_issue"]["id"]]

    raw = json.dumps(feed)
    for secret in ["citizen@example.com", "Test Citizen", "house number 42", "user_id", "password"]:
        assert secret not in raw

    card = feed["issues"][0]
    assert card["official"]["priority"] == "High"
    assert card["official"]["department"] == "Roads Dept"
    assert card["image_url"].startswith("/uploads/")

    # Direct access to a non-public issue is also refused.
    spam_issue = client.get("/api/community/feed?status=Pending&q=Drainage", headers=auth(token)).get_json()
    assert spam_issue["total"] == 0


def test_feed_pagination(client, citizen_user):
    token = get_token(client, "citizen@example.com", "password123")
    for i in range(5):
        submit_complaint(client, token, latitude=20.0 + i * 0.05, longitude=73.7 + i * 0.05, title=f"Pothole {i}")
    page1 = client.get("/api/community/feed?per_page=2&page=1", headers=auth(token)).get_json()
    page3 = client.get("/api/community/feed?per_page=2&page=3", headers=auth(token)).get_json()
    assert page1["total"] == 5 and len(page1["issues"]) == 2 and page1["has_more"] is True
    assert len(page3["issues"]) == 1 and page3["has_more"] is False
    capped = client.get("/api/community/feed?per_page=1000", headers=auth(token)).get_json()
    assert capped["per_page"] == 30


def test_feed_sorts(client, citizen_user):
    token = get_token(client, "citizen@example.com", "password123")
    near = submit_complaint(client, token, latitude=20.0110, longitude=73.7903, title="Near pothole")
    far = submit_complaint(client, token, ai_result=STREETLIGHT_AI_RESULT, latitude=20.10, longitude=73.90,
                           title="Far light")
    near_id, far_id = near["civic_issue"]["id"], far["civic_issue"]["id"]

    nearby = client.get("/api/community/feed?sort=nearby&lat=20.0111&lng=73.7904&radius_km=2",
                        headers=auth(token)).get_json()
    assert [i["id"] for i in nearby["issues"]] == [near_id]
    assert nearby["issues"][0]["distance_m"] < 50
    assert client.get("/api/community/feed?sort=nearby", headers=auth(token)).status_code == 400

    priority = client.get("/api/community/feed?sort=priority", headers=auth(token)).get_json()
    assert [i["id"] for i in priority["issues"]] == [near_id]  # Low-priority light excluded

    for i in range(2):
        voter = register_citizen(client, f"voter{i}@example.com")
        client.post(f"/api/community/issues/{far_id}/support", headers=auth(voter))
    trending = client.get("/api/community/feed?sort=trending", headers=auth(token)).get_json()
    assert trending["issues"][0]["id"] == far_id
    assert trending["issues"][0]["trending"]["recent_activity"]["supports"] == 2

    assert client.get("/api/community/feed?sort=viral", headers=auth(token)).status_code == 400


def test_non_public_issue_detail_and_engagement_refused(client, citizen_user):
    token = get_token(client, "citizen@example.com", "password123")
    flagged = submit_complaint(client, token, ai_result=SPAM_AI_RESULT)
    issue_id = flagged["civic_issue"]["id"]
    other = register_citizen(client, "second@example.com")
    assert client.get(f"/api/community/issues/{issue_id}", headers=auth(other)).status_code == 404
    assert client.post(f"/api/community/issues/{issue_id}/support", headers=auth(other)).status_code == 404
    assert client.post(f"/api/community/issues/{issue_id}/comments", json={"content": "hi there"},
                       headers=auth(other)).status_code == 404


# ==========================================
# Authorization
# ==========================================

def test_staff_cannot_cast_community_signals_but_can_comment(client, citizen_user, officer_user, admin_user):
    _, issue_id = create_public_issue(client)
    for email, password in [("officer@example.com", "officer123"), ("admin@example.com", "admin123")]:
        staff = get_token(client, email, password)
        assert client.post(f"/api/community/issues/{issue_id}/support", headers=auth(staff)).status_code == 403
        assert client.post(f"/api/community/issues/{issue_id}/verify", json={"verification_type": "RESOLVED"},
                           headers=auth(staff)).status_code == 403
        res = client.post(f"/api/community/issues/{issue_id}/comments",
                          json={"content": "NMC team scheduled for Monday."}, headers=auth(staff))
        assert res.status_code == 201
        assert res.get_json()["comment"]["author"] == {"handle": "NMC Official", "is_official": True, "is_you": True}


def test_community_analytics_admin_only(client, citizen_user, officer_user, admin_user):
    create_public_issue(client)
    citizen = get_token(client, "citizen@example.com", "password123")
    officer = get_token(client, "officer@example.com", "officer123")
    admin = get_token(client, "admin@example.com", "admin123")
    assert client.get("/api/community/analytics", headers=auth(citizen)).status_code == 403
    assert client.get("/api/community/analytics", headers=auth(officer)).status_code == 403
    res = client.get("/api/community/analytics", headers=auth(admin))
    assert res.status_code == 200
    summary = res.get_json()["summary"]
    assert summary["public_civic_issues"] == 1
    assert summary["average_impact_score"] == impact.WEIGHTS["VALID_COMPLAINT"]


def test_officer_issue_list_includes_community_signal_and_dispute(client, citizen_user, officer_user):
    _, issue_id = create_public_issue(client)
    officer = get_token(client, "officer@example.com", "officer123")
    client.put(f"/api/officers/issues/{issue_id}/status", json={"status": "Resolved"}, headers=auth(officer))
    for i in range(3):
        voter = register_citizen(client, f"voter{i}@example.com")
        client.post(f"/api/community/issues/{issue_id}/verify", json={"verification_type": "STILL_EXISTS"},
                    headers=auth(voter))

    issues = client.get("/api/officers/issues", headers=auth(officer)).get_json()["issues"]
    signal = issues[0]["community"]
    assert signal["verification"]["still_exists"] == 3
    assert signal["disputed"] is True

    citizen = get_token(client, "citizen@example.com", "password123")
    assert client.get(f"/api/community/issues/{issue_id}/intelligence", headers=auth(citizen)).status_code == 403
    intel = client.get(f"/api/community/issues/{issue_id}/intelligence", headers=auth(officer)).get_json()
    assert intel["disputed"] is True


def test_suspended_user_cannot_engage(client, citizen_user):
    _, issue_id = create_public_issue(client)
    other = register_citizen(client, "second@example.com")
    from models.user import User
    user = User.query.filter_by(email="second@example.com").first()
    user.is_suspended = True
    db.session.commit()
    assert client.post(f"/api/community/issues/{issue_id}/support", headers=auth(other)).status_code == 401
