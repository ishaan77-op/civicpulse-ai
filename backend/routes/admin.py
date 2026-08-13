from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from database.db import db
from models.complaint import Complaint
from models.user import User

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/analytics", methods=["GET"])
@jwt_required()
def get_analytics():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role != "Admin":
        return jsonify({"message": "Admin access required"}), 403

    total_complaints = Complaint.query.count()
    pending = Complaint.query.filter_by(status="Pending").count()
    in_progress = Complaint.query.filter_by(status="In Progress").count()
    resolved = Complaint.query.filter_by(status="Resolved").count()

    resolution_rate = round((resolved / total_complaints * 100), 1) if total_complaints > 0 else 0.0

    total_users = User.query.count()
    citizen_count = User.query.filter_by(role="Citizen").count()
    officer_count = User.query.filter_by(role="Officer").count()
    admin_count = User.query.filter_by(role="Admin").count()

    # Category breakdown
    categories_raw = db.session.query(
        Complaint.category, func.count(Complaint.id)
    ).group_by(Complaint.category).all()
    categories = {cat: count for cat, count in categories_raw}

    # Department breakdown
    depts_raw = db.session.query(
        Complaint.ai_department, func.count(Complaint.id)
    ).group_by(Complaint.ai_department).all()
    departments = {dept or "Unassigned": count for dept, count in depts_raw}

    # Priority breakdown
    priority_raw = db.session.query(
        Complaint.ai_priority, func.count(Complaint.id)
    ).group_by(Complaint.ai_priority).all()
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
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
    }), 200


@admin_bp.route("/users/<int:target_user_id>/role", methods=["PUT"])
@jwt_required()
def update_user_role(target_user_id):
    user_id = get_jwt_identity()
    admin = User.query.get(int(user_id))

    if not admin or admin.role != "Admin":
        return jsonify({"message": "Admin access required"}), 403

    target_user = User.query.get(target_user_id)
    if not target_user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json()
    if not data or "role" not in data:
        return jsonify({"message": "Role is required"}), 400

    new_role = data["role"]
    if new_role not in ["Citizen", "Officer", "Admin"]:
        return jsonify({"message": "Invalid role. Must be Citizen, Officer, or Admin"}), 400

    target_user.role = new_role
    db.session.commit()

    return jsonify({
        "message": f"Role for user {target_user.email} updated to {new_role}",
        "user": {
            "id": target_user.id,
            "name": target_user.name,
            "email": target_user.email,
            "role": target_user.role
        }
    }), 200
