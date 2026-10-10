from database.db import db
from utils.time_helper import utc_now


ALLOWED_WORK_UPDATE_STATUSES = ["Pending", "In Progress"]


class ComplaintWorkUpdate(db.Model):
    """A field-work evidence update submitted by an Officer against an
    existing complaint.

    Multiple updates can exist for the same complaint (the full work log
    is kept in the order they were created). A server-generated timestamp
    is always used so the official completion/progress time is never
    controlled by the client.

    Structured so a future "final resolution evidence" update can reuse
    this exact table without schema changes - the `status` column already
    carries that intent.
    """

    __tablename__ = "complaint_work_updates"

    id = db.Column(db.Integer, primary_key=True)

    complaint_id = db.Column(
        db.Integer,
        db.ForeignKey("complaints.id"),
        nullable=False,
        index=True,
    )

    # The officer who submitted this update - resolved from the JWT; never
    # trust a client-supplied officer identity.
    officer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
    )

    # Mirrors the allowed statuses on Complaint itself so this log stays
    # consistent with the parent complaint's lifecycle.
    status = db.Column(
        db.String(50),
        nullable=False,
        default="In Progress",
    )

    note = db.Column(
        db.Text,
        nullable=False,
    )

    # Optional evidence photo (same upload scheme as the complaint image).
    image_filename = db.Column(
        db.String(255),
        nullable=True,
    )

    # Optional GPS location of the officer at the time of the update.
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # Authoritative server-generated timestamp - never set by the client.
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )

    # Back-references for convenience in queries.
    complaint = db.relationship("Complaint", backref="work_updates")
    officer = db.relationship("User", foreign_keys=[officer_id])

    def __repr__(self):
        return (
            f"<ComplaintWorkUpdate complaint={self.complaint_id} "
            f"officer={self.officer_id} status={self.status}>"
        )
