from database.db import db
from utils.time_helper import utc_now


class RoleChange(db.Model):
    """One applied change of a user's role, recorded in the same transaction as the change.

    Append-only: database triggers (see ``migrate_role_change_schema`` in app.py) reject
    updates and deletes.  Only changes that took effect are recorded; a refused or failed
    attempt leaves both the user's role and this table unchanged.
    """

    __tablename__ = "role_changes"

    id = db.Column(db.Integer, primary_key=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    old_role = db.Column(db.String(20), nullable=False)
    new_role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    def __repr__(self):
        return f"<RoleChange user={self.target_user_id} {self.old_role}->{self.new_role}>"
