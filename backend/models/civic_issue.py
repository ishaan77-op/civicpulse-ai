from database.db import db
from utils.time_helper import utc_now


class CivicIssue(db.Model):
    """A real-world civic issue that one or more citizen complaints can be
    linked to. Complaints are never merged or deleted - this is purely an
    additional grouping so officers can work on the underlying issue
    instead of N duplicate-looking complaints."""

    __tablename__ = "civic_issues"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    category = db.Column(
        db.String(100),
        nullable=False
    )

    location_label = db.Column(
        db.String(255),
        nullable=True
    )

    latitude = db.Column(
        db.Float,
        nullable=False
    )

    longitude = db.Column(
        db.Float,
        nullable=False
    )

    # Pending | In Progress | Resolved - same vocabulary as Complaint.status
    status = db.Column(
        db.String(50),
        nullable=False,
        default="Pending"
    )

    report_count = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    ai_summary = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=utc_now
    )

    updated_at = db.Column(
        db.DateTime,
        default=utc_now,
        onupdate=utc_now
    )
