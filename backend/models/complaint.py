from database.db import db
from utils.time_helper import utc_now


class Complaint(db.Model):
    __tablename__ = "complaints"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    title = db.Column(
        db.String(200),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=False
    )

    category = db.Column(
        db.String(100),
        nullable=False,
        default="Other"
    )

    ai_priority = db.Column(
        db.String(20),
        nullable=True
    )

    ai_department = db.Column(
        db.String(100),
        nullable=True
    )

    ai_visual_observation = db.Column(
        db.Text,
        nullable=True
    )

    ai_summary = db.Column(
        db.Text,
        nullable=True
    )

    image_filename = db.Column(
        db.String(255),
        nullable=True
    )

    location = db.Column(
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

    status = db.Column(
        db.String(50),
        nullable=False,
        default="Pending"
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=utc_now
    )

    # ==========================================
    # Spam / misreport moderation
    # ==========================================

    ai_spam_flag = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    ai_spam_reason = db.Column(
        db.Text,
        nullable=True
    )

    ai_spam_confidence = db.Column(
        db.String(20),
        nullable=True
    )

    # NotFlagged | Pending | Confirmed | Rejected
    spam_review_status = db.Column(
        db.String(20),
        nullable=False,
        default="NotFlagged"
    )

    spam_reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    spam_reviewed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # Set only by the reopen action below, and left in place afterwards
    # (even once a new decision is recorded) so the moderation history
    # still shows a report was corrected/re-reviewed at least once.
    spam_reopened_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    spam_reopened_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # ==========================================
    # Out-of-scope rejection (Officer/Admin)
    #
    # Conceptually separate from spam moderation above: a complaint here can
    # be entirely genuine (real photo, valid GPS, accurate description) but
    # simply outside NMC/government jurisdiction (private property, private
    # society, etc). Rejecting one here must never touch spam_count,
    # is_suspended, or spam_review_status.
    # ==========================================

    # NotRejected | Rejected
    rejection_status = db.Column(
        db.String(20),
        nullable=False,
        default="NotRejected"
    )

    rejection_reason = db.Column(
        db.String(50),
        nullable=True
    )

    rejection_explanation = db.Column(
        db.Text,
        nullable=True
    )

    rejected_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    rejected_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # Set only by the reopen action below, and left in place afterwards -
    # same audit-preservation approach as spam_reopened_* above.
    rejection_reopened_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    rejection_reopened_at = db.Column(
        db.DateTime,
        nullable=True
    )

    # ==========================================
    # Issue clustering
    # ==========================================

    # Nullable: an existing complaint from before this feature, or one
    # that somehow never matched/created an issue, is simply unlinked.
    issue_id = db.Column(
        db.Integer,
        db.ForeignKey("civic_issues.id"),
        nullable=True
    )

    issue = db.relationship("CivicIssue")