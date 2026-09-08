import os
import sqlite3

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException

from config import Config
from database.db import db
from models.user import User
from models.complaint import Complaint
from models.civic_issue import CivicIssue
from models.notification import Notification
from routes.auth import auth_bp
from routes.complaints import complaint_bp
from routes.officers import officer_bp
from routes.admin import admin_bp
from routes.notifications import notification_bp

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


with app.app_context():
    instance_path = os.path.join(os.path.dirname(__file__), "instance")
    os.makedirs(instance_path, exist_ok=True)
    db.create_all()
    migrate_complaint_location_columns()
    migrate_spam_moderation_columns()
    migrate_spam_reopen_columns()
    migrate_issue_clustering_columns()
    migrate_out_of_scope_rejection_columns()


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
app.register_blueprint(notification_bp, url_prefix="/api/notifications")


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    return jsonify({"message": error.description or error.name}), error.code


@app.errorhandler(Exception)
def handle_unexpected_exception(error):
    app.logger.exception("Unhandled exception")
    return jsonify({"message": "Something went wrong on the server."}), 500


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    upload_folder = os.path.join(os.path.dirname(__file__), "uploads")
    return send_from_directory(upload_folder, filename)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def home():
    return {
        "message": "CivicPulse AI Backend Running 🚀"
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)