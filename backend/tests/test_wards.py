"""Ward registry and officer-assignment history (admin-only foundation)."""

import os
import sqlite3
import tempfile

import pytest
from sqlalchemy.exc import IntegrityError

from app import app as flask_app, migrate_ward_registry_schema
from database.db import db
from models.user import User
from models.ward import Ward, WardOfficerAssignment
from services.auth_service import hash_password
from tests.test_resolution_workflow import create_complaint, token

BASE = "/api/admin/wards"


def bearer(value):
    return {"Authorization": f"Bearer {value}"}


def login(client, email, password):
    return token(client, email, password)


@pytest.fixture
def tokens(client, citizen_user, officer_user, admin_user, chief_officer_user):
    return {
        "admin": login(client, "admin@example.com", "admin123"),
        "officer": login(client, "officer@example.com", "officer123"),
        "citizen": login(client, "citizen@example.com", "password123"),
        "chief": login(client, "chief@example.com", "chief123"),
    }


@pytest.fixture
def second_officer(app):
    user = User(name="Second Officer", email="officer2@example.com",
                password_hash=hash_password("officer456"), role="Officer")
    db.session.add(user)
    db.session.commit()
    return user


def make_ward(client, admin, name="Test Ward A", **extra):
    response = client.post(BASE, json={"name": name, **extra}, headers=bearer(admin))
    assert response.status_code == 201, response.get_json()
    return response.get_json()["ward"]


def assign(client, admin, ward_id, officer_id, **extra):
    return client.post(f"{BASE}/{ward_id}/assignments", json={"officer_id": officer_id, **extra}, headers=bearer(admin))


# ==========================================
# Authorization
# ==========================================

def test_every_management_endpoint_is_admin_only(client, tokens, officer_user):
    ward = make_ward(client, tokens["admin"])
    assignment = assign(client, tokens["admin"], ward["id"], officer_user.id).get_json()["assignment"]
    calls = [
        ("get", BASE, None),
        ("post", BASE, {"name": "X"}),
        ("put", f"{BASE}/{ward['id']}", {"name": "Y"}),
        ("put", f"{BASE}/{ward['id']}/deactivate", None),
        ("put", f"{BASE}/{ward['id']}/activate", None),
        ("get", f"{BASE}/{ward['id']}/assignments", None),
        ("post", f"{BASE}/{ward['id']}/assignments", {"officer_id": officer_user.id}),
        ("put", f"{BASE}/{ward['id']}/assignments/{assignment['id']}/end", {}),
    ]
    for role in ("officer", "citizen", "chief"):
        for method, url, body in calls:
            response = getattr(client, method)(url, json=body, headers=bearer(tokens[role]))
            assert response.status_code == 403, (role, method, url)
    for method, url, body in calls:
        assert getattr(client, method)(url, json=body).status_code == 401, (method, url)

    # Nothing changed as a result of the refused calls.
    assert Ward.query.count() == 1
    assert Ward.query.first().name == "Test Ward A" and Ward.query.first().is_active
    assert WardOfficerAssignment.query.filter_by(ended_at=None).count() == 1


# ==========================================
# Wards
# ==========================================

def test_registry_starts_empty_nothing_is_seeded(client, tokens):
    assert client.get(BASE, headers=bearer(tokens["admin"])).get_json() == {"wards": []}
    assert Ward.query.count() == 0


def test_create_list_and_update_wards(client, tokens):
    admin = tokens["admin"]
    created = make_ward(client, admin, name="  Ward One  ", code="w-1", source="Entered from municipal circular")
    assert created["name"] == "Ward One"
    assert created["code"] == "w-1" and created["is_active"] is True
    assert created["source"] == "Entered from municipal circular"
    assert created["active_assignment_count"] == 0

    make_ward(client, admin, name="Ward Two")  # code and source are optional
    listed = client.get(BASE, headers=bearer(admin)).get_json()["wards"]
    assert [w["name"] for w in listed] == ["Ward One", "Ward Two"]

    updated = client.put(f"{BASE}/{created['id']}", json={"name": "Ward 1 (renamed)", "source": None},
                         headers=bearer(admin))
    assert updated.status_code == 200
    ward = updated.get_json()["ward"]
    assert ward["name"] == "Ward 1 (renamed)" and ward["source"] is None and ward["code"] == "w-1"


def test_ward_validation_and_duplicate_codes(client, tokens):
    admin = tokens["admin"]
    make_ward(client, admin, name="Ward One", code="W-1")
    for body in ({}, {"name": "   "}, {"name": 5}, {"name": "x" * 121}, {"name": "ok", "code": "c" * 33},
                 {"name": "ok", "source": "s" * 256}):
        assert client.post(BASE, json=body, headers=bearer(admin)).status_code == 400, body
    assert client.post(BASE, data="not json", headers=bearer(admin)).status_code == 400
    # Codes are unique regardless of case; names are not forced unique.
    assert client.post(BASE, json={"name": "Other", "code": "w-1"}, headers=bearer(admin)).status_code == 409
    assert client.post(BASE, json={"name": "Ward One"}, headers=bearer(admin)).status_code == 201
    other = make_ward(client, admin, name="Third", code="W-3")
    assert client.put(f"{BASE}/{other['id']}", json={"code": "w-1"}, headers=bearer(admin)).status_code == 409
    assert client.put(f"{BASE}/{other['id']}", json={"code": "w-3"}, headers=bearer(admin)).status_code == 200  # own code
    assert client.put(f"{BASE}/{other['id']}", json={"name": ""}, headers=bearer(admin)).status_code == 400
    assert client.put(f"{BASE}/{other['id']}", json={}, headers=bearer(admin)).status_code == 400
    assert client.put(f"{BASE}/9999", json={"name": "x"}, headers=bearer(admin)).status_code == 404


def test_deactivate_keeps_the_ward_and_its_history(client, tokens, officer_user):
    admin = tokens["admin"]
    ward = make_ward(client, admin)
    assign(client, admin, ward["id"], officer_user.id, reason="Initial responsibility")

    refused = client.put(f"{BASE}/{ward['id']}", json={"is_active": False}, headers=bearer(admin))
    assert refused.status_code == 400  # state changes only through the dedicated endpoints

    deactivated = client.put(f"{BASE}/{ward['id']}/deactivate", headers=bearer(admin))
    assert deactivated.status_code == 200
    body = deactivated.get_json()["ward"]
    assert body["is_active"] is False and body["deactivated_at"]
    # Assignments are not silently ended or removed by deactivation.
    assert body["active_assignment_count"] == 1
    history = client.get(f"{BASE}/{ward['id']}/assignments", headers=bearer(admin)).get_json()["assignments"]
    assert len(history) == 1 and history[0]["is_active"] is True

    assert client.put(f"{BASE}/{ward['id']}/deactivate", headers=bearer(admin)).status_code == 200  # idempotent
    inactive_only = client.get(f"{BASE}?active=false", headers=bearer(admin)).get_json()["wards"]
    assert [w["id"] for w in inactive_only] == [ward["id"]]

    reactivated = client.put(f"{BASE}/{ward['id']}/activate", headers=bearer(admin)).get_json()["ward"]
    assert reactivated["is_active"] is True and reactivated["deactivated_at"] is None
    assert client.put(f"{BASE}/9999/deactivate", headers=bearer(admin)).status_code == 404


def test_wards_cannot_be_deleted_even_directly(client, tokens):
    ward = make_ward(client, tokens["admin"])
    with pytest.raises(IntegrityError):
        db.session.execute(db.text("DELETE FROM wards WHERE id = :i"), {"i": ward["id"]})
    db.session.rollback()
    assert Ward.query.count() == 1


# ==========================================
# Assignments
# ==========================================

def test_assign_and_list_history(client, tokens, officer_user, admin_user):
    admin = tokens["admin"]
    ward = make_ward(client, admin)
    response = assign(client, admin, ward["id"], officer_user.id, reason="  Covers this ward  ")
    assert response.status_code == 201
    row = response.get_json()["assignment"]
    assert row["officer"] == {"id": officer_user.id, "name": officer_user.name, "email": officer_user.email,
                              "role": "Officer", "is_suspended": False}
    assert row["assigned_by"] == admin_user.id
    assert row["reason"] == "Covers this ward"
    assert row["is_active"] is True and row["ended_at"] is None and row["assigned_at"]

    listing = client.get(f"{BASE}/{ward['id']}/assignments", headers=bearer(admin)).get_json()
    assert listing["ward"]["active_assignment_count"] == 1
    assert [a["id"] for a in listing["assignments"]] == [row["id"]]


def test_only_existing_unsuspended_officers_can_be_assigned(client, tokens, citizen_user, admin_user,
                                                           chief_officer_user, officer_user):
    admin = tokens["admin"]
    ward = make_ward(client, admin)
    for target in (citizen_user, admin_user, chief_officer_user):
        refused = assign(client, admin, ward["id"], target.id)
        assert refused.status_code == 400, target.role
        assert "Officer role" in refused.get_json()["message"]
    assert assign(client, admin, ward["id"], 99999).status_code == 404
    for bad in ("1", None, True, 1.5, [1]):
        assert client.post(f"{BASE}/{ward['id']}/assignments", json={"officer_id": bad},
                           headers=bearer(admin)).status_code == 400, bad
    assert client.post(f"{BASE}/{ward['id']}/assignments", json={}, headers=bearer(admin)).status_code == 400
    assert client.post(f"{BASE}/{ward['id']}/assignments", json={"officer_id": officer_user.id, "reason": "r" * 501},
                       headers=bearer(admin)).status_code == 400
    assert assign(client, admin, 9999, officer_user.id).status_code == 404

    officer_user.is_suspended = True
    db.session.commit()
    assert assign(client, admin, ward["id"], officer_user.id).status_code == 400
    assert WardOfficerAssignment.query.count() == 0


def test_inactive_wards_reject_new_assignments(client, tokens, officer_user):
    admin = tokens["admin"]
    ward = make_ward(client, admin)
    client.put(f"{BASE}/{ward['id']}/deactivate", headers=bearer(admin))
    refused = assign(client, admin, ward["id"], officer_user.id)
    assert refused.status_code == 409 and "inactive" in refused.get_json()["message"]
    assert WardOfficerAssignment.query.count() == 0


def test_duplicate_active_assignment_is_rejected_but_other_shapes_are_allowed(
    client, tokens, officer_user, second_officer
):
    admin = tokens["admin"]
    ward_a, ward_b = make_ward(client, admin, name="A"), make_ward(client, admin, name="B")
    assert assign(client, admin, ward_a["id"], officer_user.id).status_code == 201
    duplicate = assign(client, admin, ward_a["id"], officer_user.id)
    assert duplicate.status_code == 409 and "already actively assigned" in duplicate.get_json()["message"]
    # Cardinality is not restricted: several officers per ward, several wards per officer.
    assert assign(client, admin, ward_a["id"], second_officer.id).status_code == 201
    assert assign(client, admin, ward_b["id"], officer_user.id).status_code == 201
    assert WardOfficerAssignment.query.filter_by(ended_at=None).count() == 3


def test_ending_an_assignment_preserves_history_and_allows_reassignment(
    client, tokens, officer_user, admin_user
):
    admin = tokens["admin"]
    ward = make_ward(client, admin)
    first = assign(client, admin, ward["id"], officer_user.id, reason="Original").get_json()["assignment"]
    url = f"{BASE}/{ward['id']}/assignments/{first['id']}/end"

    ended = client.put(url, json={"reason": "Moved to another team"}, headers=bearer(admin))
    assert ended.status_code == 200
    row = ended.get_json()["assignment"]
    assert row["is_active"] is False and row["ended_at"] and row["ended_by"] == admin_user.id
    assert row["end_reason"] == "Moved to another team"
    assert row["assigned_at"] == first["assigned_at"] and row["reason"] == "Original"

    again = client.put(url, json={"reason": "overwrite"}, headers=bearer(admin))
    assert again.status_code == 409
    db.session.expire_all()
    stored = db.session.get(WardOfficerAssignment, first["id"])
    assert stored.end_reason == "Moved to another team"  # not overwritten

    second = assign(client, admin, ward["id"], officer_user.id)  # allowed again after ending
    assert second.status_code == 201
    history = client.get(f"{BASE}/{ward['id']}/assignments", headers=bearer(admin)).get_json()["assignments"]
    assert [a["id"] for a in history] == [second.get_json()["assignment"]["id"], first["id"]]
    assert [a["is_active"] for a in history] == [True, False]

    assert client.put(f"{BASE}/{ward['id']}/assignments/9999/end", json={}, headers=bearer(admin)).status_code == 404
    other_ward = make_ward(client, admin, name="Elsewhere")
    mismatched = client.put(f"{BASE}/{other_ward['id']}/assignments/{first['id']}/end", json={}, headers=bearer(admin))
    assert mismatched.status_code == 404  # an assignment can only be ended through its own ward


def test_history_survives_officer_demotion_and_suspension(client, tokens, officer_user):
    admin = tokens["admin"]
    ward = make_ward(client, admin)
    assign(client, admin, ward["id"], officer_user.id)
    client.put(f"/api/admin/users/{officer_user.id}/role", json={"role": "Citizen"}, headers=bearer(admin))
    officer_user.is_suspended = True
    db.session.commit()

    history = client.get(f"{BASE}/{ward['id']}/assignments", headers=bearer(admin)).get_json()["assignments"]
    assert len(history) == 1 and history[0]["is_active"] is True  # record untouched
    assert history[0]["officer"]["role"] == "Citizen" and history[0]["officer"]["is_suspended"] is True


# ==========================================
# Database-level guarantees
# ==========================================

def test_assignment_history_cannot_be_edited_or_deleted_in_the_database(client, tokens, officer_user, second_officer):
    admin = tokens["admin"]
    ward = make_ward(client, admin)
    active = assign(client, admin, ward["id"], officer_user.id, reason="Keep").get_json()["assignment"]
    ended = assign(client, admin, ward["id"], second_officer.id).get_json()["assignment"]
    client.put(f"{BASE}/{ward['id']}/assignments/{ended['id']}/end", json={}, headers=bearer(admin))

    forbidden = [
        ("DELETE FROM ward_officer_assignments WHERE id = :a", {"a": active["id"]}),
        ("DELETE FROM ward_officer_assignments WHERE id = :a", {"a": ended["id"]}),
        ("UPDATE ward_officer_assignments SET reason = 'edited' WHERE id = :a", {"a": active["id"]}),
        ("UPDATE ward_officer_assignments SET officer_id = :o WHERE id = :a", {"a": active["id"], "o": second_officer.id}),
        ("UPDATE ward_officer_assignments SET assigned_by = :o WHERE id = :a", {"a": active["id"], "o": second_officer.id}),
        ("UPDATE ward_officer_assignments SET assigned_at = '2000-01-01' WHERE id = :a", {"a": active["id"]}),
        ("UPDATE ward_officer_assignments SET ward_id = 999 WHERE id = :a", {"a": active["id"]}),
        # An already-ended row is frozen, including re-opening it or rewriting its end details.
        ("UPDATE ward_officer_assignments SET ended_at = NULL WHERE id = :a", {"a": ended["id"]}),
        ("UPDATE ward_officer_assignments SET end_reason = 'edited' WHERE id = :a", {"a": ended["id"]}),
        ("UPDATE ward_officer_assignments SET ended_by = :o WHERE id = :a", {"a": ended["id"], "o": officer_user.id}),
    ]
    for statement, params in forbidden:
        with pytest.raises(IntegrityError):
            db.session.execute(db.text(statement), params)
        db.session.rollback()
    assert WardOfficerAssignment.query.count() == 2


def test_database_enforces_officer_only_and_one_active_pair(client, tokens, officer_user, citizen_user):
    ward = make_ward(client, tokens["admin"])
    insert = ("INSERT INTO ward_officer_assignments (ward_id, officer_id, assigned_by, assigned_at) "
              "VALUES (:w, :o, :o, CURRENT_TIMESTAMP)")
    with pytest.raises(IntegrityError):
        db.session.execute(db.text(insert), {"w": ward["id"], "o": citizen_user.id})
    db.session.rollback()

    db.session.execute(db.text(insert), {"w": ward["id"], "o": officer_user.id})
    db.session.commit()
    with pytest.raises(IntegrityError):
        db.session.execute(db.text(insert), {"w": ward["id"], "o": officer_user.id})
    db.session.rollback()

    ended_at = "UPDATE ward_officer_assignments SET ended_at = CURRENT_TIMESTAMP, ended_by = :o"
    db.session.execute(db.text(ended_at), {"o": officer_user.id})  # ending is the one allowed change
    db.session.execute(db.text(insert), {"w": ward["id"], "o": officer_user.id})  # a new period may start
    db.session.commit()
    assert WardOfficerAssignment.query.count() == 2


def test_duplicate_codes_differing_only_by_case_are_rejected_by_the_database(client, tokens):
    make_ward(client, tokens["admin"], name="One", code="AB-1")
    with pytest.raises(IntegrityError):
        db.session.execute(db.text(
            "INSERT INTO wards (name, code, is_active, created_at, updated_at) "
            "VALUES ('Dup', 'ab-1', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    db.session.rollback()


# ==========================================
# Concurrency (second connection stands in for a concurrent request)
# ==========================================

def _other_connection(timeout=0.2):
    return sqlite3.connect(db.engine.url.database, timeout=timeout)


def test_ward_deactivated_just_before_the_assignment_write_is_refused(client, tokens, officer_user):
    import routes.wards as wards_module

    ward = make_ward(client, tokens["admin"])
    real_lock = wards_module._lock_ward

    def lock_after_concurrent_deactivation(ward_id, require_active=False):
        other = _other_connection(timeout=5)
        other.execute("UPDATE wards SET is_active = 0 WHERE id = ?", (ward_id,))
        other.commit()
        other.close()
        return real_lock(ward_id, require_active)

    from unittest.mock import patch
    with patch.object(wards_module, "_lock_ward", lock_after_concurrent_deactivation):
        response = assign(client, tokens["admin"], ward["id"], officer_user.id)
    assert response.status_code == 409
    assert WardOfficerAssignment.query.count() == 0


def test_a_competing_writer_is_blocked_while_an_assignment_is_being_checked(client, tokens, officer_user):
    import routes.wards as wards_module
    from unittest.mock import patch

    ward = make_ward(client, tokens["admin"])
    real_lock = wards_module._lock_ward
    outcome = []

    def lock_then_try_competing_insert(ward_id, require_active=False):
        locked = real_lock(ward_id, require_active)
        try:
            other = _other_connection()
            other.execute(
                "INSERT INTO ward_officer_assignments (ward_id, officer_id, assigned_by, assigned_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (ward_id, officer_user.id, officer_user.id))
            other.commit()
            outcome.append("committed")
        except sqlite3.OperationalError:
            outcome.append("blocked")
        return locked

    with patch.object(wards_module, "_lock_ward", lock_then_try_competing_insert):
        response = assign(client, tokens["admin"], ward["id"], officer_user.id)
    assert outcome == ["blocked"]
    assert response.status_code == 201
    assert WardOfficerAssignment.query.filter_by(ended_at=None).count() == 1


# ==========================================
# Migration safety
# ==========================================

def _run_ward_migration(path):
    previous = flask_app.config["SQLALCHEMY_DATABASE_URI"]
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{path}"
    try:
        migrate_ward_registry_schema()
    finally:
        flask_app.config["SQLALCHEMY_DATABASE_URI"] = previous


def test_ward_migration_is_additive_rerunnable_and_preserves_existing_rows():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, role VARCHAR(20));"
            "INSERT INTO users VALUES (1, 'Officer'), (2, 'Admin'), (3, 'Citizen');"
            "CREATE TABLE complaints (id INTEGER PRIMARY KEY, title TEXT);"
            "INSERT INTO complaints VALUES (7, 'Existing complaint');"
            # Tables as an earlier create_all would have left them: no protective triggers yet.
            "CREATE TABLE wards (id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, code VARCHAR(32));"
            "INSERT INTO wards VALUES (1, 'Existing ward', 'E-1');"
            "CREATE TABLE ward_officer_assignments (id INTEGER PRIMARY KEY, ward_id INTEGER NOT NULL, "
            "officer_id INTEGER NOT NULL, assigned_by INTEGER NOT NULL, assigned_at DATETIME NOT NULL, "
            "reason TEXT, ended_at DATETIME, ended_by INTEGER, end_reason TEXT);"
            "INSERT INTO ward_officer_assignments (ward_id, officer_id, assigned_by, assigned_at) "
            "VALUES (1, 1, 2, '2026-01-01');"
        )
        conn.commit()
        conn.close()

        _run_ward_migration(path)
        _run_ward_migration(path)  # safe to run again

        conn = sqlite3.connect(path)
        objects = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('index','trigger')")}
        assert {"uq_wards_code_nocase", "uq_ward_assignment_active_pair", "wards_no_delete",
                "ward_assignments_officer_only", "ward_assignments_no_delete",
                "ward_assignments_immutable_update"} <= objects
        assert conn.execute("SELECT id, name, code FROM wards").fetchall() == [(1, "Existing ward", "E-1")]
        assert conn.execute("SELECT ward_id, officer_id FROM ward_officer_assignments").fetchall() == [(1, 1)]
        assert conn.execute("SELECT title FROM complaints").fetchall() == [("Existing complaint",)]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM ward_officer_assignments")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO ward_officer_assignments (ward_id, officer_id, assigned_by, assigned_at) "
                         "VALUES (1, 3, 2, '2026-02-01')")  # user 3 is a Citizen
        conn.close()
    finally:
        os.remove(path)


def test_ward_migration_skips_databases_without_ward_tables():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        _run_ward_migration(path)
        conn = sqlite3.connect(path)
        assert [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")] == ["users"]
        conn.close()
    finally:
        os.remove(path)


# ==========================================
# No change to existing behavior
# ==========================================

def test_wards_and_assignments_do_not_change_officer_access(client, tokens, officer_user, second_officer):
    citizen = tokens["citizen"]
    complaint = create_complaint(client, citizen)
    officer = tokens["officer"]
    other_officer = login(client, "officer2@example.com", "officer456")

    def officer_view(bearer_token):
        listing = client.get("/api/officers/complaints", headers=bearer(bearer_token)).get_json()
        issues = client.get("/api/officers/issues", headers=bearer(bearer_token)).get_json()
        stats = client.get("/api/officers/stats", headers=bearer(bearer_token)).get_json()
        detail = client.get(f"/api/complaints/{complaint['id']}", headers=bearer(bearer_token)).status_code
        return [c["id"] for c in listing["complaints"]], [i["id"] for i in issues["issues"]], stats["total_complaints"], detail

    baseline = officer_view(officer)
    assert baseline == ([complaint["id"]], [complaint["civic_issue"]["id"]], 1, 200)  # empty registry

    ward = make_ward(client, tokens["admin"])
    assign(client, tokens["admin"], ward["id"], officer_user.id)
    assert officer_view(officer) == baseline
    # An officer with no ward at all still sees the municipality-wide queue (FR-2.1 unchanged).
    assert officer_view(other_officer) == baseline
