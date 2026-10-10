from database.db import db
from utils.time_helper import utc_now


# Statuses that only the Chief Officer review workflow may set on a Complaint.
# Ordinary work updates (Feature 1) must not accept any of these.
RESOLUTION_REVIEW_COMPLAINT_STATUSES = ["Pending Review", "Resolved"]

# All complaint statuses — the union of Feature-1 work-update statuses and
# Feature-2 review statuses.
ALL_COMPLAINT_STATUSES = ["Pending", "In Progress", "Pending Review", "Resolved"]

# Review decisions a Chief Officer can record.
REVIEW_DECISIONS = ["Approved", "Rejected"]


class ResolutionReview(db.Model):
    """A final-resolution review request submitted by an Officer and
    decided by a Chief Officer.

    Workflow:
      1. Officer submits a completion note + evidence photo.
      2. The parent complaint status advances to "Pending Review".
      3. A Chief Officer opens the review and either approves or rejects.
      4. On approval: complaint.status becomes "Resolved".
         On rejection: complaint.status reverts to "In Progress",
         the rejection_note is stored here, and the Officer must
         submit a corrected request.

    Audit guarantees:
      - submitted_by, reviewed_by come from JWT; clients never supply them.
      - submitted_at, reviewed_at are set by the server via utc_now().
      - Only one active (Pending) review per complaint is allowed.
      - The submitting Officer cannot be the reviewer.
    """

    __tablename__ = "resolution_reviews"

    id = db.Column(db.Integer, primary_key=True)

    complaint_id = db.Column(
        db.Integer,
        db.ForeignKey("complaints.id"),
        nullable=False,
        index=True,
    )

    # Officer who submitted the resolution request.
    submitted_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
    )

    # Required completion note describing work done.
    completion_note = db.Column(db.Text, nullable=False)

    # Required final evidence photo filename (same upload scheme as
    # complaint photos and work-update photos).
    image_filename = db.Column(db.String(255), nullable=False)

    # Optional GPS at time of submission.
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # Server-generated submission timestamp — never supplied by the client.
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    # Decision: None (pending) | "Approved" | "Rejected"
    decision = db.Column(db.String(20), nullable=True)

    # Chief Officer who reviewed the request — set from JWT on the review
    # endpoint, never from client input.
    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
    )

    # Reason for rejection (required when decision is "Rejected").
    rejection_note = db.Column(db.Text, nullable=True)

    # Server-generated review timestamp.
    reviewed_at = db.Column(db.DateTime, nullable=True)

    # Back-references for convenience in serialisation.
    complaint = db.relationship("Complaint", backref="resolution_reviews")
    officer = db.relationship("User", foreign_keys=[submitted_by])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])

    def __repr__(self):
        return (
            f"<ResolutionReview complaint={self.complaint_id} "
            f"decision={self.decision or 'Pending'}>"
        )
