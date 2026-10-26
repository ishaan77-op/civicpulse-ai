"""Officer performance ratings and low-rating corrective follow-ups.

A rating judges a completed job (an *approved* resolution review); it is a
separate decision from that approval and never touches the review or the
issue.  Ratings and follow-up events are append-only: corrections are new
rows, and database triggers (see ``migrate_performance_schema`` in app.py)
refuse updates and deletes of history.
"""

from database.db import db
from utils.time_helper import utc_now


# Transitions (enforced by compare-and-swap in services/performance.py):
#   Awaiting Assignment -> Assigned                (assign)
#   Assigned            -> Assigned                (reassign to another Officer)
#   Assigned            -> Correction Submitted    (assigned Officer submits)
#   Correction Submitted-> Closed                  (Chief Officer verifies and closes)
#   Correction Submitted-> Assigned                (Chief Officer returns for more work)
# A rating revision never moves, closes, or deletes an existing case.
FOLLOW_UP_STATES = (
    "Awaiting Assignment",
    "Assigned",
    "Correction Submitted",
    "Closed",
)
OPEN_FOLLOW_UP_STATES = ("Awaiting Assignment", "Assigned", "Correction Submitted")
FOLLOW_UP_EVENT_TYPES = (
    "Created", "Assigned", "Reassigned", "CorrectionSubmitted",
    "CorrectionReturned", "Closed",
)
LOW_RATING_MAX = 2


class ResolutionRating(db.Model):
    """One Chief Officer rating of approved work, or a revision of an earlier one.

    ``rated_officer_id`` is copied from the review's submitter by the server;
    nothing about the officer comes from the client.  A review has exactly one
    original rating (``supersedes_rating_id IS NULL``) and each rating can be
    revised at most once, so the revisions form a single chain whose last row
    is the effective rating.
    """

    __tablename__ = "resolution_ratings"
    __table_args__ = (
        db.Index("uq_rating_one_original", "resolution_review_id", unique=True,
                 sqlite_where=db.text("supersedes_rating_id IS NULL")),
        db.Index("uq_rating_one_revision", "supersedes_rating_id", unique=True,
                 sqlite_where=db.text("supersedes_rating_id IS NOT NULL")),
    )

    id = db.Column(db.Integer, primary_key=True)
    resolution_review_id = db.Column(
        db.Integer, db.ForeignKey("resolution_reviews.id"), nullable=False, index=True
    )
    rated_officer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    rated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.Text, nullable=True)
    needs_follow_up = db.Column(db.Boolean, nullable=False, default=False)
    supersedes_rating_id = db.Column(db.Integer, db.ForeignKey("resolution_ratings.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    review = db.relationship("ResolutionReview")
    rated_officer = db.relationship("User", foreign_keys=[rated_officer_id])
    rater = db.relationship("User", foreign_keys=[rated_by])


class ResolutionFollowUp(db.Model):
    """The corrective case opened by a 1- or 2-star rating.

    Deliberately separate from the issue: its status never changes the issue's
    or the review's status.  At most one case exists per reviewed job.  The
    current-state columns are a convenience; the authoritative trail is
    ``FollowUpEvent``.
    """

    __tablename__ = "resolution_follow_ups"

    id = db.Column(db.Integer, primary_key=True)
    resolution_review_id = db.Column(
        db.Integer, db.ForeignKey("resolution_reviews.id"), nullable=False, unique=True
    )
    rating_id = db.Column(db.Integer, db.ForeignKey("resolution_ratings.id"), nullable=False)
    issue_id = db.Column(db.Integer, db.ForeignKey("civic_issues.id"), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="Awaiting Assignment", index=True)
    assigned_officer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    closed_at = db.Column(db.DateTime, nullable=True)

    review = db.relationship("ResolutionReview")
    rating = db.relationship("ResolutionRating")
    issue = db.relationship("CivicIssue")
    assigned_officer = db.relationship("User", foreign_keys=[assigned_officer_id])
    events = db.relationship("FollowUpEvent", backref="follow_up", order_by="FollowUpEvent.id")


class FollowUpEvent(db.Model):
    """Append-only audit entry: assignment, correction submission, return, closure."""

    __tablename__ = "resolution_follow_up_events"

    id = db.Column(db.Integer, primary_key=True)
    follow_up_id = db.Column(
        db.Integer, db.ForeignKey("resolution_follow_ups.id"), nullable=False, index=True
    )
    event_type = db.Column(db.String(30), nullable=False)
    from_status = db.Column(db.String(30), nullable=True)
    to_status = db.Column(db.String(30), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    officer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    note = db.Column(db.Text, nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    actor = db.relationship("User", foreign_keys=[actor_id])
    officer = db.relationship("User", foreign_keys=[officer_id])
