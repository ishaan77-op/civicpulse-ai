"""Admin-only ward registry and responsible-officer assignment routes.

These routes only manage records. They do not change who can see or handle
complaints; Officer access remains municipality-wide until the team decides
otherwise (docs/requirements.md FR-2.1).
"""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from database.db import db
from models.user import User
from models.ward import Ward, WardOfficerAssignment
from utils.time_helper import to_iso8601, utc_now

ward_bp = Blueprint("wards", __name__)

MAX_NAME = 120
MAX_CODE = 32
MAX_SOURCE = 255
MAX_REASON = 500


def _admin_or_denied():
    user = User.query.get(int(get_jwt_identity()))
    if not user or user.role != "Admin":
        return None, (jsonify({"message": "Admin access required"}), 403)
    return user, None


def _clean(data, field, maximum, required=False):
    """Trimmed string, None when blank. Raises ValueError with a client-safe message."""
    value = data.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"{field.capitalize()} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field.capitalize()} must be text")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{field.capitalize()} must be at most {maximum} characters")
    return value


def _active_count(ward_id):
    return WardOfficerAssignment.query.filter_by(ward_id=ward_id, ended_at=None).count()


def serialize_ward(ward):
    return {
        "id": ward.id,
        "name": ward.name,
        "code": ward.code,
        "source": ward.source,
        "is_active": ward.is_active,
        "created_at": to_iso8601(ward.created_at),
        "updated_at": to_iso8601(ward.updated_at),
        "deactivated_at": to_iso8601(ward.deactivated_at),
        "active_assignment_count": _active_count(ward.id),
    }


def serialize_assignment(assignment):
    officer = assignment.officer
    return {
        "id": assignment.id,
        "ward_id": assignment.ward_id,
        "officer": {
            "id": officer.id,
            "name": officer.name,
            "email": officer.email,
            # Current account state, so a later demotion or suspension is visible
            # next to the (unchanged) historical record.
            "role": officer.role,
            "is_suspended": officer.is_suspended,
        },
        "assigned_by": assignment.assigned_by,
        "assigned_at": to_iso8601(assignment.assigned_at),
        "reason": assignment.reason,
        "is_active": assignment.ended_at is None,
        "ended_at": to_iso8601(assignment.ended_at),
        "ended_by": assignment.ended_by,
        "end_reason": assignment.end_reason,
    }


def _code_taken(code, except_id=None):
    query = Ward.query.filter(func.lower(Ward.code) == code.lower())
    if except_id is not None:
        query = query.filter(Ward.id != except_id)
    return query.first() is not None


def _lock_ward(ward_id, require_active=False):
    """Take the database write lock and confirm the ward (still) qualifies.

    SQLite has no row locks and a SELECT does not start a write transaction, so
    this no-op UPDATE both acquires the lock and makes the check atomic with the
    writes that follow (e.g. a ward deactivated while an assignment is created).
    """
    query = Ward.query.filter(Ward.id == ward_id)
    if require_active:
        query = query.filter(Ward.is_active.is_(True))
    # Setting updated_at to itself keeps its onupdate default from firing.
    return query.update({Ward.updated_at: Ward.updated_at}, synchronize_session=False) == 1


# ---------- Wards ----------

@ward_bp.route("/wards", methods=["GET"])
@jwt_required()
def list_wards():
    _admin, denied = _admin_or_denied()
    if denied:
        return denied
    query = Ward.query
    active = request.args.get("active")
    if active in ("true", "false"):
        query = query.filter(Ward.is_active.is_(active == "true"))
    wards = query.order_by(Ward.is_active.desc(), Ward.name.asc(), Ward.id.asc()).all()
    return jsonify({"wards": [serialize_ward(ward) for ward in wards]}), 200


@ward_bp.route("/wards", methods=["POST"])
@jwt_required()
def create_ward():
    admin, denied = _admin_or_denied()
    if denied:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"message": "Request body is required"}), 400
    try:
        name = _clean(data, "name", MAX_NAME, required=True)
        code = _clean(data, "code", MAX_CODE)
        source = _clean(data, "source", MAX_SOURCE)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400
    if code and _code_taken(code):
        return jsonify({"message": "A ward with this code already exists"}), 409

    ward = Ward(name=name, code=code, source=source, created_by=admin.id)
    try:
        db.session.add(ward)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "A ward with this code already exists"}), 409
    return jsonify({"message": "Ward created", "ward": serialize_ward(ward)}), 201


@ward_bp.route("/wards/<int:ward_id>", methods=["PUT"])
@jwt_required()
def update_ward(ward_id):
    _admin, denied = _admin_or_denied()
    if denied:
        return denied
    ward = db.session.get(Ward, ward_id)
    if not ward:
        return jsonify({"message": "Ward not found"}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({"message": "Request body is required"}), 400
    if "is_active" in data:
        return jsonify({"message": "Use the activate/deactivate endpoints to change a ward's state"}), 400
    try:
        if "name" in data:
            ward.name = _clean(data, "name", MAX_NAME, required=True)
        if "code" in data:
            code = _clean(data, "code", MAX_CODE)
            if code and _code_taken(code, except_id=ward.id):
                return jsonify({"message": "A ward with this code already exists"}), 409
            ward.code = code
        if "source" in data:
            ward.source = _clean(data, "source", MAX_SOURCE)
    except ValueError as error:
        db.session.rollback()
        return jsonify({"message": str(error)}), 400
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "A ward with this code already exists"}), 409
    return jsonify({"message": "Ward updated", "ward": serialize_ward(ward)}), 200


def _set_ward_active(ward_id, active):
    _admin, denied = _admin_or_denied()
    if denied:
        return denied
    ward = db.session.get(Ward, ward_id)
    if not ward:
        return jsonify({"message": "Ward not found"}), 404
    if ward.is_active != active:
        # Deliberately leaves assignments untouched: ending them is an explicit,
        # separately recorded Admin action, never a side effect.
        ward.is_active = active
        ward.deactivated_at = None if active else utc_now()
        db.session.commit()
    return jsonify({
        "message": "Ward activated" if active else "Ward deactivated",
        "ward": serialize_ward(ward),
    }), 200


@ward_bp.route("/wards/<int:ward_id>/deactivate", methods=["PUT"])
@jwt_required()
def deactivate_ward(ward_id):
    return _set_ward_active(ward_id, False)


@ward_bp.route("/wards/<int:ward_id>/activate", methods=["PUT"])
@jwt_required()
def activate_ward(ward_id):
    return _set_ward_active(ward_id, True)


# ---------- Assignments ----------

@ward_bp.route("/wards/<int:ward_id>/assignments", methods=["GET"])
@jwt_required()
def list_assignments(ward_id):
    _admin, denied = _admin_or_denied()
    if denied:
        return denied
    ward = db.session.get(Ward, ward_id)
    if not ward:
        return jsonify({"message": "Ward not found"}), 404
    rows = WardOfficerAssignment.query.filter_by(ward_id=ward_id).order_by(
        WardOfficerAssignment.assigned_at.desc(), WardOfficerAssignment.id.desc()
    ).all()
    return jsonify({
        "ward": serialize_ward(ward),
        "assignments": [serialize_assignment(row) for row in rows],
    }), 200


@ward_bp.route("/wards/<int:ward_id>/assignments", methods=["POST"])
@jwt_required()
def assign_officer(ward_id):
    admin, denied = _admin_or_denied()
    if denied:
        return denied
    if not db.session.get(Ward, ward_id):
        return jsonify({"message": "Ward not found"}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"message": "Request body is required"}), 400

    officer_id = data.get("officer_id")
    if isinstance(officer_id, bool) or not isinstance(officer_id, int):
        return jsonify({"message": "officer_id must be a whole number"}), 400
    try:
        reason = _clean(data, "reason", MAX_REASON)
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    officer = db.session.get(User, officer_id)
    if not officer:
        return jsonify({"message": "Officer not found"}), 404
    if officer.role != "Officer":
        return jsonify({"message": "Only users with the Officer role can be assigned to a ward"}), 400
    if officer.is_suspended:
        return jsonify({"message": "A suspended Officer cannot be assigned to a ward"}), 400

    try:
        # Lock first, then verify: the ward must still be active when we write.
        if not _lock_ward(ward_id, require_active=True):
            db.session.rollback()
            return jsonify({"message": "This ward is inactive; reactivate it before assigning an Officer"}), 409
        existing = WardOfficerAssignment.query.filter_by(
            ward_id=ward_id, officer_id=officer_id, ended_at=None
        ).first()
        if existing:
            db.session.rollback()
            return jsonify({"message": "This Officer is already actively assigned to the ward"}), 409
        assignment = WardOfficerAssignment(
            ward_id=ward_id, officer_id=officer_id, assigned_by=admin.id, reason=reason
        )
        db.session.add(assignment)
        db.session.commit()
    except IntegrityError:
        # The partial unique index caught a concurrent duplicate.
        db.session.rollback()
        return jsonify({"message": "This Officer is already actively assigned to the ward"}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to assign officer to ward")
        return jsonify({"message": "Could not assign the Officer"}), 500
    return jsonify({"message": "Officer assigned", "assignment": serialize_assignment(assignment)}), 201


@ward_bp.route("/wards/<int:ward_id>/assignments/<int:assignment_id>/end", methods=["PUT"])
@jwt_required()
def end_assignment(ward_id, assignment_id):
    admin, denied = _admin_or_denied()
    if denied:
        return denied
    assignment = WardOfficerAssignment.query.filter_by(id=assignment_id, ward_id=ward_id).first()
    if not assignment:
        return jsonify({"message": "Assignment not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        reason = _clean(data, "reason", MAX_REASON) if isinstance(data, dict) else None
    except ValueError as error:
        return jsonify({"message": str(error)}), 400

    try:
        # Conditional on still being active, so a repeated or concurrent request
        # cannot end the same assignment twice or overwrite who ended it.
        ended = WardOfficerAssignment.query.filter_by(id=assignment_id, ended_at=None).update({
            "ended_at": utc_now(),
            "ended_by": admin.id,
            "end_reason": reason,
        }, synchronize_session=False)
        if ended != 1:
            db.session.rollback()
            return jsonify({"message": "This assignment has already ended"}), 409
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to end ward assignment")
        return jsonify({"message": "Could not end the assignment"}), 500

    db.session.expire_all()
    ended_row = db.session.get(WardOfficerAssignment, assignment_id)
    return jsonify({"message": "Assignment ended", "assignment": serialize_assignment(ended_row)}), 200
