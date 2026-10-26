"""Issue-wide final-resolution review records and complaint dispositions."""

from database.db import db
from utils.time_helper import utc_now


REVIEW_STATES = ("Pending", "Approved", "Rejected", "Stale", "Superseded")
COMPLAINT_DISPOSITIONS = (
    "Addressed",
    "Duplicate Covered",
    "Additional Work Required",
)


class ResolutionReview(db.Model):
    """A Chief Officer decision request for one shared civic issue.

    ``issue_revision`` is a point-in-time snapshot.  The workflow routes will
    compare it with ``CivicIssue.review_revision`` before deciding a review,
    so a complaint or material evidence change cannot be approved silently.
    """

    __tablename__ = "resolution_reviews"

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(
        db.Integer, db.ForeignKey("civic_issues.id"), nullable=False, index=True
    )
    submitted_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    completion_note = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    issue_revision = db.Column(db.Integer, nullable=False)
    state = db.Column(db.String(20), nullable=False, default="Pending", index=True)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    stale_reason = db.Column(db.Text, nullable=True)
    stale_at = db.Column(db.DateTime, nullable=True)
    supersedes_review_id = db.Column(
        db.Integer, db.ForeignKey("resolution_reviews.id"), nullable=True, index=True
    )

    issue = db.relationship("CivicIssue")
    submitter = db.relationship("User", foreign_keys=[submitted_by])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    supersedes = db.relationship(
        "ResolutionReview", remote_side=[id], foreign_keys=[supersedes_review_id]
    )


class ResolutionReviewComplaintDisposition(db.Model):
    """An officer's auditable assessment of a linked complaint at submission.

    The unique constraint means a review has exactly one disposition per
    considered complaint.  The Stage 2 submission route will require a row
    for every eligible linked complaint and reject unfinished dispositions.
    """

    __tablename__ = "resolution_review_complaint_dispositions"
    __table_args__ = (
        db.UniqueConstraint(
            "resolution_review_id", "complaint_id", name="uq_review_complaint_disposition"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    resolution_review_id = db.Column(
        db.Integer, db.ForeignKey("resolution_reviews.id"), nullable=False, index=True
    )
    complaint_id = db.Column(
        db.Integer, db.ForeignKey("complaints.id"), nullable=False, index=True
    )
    disposition = db.Column(db.String(40), nullable=False)
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    review = db.relationship("ResolutionReview", backref="complaint_dispositions")
    complaint = db.relationship("Complaint")
