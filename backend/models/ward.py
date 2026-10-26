"""Ward registry and the append-only history of responsible-officer assignments.

Deliberately a standalone foundation: nothing here is linked to complaints,
issues, or officer access yet, and no ward is ever created by the code itself
(names, codes, and any boundaries must come from an official source that an
Admin enters or imports).
"""

from database.db import db
from utils.time_helper import utc_now


class Ward(db.Model):
    """An administrative area. Never deleted: a ward is deactivated instead, so
    its assignment history stays attached to a real record.

    ``code`` is the stable official identifier when one exists (unique,
    case-insensitively); ``name`` is required but not forced unique because the
    team has not confirmed that official ward names are.  ``source`` records
    where the name/code came from (for example the circular or dataset an
    Admin copied it from) so provenance is never implied.
    """

    __tablename__ = "wards"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(32), nullable=True, unique=True)
    source = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    deactivated_at = db.Column(db.DateTime, nullable=True)


class WardOfficerAssignment(db.Model):
    """One period during which an Officer is responsible for a ward.

    A row is created when the Officer is assigned and *ended*, never edited or
    removed: ``ended_at`` is set once, together with who ended it and why.
    "Active" simply means ``ended_at IS NULL``.  Reassigning or replacing
    someone is therefore an end plus a new row, so the full timeline survives.

    No cardinality is imposed beyond "the same Officer cannot be actively
    assigned to the same ward twice": a ward may have several Officers and an
    Officer several wards until the team decides otherwise.  Database triggers
    (see ``migrate_ward_registry_schema`` in app.py) make the history immutable.
    """

    __tablename__ = "ward_officer_assignments"
    __table_args__ = (
        db.Index(
            "uq_ward_assignment_active_pair",
            "ward_id", "officer_id",
            unique=True,
            sqlite_where=db.text("ended_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    ward_id = db.Column(db.Integer, db.ForeignKey("wards.id"), nullable=False, index=True)
    officer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    reason = db.Column(db.Text, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    ended_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    end_reason = db.Column(db.Text, nullable=True)

    ward = db.relationship("Ward", backref="assignments")
    officer = db.relationship("User", foreign_keys=[officer_id])
