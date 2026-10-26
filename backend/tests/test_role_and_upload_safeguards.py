"""Safeguards: uploads are served with nosniff, the last Admin cannot be demoted, role changes are
audited in the same transaction, and a Chief Officer cannot rate work they submitted themselves."""

import os
import sqlite3
import uuid
from unittest.mock import patch

import pytest

from database.db import db
from models.role_change import RoleChange
from models.user import User
from services.auth_service import hash_password
from tests.helpers import JPEG_BYTES
from tests.test_resolution_workflow import auth, create_complaint, submit_review, token


def db_file(app):
    return app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")


def make_user(email, role, password="password123"):
    user = User(name=email.split("@")[0], email=email, password_hash=hash_password(password), role=role)
    db.session.add(user)
    db.session.commit()
    return user


def set_role(client, bearer, user_id, role):
    return client.put(f"/api/admin/users/{user_id}/role", json={"role": role}, headers=auth(bearer))


def changes():
    db.session.expire_all()
    return [(c.target_user_id, c.changed_by, c.old_role, c.new_role) for c in RoleChange.query.order_by(RoleChange.id)]


# ---------------- /uploads ----------------

def test_uploads_are_served_with_nosniff(client, app):
    name = f"{uuid.uuid4().hex}_photo.jpg"
    with open(os.path.join(app.config["UPLOAD_FOLDER"], name), "wb") as handle:
        handle.write(JPEG_BYTES)
    response = client.get(f"/uploads/{name}")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Type"].startswith("image/jpeg")
    assert client.get("/uploads/does-not-exist.jpg").status_code == 404


# ---------------- last Admin ----------------

def test_the_only_admin_cannot_be_demoted_even_by_themselves(client, app, admin_user, citizen_user):
    admin_token = token(client, "admin@example.com", "admin123")
    response = set_role(client, admin_token, admin_user.id, "Citizen")
    assert response.status_code == 409 and "At least one active Admin" in response.get_json()["message"]
    db.session.expire_all()
    assert db.session.get(User, admin_user.id).role == "Admin"
    assert changes() == []  # a refused attempt leaves no audit row


def test_an_admin_can_be_demoted_while_another_active_admin_remains(client, admin_user):
    second = make_user("second.admin@example.com", "Admin")
    admin_token = token(client, "admin@example.com", "admin123")
    assert set_role(client, admin_token, second.id, "Officer").status_code == 200
    assert changes() == [(second.id, admin_user.id, "Admin", "Officer")]
    # Now the first Admin is the last one.
    assert set_role(client, admin_token, admin_user.id, "Citizen").status_code == 409
    assert len(changes()) == 1


def test_a_suspended_admin_does_not_count_as_the_remaining_admin(client, admin_user):
    other = make_user("suspended.admin@example.com", "Admin")
    other.is_suspended = True
    db.session.commit()
    admin_token = token(client, "admin@example.com", "admin123")
    assert set_role(client, admin_token, admin_user.id, "Citizen").status_code == 409
    db.session.expire_all()
    assert db.session.get(User, admin_user.id).role == "Admin"


def test_two_admins_cannot_both_be_demoted_one_after_the_other(client, admin_user):
    second = make_user("second.admin@example.com", "Admin")
    first_token = token(client, "admin@example.com", "admin123")
    second_token = token(client, "second.admin@example.com", "password123")
    assert set_role(client, first_token, second.id, "Citizen").status_code == 200
    # The demoted Admin has lost the right to act, and the remaining one is protected.
    assert set_role(client, second_token, admin_user.id, "Citizen").status_code == 403
    assert set_role(client, first_token, admin_user.id, "Citizen").status_code == 409
    assert [c[3] for c in changes()] == ["Citizen"]


# ---------------- audit ----------------

def test_applied_role_changes_are_recorded_with_who_old_and_new(client, admin_user, officer_user):
    admin_token = token(client, "admin@example.com", "admin123")
    assert set_role(client, admin_token, officer_user.id, "Chief Officer").status_code == 200
    assert set_role(client, admin_token, officer_user.id, "Officer").status_code == 200
    assert changes() == [
        (officer_user.id, admin_user.id, "Officer", "Chief Officer"),
        (officer_user.id, admin_user.id, "Chief Officer", "Officer"),
    ]
    assert RoleChange.query.first().created_at is not None


def test_refused_or_unchanged_requests_leave_no_audit_row(client, admin_user, officer_user, citizen_user):
    admin_token = token(client, "admin@example.com", "admin123")
    citizen_token = token(client, "citizen@example.com", "password123")
    assert set_role(client, admin_token, officer_user.id, "Officer").status_code == 200  # already an Officer
    assert set_role(client, admin_token, officer_user.id, "Superuser").status_code == 400
    assert client.put(f"/api/admin/users/{officer_user.id}/role", json={}, headers=auth(admin_token)).status_code == 400
    assert client.put(f"/api/admin/users/{officer_user.id}/role", json={"role": ["Admin"]}, headers=auth(admin_token)).status_code == 400
    assert set_role(client, admin_token, 99999, "Officer").status_code == 404
    assert set_role(client, citizen_token, officer_user.id, "Admin").status_code == 403
    assert client.put(f"/api/admin/users/{officer_user.id}/role", json={"role": "Admin"}).status_code == 401
    db.session.expire_all()
    assert db.session.get(User, officer_user.id).role == "Officer"
    assert changes() == []


def test_if_the_audit_row_cannot_be_written_the_role_does_not_change(client, admin_user, officer_user):
    admin_token = token(client, "admin@example.com", "admin123")

    def broken(**kwargs):
        raise RuntimeError("audit store unavailable")

    with patch("routes.admin.RoleChange", broken):
        response = set_role(client, admin_token, officer_user.id, "Chief Officer")
    assert response.status_code == 500 and "Could not change the role" in response.get_json()["message"]
    db.session.expire_all()
    assert db.session.get(User, officer_user.id).role == "Officer"
    assert changes() == []
    assert set_role(client, admin_token, officer_user.id, "Chief Officer").status_code == 200  # recovers
    assert len(changes()) == 1


def test_the_audit_trail_cannot_be_edited_or_deleted(client, app, admin_user, officer_user):
    admin_token = token(client, "admin@example.com", "admin123")
    set_role(client, admin_token, officer_user.id, "Chief Officer")
    conn = sqlite3.connect(db_file(app))
    try:
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            conn.execute("UPDATE role_changes SET new_role = 'Citizen'")
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            conn.execute("DELETE FROM role_changes")
    finally:
        conn.close()
    assert len(changes()) == 1


def test_chief_officer_role_assignment_stays_admin_only(client, admin_user, officer_user, citizen_user, chief_officer_user):
    chief_token = token(client, "chief@example.com", "chief123")
    officer_token = token(client, "officer@example.com", "officer123")
    for bearer in (chief_token, officer_token):
        assert set_role(client, bearer, citizen_user.id, "Chief Officer").status_code == 403
    assert changes() == []


# ---------------- no self-rating ----------------

def promoted_submitter(client, admin_user, officer_user, chief_officer_user):
    citizen_token = token(client, "citizen@example.com", "password123")
    officer_token = token(client, "officer@example.com", "officer123")
    chief_token = token(client, "chief@example.com", "chief123")
    complaint = create_complaint(client, citizen_token)
    review_id = submit_review(client, officer_token, complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]["id"]
    approved = client.put(f"/api/chief-officer/resolution-reviews/{review_id}/decision",
                          json={"decision": "Approved"}, headers=auth(chief_token))
    assert approved.status_code == 200
    admin_token = token(client, "admin@example.com", "admin123")
    assert set_role(client, admin_token, officer_user.id, "Chief Officer").status_code == 200
    return review_id, token(client, "officer@example.com", "officer123"), chief_token


def test_a_chief_officer_cannot_rate_work_they_submitted_before_promotion(
    client, citizen_user, officer_user, admin_user, chief_officer_user
):
    review_id, promoted_token, chief_token = promoted_submitter(client, admin_user, officer_user, chief_officer_user)
    own = client.post(f"/api/chief-officer/resolution-reviews/{review_id}/rating", json={"stars": 5}, headers=auth(promoted_token))
    assert own.status_code == 403 and "submitted yourself" in own.get_json()["message"]
    from models.performance import ResolutionRating
    assert ResolutionRating.query.count() == 0
    # Another Chief Officer can still rate it.
    other = client.post(f"/api/chief-officer/resolution-reviews/{review_id}/rating", json={"stars": 4}, headers=auth(chief_token))
    assert other.status_code == 201


def test_the_database_also_refuses_a_self_rating(app, client, citizen_user, officer_user, admin_user, chief_officer_user):
    review_id, _, _ = promoted_submitter(client, admin_user, officer_user, chief_officer_user)
    conn = sqlite3.connect(db_file(app))
    try:
        with pytest.raises(sqlite3.DatabaseError, match="cannot rate work they submitted"):
            conn.execute(
                "INSERT INTO resolution_ratings (resolution_review_id, rated_officer_id, rated_by, stars, "
                "needs_follow_up, created_at) VALUES (?, ?, ?, 5, 0, '2026-01-01 00:00:00')",
                (review_id, officer_user.id, officer_user.id),
            )
    finally:
        conn.close()
