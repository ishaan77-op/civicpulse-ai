from flask import Blueprint, current_app, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, text

from database.db import db
from models.complaint import Complaint
from models.role_change import RoleChange
from models.user import User
from utils.time_helper import to_iso8601

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/analytics", methods=["GET"])
@jwt_required()
def get_analytics():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role != "Admin":
        return jsonify({"message": "Admin access required"}), 403

    # Confirmed spam is moderation history, not a genuine civic complaint -
    # excluded from every analytics figure below while the row itself (and
    # its spam audit trail) is preserved. Same treatment for a complaint
    # rejected as out-of-scope (a separate, non-spam moderation outcome).
    active = Complaint.query.filter(
        Complaint.spam_review_status != "Confirmed",
        Complaint.rejection_status != "Rejected",
    )

    total_complaints = active.count()
    pending = active.filter(Complaint.status == "Pending").count()
    in_progress = active.filter(Complaint.status == "In Progress").count()
    resolved = active.filter(Complaint.status == "Resolved").count()

    resolution_rate = round((resolved / total_complaints * 100), 1) if total_complaints > 0 else 0.0

    total_users = User.query.count()
    citizen_count = User.query.filter_by(role="Citizen").count()
    officer_count = User.query.filter_by(role="Officer").count()
    admin_count = User.query.filter_by(role="Admin").count()

    active_filter = db.and_(
        Complaint.spam_review_status != "Confirmed",
        Complaint.rejection_status != "Rejected",
    )

    # Category breakdown
    categories_raw = db.session.query(
        Complaint.category, func.count(Complaint.id)
    ).filter(active_filter).group_by(Complaint.category).all()
    categories = {cat: count for cat, count in categories_raw}

    # Department breakdown
    depts_raw = db.session.query(
        Complaint.ai_department, func.count(Complaint.id)
    ).filter(active_filter).group_by(Complaint.ai_department).all()
    departments = {dept or "Unassigned": count for dept, count in depts_raw}

    # Priority breakdown
    priority_raw = db.session.query(
        Complaint.ai_priority, func.count(Complaint.id)
    ).filter(active_filter).group_by(Complaint.ai_priority).all()
    priorities = {p or "Unclassified": count for p, count in priority_raw}

    return jsonify({
        "summary": {
            "total_complaints": total_complaints,
            "pending": pending,
            "in_progress": in_progress,
            "resolved": resolved,
            "resolution_rate": resolution_rate,
            "total_users": total_users,
            "citizens": citizen_count,
            "officers": officer_count,
            "admins": admin_count
        },
        "breakdown": {
            "categories": categories,
            "departments": departments,
            "priorities": priorities
        }
    }), 200


@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def get_users():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role != "Admin":
        return jsonify({"message": "Admin access required"}), 403

    users = User.query.order_by(User.created_at.desc()).all()

    return jsonify({
        "users": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "spam_count": u.spam_count,
                "is_suspended": u.is_suspended,
                "created_at": to_iso8601(u.created_at)
            }
            for u in users
        ]
    }), 200


ASSIGNABLE_ROLES = ("Citizen", "Officer", "Chief Officer", "Admin")


def _role_response(target_user, message):
    return jsonify({
        "message": message,
        "user": {
            "id": target_user.id,
            "name": target_user.name,
            "email": target_user.email,
            "role": target_user.role,
        },
    }), 200


@admin_bp.route("/users/<int:target_user_id>/role", methods=["PUT"])
@jwt_required()
def update_user_role(target_user_id):
    """Change a user's role. Admin only.

    Two protections beyond the Admin check:
    * The last active (non-suspended) Admin cannot be demoted, so the system can never
      end up with nobody able to manage roles.  The check and the change are one SQL
      statement, so two Admins demoting each other at the same moment cannot both succeed.
    * Every applied change is written to ``role_changes`` in the same transaction.  If the
      audit row cannot be written, the role change is rolled back with it.
    """
    user_id = get_jwt_identity()
    admin = User.query.get(int(user_id))

    if not admin or admin.role != "Admin":
        return jsonify({"message": "Admin access required"}), 403

    target_user = User.query.get(target_user_id)
    if not target_user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "role" not in data:
        return jsonify({"message": "Role is required"}), 400

    new_role = data["role"]
    if not isinstance(new_role, str) or new_role not in ASSIGNABLE_ROLES:
        return jsonify({"message": "Invalid role. Must be Citizen, Officer, Chief Officer, or Admin"}), 400

    old_role = target_user.role
    if new_role == old_role:
        return _role_response(target_user, f"User {target_user.email} already has the role {new_role}")

    try:
        if old_role == "Admin":
            # Demoting an Admin: another active Admin must exist, decided inside the UPDATE itself.
            result = db.session.execute(
                text(
                    "UPDATE users SET role = :new_role "
                    "WHERE id = :id AND role = 'Admin' AND EXISTS ("
                    "SELECT 1 FROM users other WHERE other.role = 'Admin' "
                    "AND other.is_suspended = 0 AND other.id <> :id)"
                ),
                {"new_role": new_role, "id": target_user.id},
            )
        else:
            # Compare-and-swap on the role we read, so a concurrent change is never overwritten.
            result = db.session.execute(
                text("UPDATE users SET role = :new_role WHERE id = :id AND role IS :old_role"),
                {"new_role": new_role, "id": target_user.id, "old_role": old_role},
            )

        if result.rowcount != 1:
            db.session.rollback()
            db.session.expire_all()
            current = db.session.get(User, target_user_id)
            if old_role == "Admin" and current is not None and current.role == "Admin":
                current_app.logger.warning(
                    "Refused to demote the last active Admin (user id %s) by Admin id %s", target_user_id, admin.id
                )
                return jsonify({
                    "message": "At least one active Admin must remain. Promote another Admin before demoting this one."
                }), 409
            return jsonify({"message": "This user's role changed while you were editing it. Reload and try again."}), 409

        db.session.add(RoleChange(
            target_user_id=target_user.id, changed_by=admin.id, old_role=old_role, new_role=new_role,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to change a user's role")
        return jsonify({"message": "Could not change the role"}), 500

    db.session.expire_all()
    target_user = db.session.get(User, target_user_id)
    return _role_response(target_user, f"Role for user {target_user.email} updated to {new_role}")
