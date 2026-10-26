from database.db import db
from utils.time_helper import utc_now


class Notification(db.Model):
    """A simple in-app notification for a citizen. Currently only created
    for a Confirmed spam decision - never for the AI flag alone, never for
    a Rejected decision."""

    __tablename__ = "notifications"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    complaint_id = db.Column(
        db.Integer,
        db.ForeignKey("complaints.id"),
        nullable=True
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    spam_count_at_time = db.Column(
        db.Integer,
        nullable=True
    )

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        default=utc_now
    )
