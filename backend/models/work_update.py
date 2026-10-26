"""Auditable officer field-work records for a shared civic issue."""

from database.db import db
from utils.time_helper import utc_now


ALLOWED_WORK_UPDATE_STATUSES = ("Pending", "In Progress")


class IssueWorkUpdate(db.Model):
    """Progress recorded against the underlying issue.

    ``complaint_id`` is optional because one visit can address the entire
    issue.  When a visit concerns one report or location specifically, the
    association preserves that context without duplicating the work log for
    every linked complaint.
    """

    __tablename__ = "issue_work_updates"
    __table_args__ = (
        db.UniqueConstraint(
            "officer_id", "idempotency_key", name="uq_issue_work_update_retry"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(
        db.Integer, db.ForeignKey("civic_issues.id"), nullable=False, index=True
    )
    complaint_id = db.Column(
        db.Integer, db.ForeignKey("complaints.id"), nullable=True, index=True
    )
    officer_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    status = db.Column(db.String(50), nullable=False, default="In Progress")
    note = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True, index=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # A client-generated retry key is optional for backwards-compatible API
    # rollout.  When supplied, the database guarantees one update per officer
    # and key even if a request is retried after a network failure.
    idempotency_key = db.Column(db.String(128), nullable=True)
    request_fingerprint = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    issue = db.relationship("CivicIssue")
    complaint = db.relationship("Complaint")
    officer = db.relationship("User", foreign_keys=[officer_id])
