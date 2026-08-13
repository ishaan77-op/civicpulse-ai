from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import db
from models.complaint import Complaint
from models.user import User
from routes.complaints import serialize_complaint

officer_bp = Blueprint("officer", __name__)


@officer_bp.route("/complaints", methods=["GET"])
@jwt_required()
def get_all_complaints():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    status = request.args.get("status")
    category = request.args.get("category")
    priority = request.args.get("priority")
    department = request.args.get("department")

    query = Complaint.query

    if status:
        query = query.filter(Complaint.status == status)
    if category:
        query = query.filter(Complaint.category == category)
    if priority:
        query = query.filter(Complaint.ai_priority == priority)
    if department:
        query = query.filter(Complaint.ai_department == department)

    complaints = query.order_by(Complaint.created_at.desc()).all()

    return jsonify({
        "total": len(complaints),
        "complaints": [serialize_complaint(c) for c in complaints]
    }), 200


@officer_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_officer_stats():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    total = Complaint.query.count()
    pending = Complaint.query.filter_by(status="Pending").count()
    in_progress = Complaint.query.filter_by(status="In Progress").count()
    resolved = Complaint.query.filter_by(status="Resolved").count()

    return jsonify({
        "total_complaints": total,
        "pending": pending,
        "in_progress": in_progress,
        "resolved": resolved
    }), 200
