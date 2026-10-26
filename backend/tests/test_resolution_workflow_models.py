import os
import sqlite3
import tempfile

import pytest
from sqlalchemy.exc import IntegrityError

from app import (
    LEGACY_RESOLUTION_REVIEWS_TABLE,
    app as flask_app,
    migrate_legacy_resolution_reviews_table,
    migrate_resolution_workflow_schema,
)
from database.db import db
from models.civic_issue import CivicIssue
from models.complaint import Complaint
from models.resolution_review import (
    ResolutionReview,
    ResolutionReviewComplaintDisposition,
)
from models.work_update import IssueWorkUpdate


def make_issue():
    issue = CivicIssue(
        category="Road Infrastructure",
        latitude=20.0,
        longitude=73.0,
        report_count=1,
    )
    db.session.add(issue)
    db.session.flush()
    return issue


def make_complaint(user_id, issue_id):
    complaint = Complaint(
        title="Pothole",
        description="Large pothole",
        category="Road Infrastructure",
        latitude=20.0,
        longitude=73.0,
        user_id=user_id,
        issue_id=issue_id,
    )
    db.session.add(complaint)
    db.session.flush()
    return complaint


def test_issue_work_update_keeps_shared_issue_and_optional_complaint_context(app, officer_user):
    with app.app_context():
        issue = make_issue()
        complaint = make_complaint(officer_user.id, issue.id)
        update = IssueWorkUpdate(
            issue_id=issue.id,
            complaint_id=complaint.id,
            officer_id=officer_user.id,
            note="Crew cleared the obstruction at this reported location.",
            idempotency_key="field-visit-1",
        )
        db.session.add(update)
        db.session.commit()

        saved = db.session.get(IssueWorkUpdate, update.id)
        assert saved.issue_id == issue.id
        assert saved.complaint_id == complaint.id
        assert saved.created_at is not None
        assert saved.status == "In Progress"


def test_work_update_retry_key_is_unique_per_officer(app, officer_user):
    with app.app_context():
        issue = make_issue()
        db.session.add(IssueWorkUpdate(
            issue_id=issue.id,
            officer_id=officer_user.id,
            note="First request",
            idempotency_key="retry-key",
        ))
        db.session.commit()

        db.session.add(IssueWorkUpdate(
            issue_id=issue.id,
            officer_id=officer_user.id,
            note="Retried request",
            idempotency_key="retry-key",
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_review_snapshots_issue_revision_and_dispositions_are_unique(app, officer_user):
    with app.app_context():
        issue = make_issue()
        complaint = make_complaint(officer_user.id, issue.id)
        review = ResolutionReview(
            issue_id=issue.id,
            submitted_by=officer_user.id,
            completion_note="Road surface repaired and site checked.",
            image_filename="validated-final.jpg",
            issue_revision=issue.review_revision,
        )
        db.session.add(review)
        db.session.flush()
        db.session.add(ResolutionReviewComplaintDisposition(
            resolution_review_id=review.id,
            complaint_id=complaint.id,
            disposition="Addressed",
            note="Repair covers the reported pothole.",
        ))
        db.session.commit()

        assert review.state == "Pending"
        assert review.issue_revision == 1

        db.session.add(ResolutionReviewComplaintDisposition(
            resolution_review_id=review.id,
            complaint_id=complaint.id,
            disposition="Duplicate Covered",
            note="Duplicate row must not be accepted.",
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_submitted_dispositions_are_immutable_in_the_database(app, officer_user):
    with app.app_context():
        issue = make_issue()
        complaint = make_complaint(officer_user.id, issue.id)
        review = ResolutionReview(
            issue_id=issue.id,
            submitted_by=officer_user.id,
            completion_note="Completed repair.",
            image_filename="evidence.jpg",
            issue_revision=issue.review_revision,
        )
        db.session.add(review)
        db.session.flush()
        disposition = ResolutionReviewComplaintDisposition(
            resolution_review_id=review.id,
            complaint_id=complaint.id,
            disposition="Addressed",
            note="Covered by the repair.",
        )
        db.session.add(disposition)
        db.session.commit()

        disposition.note = "Changed after submission"
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        disposition = db.session.get(ResolutionReviewComplaintDisposition, disposition.id)
        db.session.delete(disposition)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_sqlite_foreign_keys_are_enabled_for_a_new_sqlalchemy_connection(app):
    with app.app_context():
        db.engine.dispose()
        with db.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_resolution_migration_adds_revision_without_losing_existing_issue_data():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE civic_issues ("
            "id INTEGER PRIMARY KEY, category VARCHAR(100) NOT NULL, "
            "location_label VARCHAR(255), latitude FLOAT NOT NULL, "
            "longitude FLOAT NOT NULL, status VARCHAR(50) NOT NULL, "
            "report_count INTEGER NOT NULL, ai_summary TEXT, "
            "created_at DATETIME, updated_at DATETIME)"
        )
        conn.execute(
            "CREATE TABLE complaints (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO complaints (id, title) VALUES (4, 'Existing complaint')")
        conn.execute(
            "INSERT INTO civic_issues "
            "(id, category, latitude, longitude, status, report_count) "
            "VALUES (7, 'Drainage', 20.1, 73.8, 'In Progress', 4)"
        )
        conn.commit()
        conn.close()

        previous_uri = flask_app.config["SQLALCHEMY_DATABASE_URI"]
        flask_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{path}"
        try:
            migrate_resolution_workflow_schema()
            migrate_resolution_workflow_schema()
        finally:
            flask_app.config["SQLALCHEMY_DATABASE_URI"] = previous_uri

        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT id, category, status, report_count, review_revision "
            "FROM civic_issues WHERE id = 7"
        ).fetchone()
        complaint = conn.execute("SELECT id, title FROM complaints WHERE id = 4").fetchone()
        conn.close()
        assert row == (7, "Drainage", "In Progress", 4, 1)
        assert complaint == (4, "Existing complaint")
    finally:
        os.remove(path)


def test_database_rejects_unknown_workflow_values(app, officer_user):
    issue = make_issue()
    complaint = make_complaint(officer_user.id, issue.id)
    review = ResolutionReview(
        issue_id=issue.id, submitted_by=officer_user.id, completion_note="Done",
        image_filename="final.jpg", issue_revision=issue.review_revision,
    )
    db.session.add(review)
    db.session.commit()

    statements = [
        ("INSERT INTO resolution_reviews (issue_id, submitted_by, completion_note, image_filename, "
         "issue_revision, state, submitted_at) VALUES (:i, :u, 'n', 'f', 1, 'Bogus', CURRENT_TIMESTAMP)"),
        "UPDATE resolution_reviews SET state = 'Bogus' WHERE id = :r",
        ("INSERT INTO resolution_review_complaint_dispositions (resolution_review_id, complaint_id, "
         "disposition, note, created_at) VALUES (:r, :c, 'Bogus', 'n', CURRENT_TIMESTAMP)"),
        ("INSERT INTO issue_work_updates (issue_id, officer_id, status, note, created_at) "
         "VALUES (:i, :u, 'Resolved', 'n', CURRENT_TIMESTAMP)"),
        "UPDATE civic_issues SET status = 'Bogus' WHERE id = :i",
    ]
    params = {"i": issue.id, "u": officer_user.id, "r": review.id, "c": complaint.id}
    for statement in statements:
        with pytest.raises(IntegrityError):
            db.session.execute(db.text(statement), params)
        db.session.rollback()


LEGACY_REVIEWS_DDL = (
    "CREATE TABLE resolution_reviews (id INTEGER PRIMARY KEY, complaint_id INTEGER NOT NULL, "
    "submitted_by INTEGER NOT NULL, completion_note TEXT NOT NULL, decision VARCHAR(20))"
)


def _run_legacy_migration(path):
    previous_uri = flask_app.config["SQLALCHEMY_DATABASE_URI"]
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{path}"
    try:
        migrate_legacy_resolution_reviews_table()
    finally:
        flask_app.config["SQLALCHEMY_DATABASE_URI"] = previous_uri


def test_legacy_complaint_level_reviews_table_is_renamed_with_rows_preserved(tmp_path):
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.execute(LEGACY_REVIEWS_DDL)
    conn.execute("CREATE INDEX ix_resolution_reviews_complaint_id ON resolution_reviews (complaint_id)")
    conn.execute("INSERT INTO resolution_reviews VALUES (1, 4, 2, 'Old prototype note', 'Approved')")
    conn.commit()
    conn.close()

    _run_legacy_migration(path)
    _run_legacy_migration(path)  # rerun is a no-op

    conn = sqlite3.connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    rows = conn.execute(f"SELECT * FROM {LEGACY_RESOLUTION_REVIEWS_TABLE}").fetchall()
    conn.close()
    assert "resolution_reviews" not in tables
    assert rows == [(1, 4, 2, "Old prototype note", "Approved")]


def test_issue_level_reviews_table_is_left_alone_by_legacy_migration(tmp_path):
    path = str(tmp_path / "current.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE resolution_reviews (id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL)")
    conn.commit()
    conn.close()

    _run_legacy_migration(path)

    conn = sqlite3.connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert tables == {"resolution_reviews"}


def test_legacy_migration_refuses_to_overwrite_an_existing_legacy_name(tmp_path):
    path = str(tmp_path / "conflict.db")
    conn = sqlite3.connect(path)
    conn.execute(LEGACY_REVIEWS_DDL)
    conn.execute(f"CREATE TABLE {LEGACY_RESOLUTION_REVIEWS_TABLE} (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="already exists"):
        _run_legacy_migration(path)

    conn = sqlite3.connect(path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(resolution_reviews)")}
    conn.close()
    assert "complaint_id" in columns
