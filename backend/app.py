import os
import sqlite3

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException

from config import Config, ConfigurationError, LOOPBACK_HOSTS, resolve_server_options
from database.db import db
from models.user import User
from models.complaint import Complaint
from models.civic_issue import CivicIssue
from models.notification import Notification
from models.ward import Ward, WardOfficerAssignment  # noqa: F401
from models.performance import (  # noqa: F401
    FOLLOW_UP_EVENT_TYPES,
    FOLLOW_UP_STATES,
    FollowUpEvent,
    ResolutionFollowUp,
    ResolutionRating,
)
from models.work_update import ALLOWED_WORK_UPDATE_STATUSES, IssueWorkUpdate  # noqa: F401
from models.resolution_review import (  # noqa: F401
    COMPLAINT_DISPOSITIONS,
    REVIEW_STATES,
    ResolutionReview,
    ResolutionReviewComplaintDisposition,
)
# Level 2 community tables - imported so db.create_all() below creates them.
# These are brand-new tables only; no existing table is altered.
from models.community import (  # noqa: F401
    CivicIssueStatusChange,
    ImpactScoreEvent,
    IssueComment,
    IssueSupport,
    IssueVerification,
)
from routes.auth import auth_bp
from routes.complaints import complaint_bp
from routes.officers import officer_bp
from routes.admin import admin_bp
from routes.notifications import notification_bp
from routes.community import community_bp
from routes.resolution_review import resolution_bp
from routes.wards import ward_bp
from routes.supervision import supervision_bp

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)

db.init_app(app)
jwt = JWTManager(app)


def migrate_complaint_location_columns():
    """Additive migration: add latitude/longitude columns to complaints
    and backfill them from the existing free-text `location` column.
    No-op if the columns already exist. Never drops data.

    Uses the app's actually-configured database URI (so tests pointed at
    a separate sqlite file, or a future non-default DATABASE_URL, are
    never confused with the real dev database)."""

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")

    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]

    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(complaints)")
        existing_columns = {row[1] for row in cur.fetchall()}

        if "latitude" not in existing_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN latitude FLOAT"
            )
        if "longitude" not in existing_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN longitude FLOAT"
            )

        cur.execute(
            "SELECT id, location FROM complaints WHERE latitude IS NULL"
        )
        rows = cur.fetchall()

        for complaint_id, location in rows:
            if not location:
                continue
            parts = [part.strip() for part in location.split(",")]
            if len(parts) != 2:
                continue
            try:
                lat, lng = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            cur.execute(
                "UPDATE complaints SET latitude = ?, longitude = ? WHERE id = ?",
                (lat, lng, complaint_id),
            )

        conn.commit()
    finally:
        conn.close()


def migrate_spam_moderation_columns():
    """Additive migration: add the spam/misreport moderation columns to
    complaints and users. No-op if the columns already exist. Never
    drops data. Same approach as migrate_complaint_location_columns."""

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")

    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]

    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(complaints)")
        complaint_columns = {row[1] for row in cur.fetchall()}

        if "ai_spam_flag" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN ai_spam_flag BOOLEAN NOT NULL DEFAULT 0"
            )
        if "ai_spam_reason" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN ai_spam_reason TEXT"
            )
        if "ai_spam_confidence" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN ai_spam_confidence VARCHAR(20)"
            )
        if "spam_review_status" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN spam_review_status VARCHAR(20) NOT NULL DEFAULT 'NotFlagged'"
            )
        if "spam_reviewed_by" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN spam_reviewed_by INTEGER"
            )
        if "spam_reviewed_at" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN spam_reviewed_at DATETIME"
            )

        cur.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cur.fetchall()}

        if "spam_count" not in user_columns:
            cur.execute(
                "ALTER TABLE users ADD COLUMN spam_count INTEGER NOT NULL DEFAULT 0"
            )
        if "is_suspended" not in user_columns:
            cur.execute(
                "ALTER TABLE users ADD COLUMN is_suspended BOOLEAN NOT NULL DEFAULT 0"
            )

        conn.commit()
    finally:
        conn.close()


def migrate_spam_reopen_columns():
    """Additive migration: add the reopen-for-review audit columns to
    complaints (who/when last sent an already-decided report back to
    Pending). No-op if the columns already exist. Never drops data."""

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")

    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]

    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(complaints)")
        complaint_columns = {row[1] for row in cur.fetchall()}

        if "spam_reopened_by" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN spam_reopened_by INTEGER"
            )
        if "spam_reopened_at" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN spam_reopened_at DATETIME"
            )

        conn.commit()
    finally:
        conn.close()


def migrate_issue_clustering_columns():
    """Additive migration: add the `issue_id` column linking a complaint
    to a CivicIssue. The civic_issues/notifications tables themselves are
    brand new and already created by db.create_all() above - this only
    needs to add a column to the pre-existing complaints table.
    No-op if the column already exists. Never drops data."""

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")

    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]

    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(complaints)")
        complaint_columns = {row[1] for row in cur.fetchall()}

        if "issue_id" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN issue_id INTEGER REFERENCES civic_issues(id)"
            )

        conn.commit()
    finally:
        conn.close()


def migrate_out_of_scope_rejection_columns():
    """Additive migration: add the out-of-scope rejection columns to
    complaints (a genuine complaint that is outside NMC/government
    jurisdiction - conceptually separate from spam moderation above).
    No-op if the columns already exist. Never drops data."""

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")

    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]

    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(complaints)")
        complaint_columns = {row[1] for row in cur.fetchall()}

        if "rejection_status" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN rejection_status VARCHAR(20) NOT NULL DEFAULT 'NotRejected'"
            )
        if "rejection_reason" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN rejection_reason VARCHAR(50)"
            )
        if "rejection_explanation" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN rejection_explanation TEXT"
            )
        if "rejected_by" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN rejected_by INTEGER"
            )
        if "rejected_at" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN rejected_at DATETIME"
            )
        if "rejection_reopened_by" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN rejection_reopened_by INTEGER"
            )
        if "rejection_reopened_at" not in complaint_columns:
            cur.execute(
                "ALTER TABLE complaints ADD COLUMN rejection_reopened_at DATETIME"
            )

        conn.commit()
    finally:
        conn.close()


LEGACY_RESOLUTION_REVIEWS_TABLE = "resolution_reviews_legacy_complaint_level"


def migrate_legacy_resolution_reviews_table():
    """Set aside the prototype's complaint-level ``resolution_reviews`` table.

    An earlier prototype stored reviews per complaint.  ``db.create_all()``
    never alters an existing table, so that layout would shadow the current
    issue-level table.  It is renamed (rows, indexes and data intact) so
    ``create_all`` can create the new table.  Must run before ``create_all``.
    Safe to rerun: it does nothing once the table has the issue-level layout,
    and it refuses to overwrite an existing legacy-named table.
    """

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(resolution_reviews)")
        columns = {row[1] for row in cur.fetchall()}
        if not columns or "issue_id" in columns:
            return
        if "complaint_id" not in columns:
            raise RuntimeError(
                "resolution_reviews has an unrecognised schema; refusing to modify it"
            )
        exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ?",
            (LEGACY_RESOLUTION_REVIEWS_TABLE,),
        ).fetchone()
        if exists:
            raise RuntimeError(
                f"Cannot set aside legacy resolution_reviews: "
                f"{LEGACY_RESOLUTION_REVIEWS_TABLE} already exists"
            )
        cur.execute(
            f"ALTER TABLE resolution_reviews RENAME TO {LEGACY_RESOLUTION_REVIEWS_TABLE}"
        )
        conn.commit()
    finally:
        conn.close()


def _create_value_guards(cur, table, column, allowed, label):
    """Reject values outside ``allowed`` at the database level.

    SQLite cannot add a CHECK constraint to an existing table, so insert and
    update triggers give both new and upgraded databases the same protection
    without rebuilding any table.
    """
    values = ", ".join("'" + value.replace("'", "''") + "'" for value in allowed)
    message = f"Invalid {label}"
    for suffix, event in (("insert", "INSERT"), ("update", f"UPDATE OF {column}")):
        cur.execute(
            f"CREATE TRIGGER IF NOT EXISTS {table}_valid_{column}_{suffix} "
            f"BEFORE {event} ON {table} "
            f"WHEN NEW.{column} NOT IN ({values}) "
            f"BEGIN SELECT RAISE(ABORT, '{message}'); END"
        )


def migrate_resolution_workflow_schema():
    """Apply additive, idempotent resolution-workflow schema upgrades.

    New tables come from ``db.create_all()``.  Existing databases only gain
    columns, indexes, and audit-protection triggers; no table is rebuilt,
    dropped, or rewritten beyond backfilling a valid revision default.
    """

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(civic_issues)")
        columns = {row[1] for row in cur.fetchall()}
        if "review_revision" not in columns:
            cur.execute(
                "ALTER TABLE civic_issues "
                "ADD COLUMN review_revision INTEGER NOT NULL DEFAULT 1"
            )
        cur.execute(
            "UPDATE civic_issues SET review_revision = 1 "
            "WHERE review_revision IS NULL OR review_revision < 1"
        )

        tables = {
            row[0] for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "issue_work_updates" in tables:
            cur.execute("PRAGMA table_info(issue_work_updates)")
            work_update_columns = {row[1] for row in cur.fetchall()}
            if "request_fingerprint" not in work_update_columns:
                cur.execute(
                    "ALTER TABLE issue_work_updates "
                    "ADD COLUMN request_fingerprint VARCHAR(64)"
                )
            _create_value_guards(
                cur, "issue_work_updates", "status",
                ALLOWED_WORK_UPDATE_STATUSES, "work update status",
            )

        if "resolution_reviews" in tables:
            cur.execute("PRAGMA table_info(resolution_reviews)")
            review_columns = {row[1] for row in cur.fetchall()}
            if "supersedes_review_id" not in review_columns:
                cur.execute(
                    "ALTER TABLE resolution_reviews "
                    "ADD COLUMN supersedes_review_id INTEGER REFERENCES resolution_reviews(id)"
                )
            if "stale_reason" not in review_columns:
                cur.execute("ALTER TABLE resolution_reviews ADD COLUMN stale_reason TEXT")
            if "stale_at" not in review_columns:
                cur.execute("ALTER TABLE resolution_reviews ADD COLUMN stale_at DATETIME")
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_resolution_reviews_pending_issue "
                "ON resolution_reviews(issue_id) WHERE state = 'Pending'"
            )
            _create_value_guards(
                cur, "resolution_reviews", "state", REVIEW_STATES, "resolution review state"
            )

        _create_value_guards(
            cur, "civic_issues", "status",
            ("Pending", "In Progress", "Pending Review", "Resolved"), "civic issue status",
        )

        if "resolution_review_complaint_dispositions" in tables:
            _create_value_guards(
                cur, "resolution_review_complaint_dispositions", "disposition",
                COMPLAINT_DISPOSITIONS, "complaint disposition",
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS "
                "resolution_dispositions_immutable_update "
                "BEFORE UPDATE ON resolution_review_complaint_dispositions "
                "BEGIN SELECT RAISE(ABORT, 'Resolution review dispositions are immutable'); END"
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS "
                "resolution_dispositions_immutable_delete "
                "BEFORE DELETE ON resolution_review_complaint_dispositions "
                "BEGIN SELECT RAISE(ABORT, 'Resolution review dispositions are immutable'); END"
            )
        conn.commit()
    finally:
        conn.close()


def migrate_ward_registry_schema():
    """Apply additive, idempotent protections for the ward registry tables.

    The tables themselves come from ``db.create_all()``; nothing is rebuilt,
    dropped, or seeded.  This adds what SQLAlchemy cannot express portably:
    a case-insensitive unique ward code, "at most one active assignment per
    ward and Officer" for databases whose table predates the index, an
    Officer-role check on new assignments, and triggers that make assignment
    history append-only (a row may only be *ended*, once) and keep wards from
    being deleted.
    """

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        tables = {
            row[0] for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "wards" in tables:
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_wards_code_nocase "
                "ON wards(code COLLATE NOCASE) WHERE code IS NOT NULL"
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS wards_no_delete BEFORE DELETE ON wards "
                "BEGIN SELECT RAISE(ABORT, 'Wards cannot be deleted; deactivate them instead'); END"
            )
        if "ward_officer_assignments" in tables:
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_ward_assignment_active_pair "
                "ON ward_officer_assignments(ward_id, officer_id) WHERE ended_at IS NULL"
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS ward_assignments_officer_only "
                "BEFORE INSERT ON ward_officer_assignments "
                "WHEN (SELECT role FROM users WHERE id = NEW.officer_id) IS NOT 'Officer' "
                "BEGIN SELECT RAISE(ABORT, 'Only Officers can be assigned to a ward'); END"
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS ward_assignments_no_delete "
                "BEFORE DELETE ON ward_officer_assignments "
                "BEGIN SELECT RAISE(ABORT, 'Ward assignment history is immutable'); END"
            )
            # The only permitted change: an active row gaining its end details,
            # exactly once. Every historical column is frozen.
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS ward_assignments_immutable_update "
                "BEFORE UPDATE ON ward_officer_assignments "
                "WHEN OLD.ended_at IS NOT NULL "
                "OR NEW.id IS NOT OLD.id "
                "OR NEW.ward_id IS NOT OLD.ward_id "
                "OR NEW.officer_id IS NOT OLD.officer_id "
                "OR NEW.assigned_by IS NOT OLD.assigned_by "
                "OR NEW.assigned_at IS NOT OLD.assigned_at "
                "OR NEW.reason IS NOT OLD.reason "
                "BEGIN SELECT RAISE(ABORT, 'Ward assignment history is immutable'); END"
            )
        conn.commit()
    finally:
        conn.close()


def migrate_performance_schema():
    """Additive, idempotent protections for ratings and follow-ups.

    Tables come from ``db.create_all()``.  This adds the database-level rules
    the API also enforces, so a direct SQL write cannot bypass them: rating
    scale and explanation rules, "only a Chief Officer rates only approved
    work and only its submitter", the single-chain revision indexes, valid
    follow-up states, and append-only (no update, no delete) history for
    ratings and follow-up events.
    """

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri.startswith("sqlite:///"):
        return

    db_path = db_uri[len("sqlite:///"):]
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        tables = {
            row[0] for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "resolution_ratings" in tables:
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_rating_one_original "
                "ON resolution_ratings(resolution_review_id) WHERE supersedes_rating_id IS NULL"
            )
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_rating_one_revision "
                "ON resolution_ratings(supersedes_rating_id) WHERE supersedes_rating_id IS NOT NULL"
            )
            rules = [
                ("stars_range", "NEW.stars NOT BETWEEN 1 AND 5", "Rating must be between 1 and 5 stars"),
                ("low_needs_explanation",
                 "NEW.stars <= 2 AND (NEW.explanation IS NULL OR trim(NEW.explanation) = '')",
                 "An explanation is required for a rating of 1 or 2 stars"),
                ("follow_up_flag",
                 "NEW.needs_follow_up IS NOT (NEW.stars <= 2)",
                 "needs_follow_up must match the rating"),
                ("chief_only",
                 "(SELECT role FROM users WHERE id = NEW.rated_by) IS NOT 'Chief Officer'",
                 "Only a Chief Officer can rate work"),
                ("approved_only",
                 "(SELECT state FROM resolution_reviews WHERE id = NEW.resolution_review_id) IS NOT 'Approved'",
                 "Only approved work can be rated"),
                ("submitter_only",
                 "NEW.rated_officer_id IS NOT (SELECT submitted_by FROM resolution_reviews WHERE id = NEW.resolution_review_id)",
                 "The rated officer must be the review submitter"),
            ]
            for name, condition, message in rules:
                cur.execute(
                    f"CREATE TRIGGER IF NOT EXISTS resolution_ratings_{name} "
                    f"BEFORE INSERT ON resolution_ratings WHEN {condition} "
                    f"BEGIN SELECT RAISE(ABORT, '{message}'); END"
                )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS resolution_ratings_immutable_update "
                "BEFORE UPDATE ON resolution_ratings "
                "BEGIN SELECT RAISE(ABORT, 'Rating history is immutable; submit a revision'); END"
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS resolution_ratings_immutable_delete "
                "BEFORE DELETE ON resolution_ratings "
                "BEGIN SELECT RAISE(ABORT, 'Rating history is immutable'); END"
            )
        if "resolution_follow_ups" in tables:
            _create_value_guards(
                cur, "resolution_follow_ups", "status", FOLLOW_UP_STATES, "follow-up status"
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS resolution_follow_ups_no_delete "
                "BEFORE DELETE ON resolution_follow_ups "
                "BEGIN SELECT RAISE(ABORT, 'Follow-up cases cannot be deleted'); END"
            )
            # The review and rating a case belongs to never change.
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS resolution_follow_ups_frozen_links "
                "BEFORE UPDATE ON resolution_follow_ups "
                "WHEN NEW.resolution_review_id IS NOT OLD.resolution_review_id "
                "OR NEW.rating_id IS NOT OLD.rating_id OR NEW.issue_id IS NOT OLD.issue_id "
                "OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at "
                "BEGIN SELECT RAISE(ABORT, 'A follow-up case cannot be re-linked'); END"
            )
        if "resolution_follow_up_events" in tables:
            _create_value_guards(
                cur, "resolution_follow_up_events", "event_type", FOLLOW_UP_EVENT_TYPES, "follow-up event"
            )
            _create_value_guards(
                cur, "resolution_follow_up_events", "to_status", FOLLOW_UP_STATES, "follow-up status"
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS resolution_follow_up_events_immutable_update "
                "BEFORE UPDATE ON resolution_follow_up_events "
                "BEGIN SELECT RAISE(ABORT, 'Follow-up history is immutable'); END"
            )
            cur.execute(
                "CREATE TRIGGER IF NOT EXISTS resolution_follow_up_events_immutable_delete "
                "BEFORE DELETE ON resolution_follow_up_events "
                "BEGIN SELECT RAISE(ABORT, 'Follow-up history is immutable'); END"
            )
        conn.commit()
    finally:
        conn.close()


with app.app_context():
    instance_path = os.path.join(os.path.dirname(__file__), "instance")
    os.makedirs(instance_path, exist_ok=True)
    migrate_legacy_resolution_reviews_table()
    db.create_all()
    migrate_complaint_location_columns()
    migrate_spam_moderation_columns()
    migrate_spam_reopen_columns()
    migrate_issue_clustering_columns()
    migrate_out_of_scope_rejection_columns()
    migrate_resolution_workflow_schema()
    migrate_ward_registry_schema()
    migrate_performance_schema()


@jwt.token_in_blocklist_loader
def check_if_user_is_suspended(jwt_header, jwt_payload):
    """Treats every token belonging to a suspended (or deleted) user as
    revoked. This runs automatically on every @jwt_required() route via
    Flask-JWT-Extended, so a suspension takes effect immediately for
    already-issued tokens without touching any individual route."""

    user = User.query.get(int(jwt_payload["sub"]))
    return user is None or user.is_suspended

app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(complaint_bp, url_prefix="/api/complaints")
app.register_blueprint(officer_bp, url_prefix="/api/officers")
app.register_blueprint(admin_bp, url_prefix="/api/admin")
app.register_blueprint(ward_bp, url_prefix="/api/admin")
app.register_blueprint(notification_bp, url_prefix="/api/notifications")
app.register_blueprint(community_bp, url_prefix="/api/community")
app.register_blueprint(resolution_bp, url_prefix="/api")
app.register_blueprint(supervision_bp, url_prefix="/api")


@app.errorhandler(413)
def handle_request_too_large(error):
    return jsonify({
        "message": f"Upload is too large. The maximum photo size is {app.config['MAX_UPLOAD_BYTES'] // (1024 * 1024)} MB."
    }), 413


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    return jsonify({"message": error.description or error.name}), error.code


@app.errorhandler(Exception)
def handle_unexpected_exception(error):
    app.logger.exception("Unhandled exception")
    return jsonify({"message": "Something went wrong on the server."}), 500


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def home():
    return {
        "message": "CivicPulse AI Backend Running 🚀"
    }


if __name__ == "__main__":
    # Defaults: 127.0.0.1, debug off. See resolve_server_options in config.py.
    try:
        host, port, debug = resolve_server_options(os.environ)
    except ConfigurationError as error:
        raise SystemExit(f"Configuration error: {error}")

    if host not in LOOPBACK_HOSTS:
        print(
            f"WARNING: listening on {host}:{port} - the API is reachable from "
            "other devices on your network."
        )

    app.run(host=host, port=port, debug=debug)
