"""
Level 2 community models.

Every engagement object attaches to a CivicIssue (the real-world problem),
never to an individual Complaint, so N duplicate reports never become N
separate community threads. The real user_id is always stored here, but is
never serialized into a public API response - see services/community_identity.py.

All of these are brand-new tables, created additively by db.create_all() in
app.py. No existing table is altered.
"""

from database.db import db
from utils.time_helper import utc_now


class IssueSupport(db.Model):
    """One citizen's support for a civic issue. The unique constraint is
    the real guarantee against double-voting - the route checks first for a
    friendly response, but the database has the final word."""

    __tablename__ = "issue_supports"
    __table_args__ = (
        db.UniqueConstraint("civic_issue_id", "user_id", name="uq_issue_support_user"),
    )

    id = db.Column(db.Integer, primary_key=True)

    civic_issue_id = db.Column(
        db.Integer,
        db.ForeignKey("civic_issues.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    created_at = db.Column(db.DateTime, default=utc_now, index=True)


# STILL_EXISTS | RESOLVED | NOT_SURE
VERIFICATION_TYPES = ["STILL_EXISTS", "RESOLVED", "NOT_SURE"]


class IssueVerification(db.Model):
    """A citizen's current on-the-ground observation of a civic issue.
    Purely a community signal - it never changes CivicIssue.status, which
    stays under Officer/Admin control. One row per (issue, citizen); a
    citizen changing their observation updates the row in place."""

    __tablename__ = "issue_verifications"
    __table_args__ = (
        db.UniqueConstraint("civic_issue_id", "user_id", name="uq_issue_verification_user"),
    )

    id = db.Column(db.Integer, primary_key=True)

    civic_issue_id = db.Column(
        db.Integer,
        db.ForeignKey("civic_issues.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    verification_type = db.Column(db.String(20), nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now)

    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, index=True)


# Visible | Flagged | Removed | Deleted
#   Flagged - reported by a citizen or caught by the lightweight content
#             check; still visible, waiting for a human decision.
#   Removed - an Officer/Admin moderation decision (auditable, reversible).
#   Deleted - withdrawn by its own author.
COMMENT_PUBLIC_STATUSES = ["Visible", "Flagged"]


class IssueComment(db.Model):
    __tablename__ = "issue_comments"

    id = db.Column(db.Integer, primary_key=True)

    civic_issue_id = db.Column(
        db.Integer,
        db.ForeignKey("civic_issues.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    content = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now, index=True)

    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    edited = db.Column(db.Boolean, nullable=False, default=False)

    moderation_status = db.Column(
        db.String(20),
        nullable=False,
        default="Visible",
        index=True
    )

    # "Citizen report" or "Automatic check" - who/what sent it for review.
    flag_source = db.Column(db.String(30), nullable=True)

    flag_reason = db.Column(db.Text, nullable=True)

    flagged_at = db.Column(db.DateTime, nullable=True)

    moderated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    moderated_at = db.Column(db.DateTime, nullable=True)

    moderation_reason = db.Column(db.Text, nullable=True)


class ImpactScoreEvent(db.Model):
    """Append-only ledger behind the Community Impact Score. The score is
    always SUM(points) over this table - never a stored counter a client
    could influence. Corrections are new compensating rows, never edits,
    so the history stays auditable.

    `dedupe_key` (unique, nullable) is how once-only awards are enforced
    at the database level, e.g. "support:<issue>:<user>"."""

    __tablename__ = "impact_score_events"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    event_type = db.Column(db.String(40), nullable=False, index=True)

    points = db.Column(db.Integer, nullable=False)

    civic_issue_id = db.Column(db.Integer, db.ForeignKey("civic_issues.id"), nullable=True)

    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=True)

    comment_id = db.Column(db.Integer, db.ForeignKey("issue_comments.id"), nullable=True)

    dedupe_key = db.Column(db.String(120), nullable=True, unique=True)

    # JSON-encoded, free-form context for auditors (never shown publicly).
    event_metadata = db.Column("metadata", db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now, index=True)


class CivicIssueStatusChange(db.Model):
    """Official status history for a CivicIssue. Level 1 only stored the
    current status, so there was no truthful way to render an official
    timeline. Written by the officer issue-status endpoint from Level 2 on;
    older issues simply have no history rows (and the timeline shows none,
    rather than inventing any)."""

    __tablename__ = "civic_issue_status_changes"

    id = db.Column(db.Integer, primary_key=True)

    civic_issue_id = db.Column(
        db.Integer,
        db.ForeignKey("civic_issues.id"),
        nullable=False,
        index=True
    )

    old_status = db.Column(db.String(50), nullable=True)

    new_status = db.Column(db.String(50), nullable=False)

    # Private: which officer made the change. Never serialized publicly.
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now)
