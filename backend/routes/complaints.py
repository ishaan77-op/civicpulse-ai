from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import db
from models.complaint import Complaint
from models.user import User


complaint_bp = Blueprint("complaint", __name__)


# ==========================================
# CREATE COMPLAINT
# ==========================================

@complaint_bp.route("/", methods=["POST"])
@jwt_required()
def create_complaint():

    data = request.get_json()

    if not data:
        return jsonify({
            "message": "Request body is required"
        }), 400

    title = data.get("title")
    description = data.get("description")
    category = data.get("category", "Other")
    location = data.get("location")

    if not title or not description or not location:
        return jsonify({
            "message": "Title, description and location are required"
        }), 400

    user_id = get_jwt_identity()

    complaint = Complaint(
        title=title,
        description=description,
        category=category,
        location=location,
        user_id=int(user_id)
    )

    db.session.add(complaint)
    db.session.commit()

    return jsonify({
        "message": "Complaint created successfully",
        "complaint": {
            "id": complaint.id,
            "title": complaint.title,
            "description": complaint.description,
            "category": complaint.category,
            "location": complaint.location,
            "status": complaint.status,
            "user_id": complaint.user_id,
            "created_at": complaint.created_at.isoformat()
        }
    }), 201


# ==========================================
# GET MY COMPLAINTS
# ==========================================

@complaint_bp.route("/", methods=["GET"])
@jwt_required()
def get_my_complaints():

    user_id = get_jwt_identity()

    complaints = Complaint.query.filter_by(
        user_id=int(user_id)
    ).order_by(
        Complaint.created_at.desc()
    ).all()

    return jsonify({
        "complaints": [
            {
                "id": complaint.id,
                "title": complaint.title,
                "description": complaint.description,
                "category": complaint.category,
                "location": complaint.location,
                "status": complaint.status,
                "user_id": complaint.user_id,
                "created_at": complaint.created_at.isoformat()
            }
            for complaint in complaints
        ]
    }), 200
# ==========================================
# GET SINGLE COMPLAINT
# ==========================================

@complaint_bp.route("/<int:complaint_id>", methods=["GET"])
@jwt_required()
def get_complaint(complaint_id):

    user_id = get_jwt_identity()

    complaint = Complaint.query.filter_by(
        id=complaint_id,
        user_id=int(user_id)
    ).first()

    if not complaint:
        return jsonify({
            "message": "Complaint not found"
        }), 404

    return jsonify({
        "complaint": {
            "id": complaint.id,
            "title": complaint.title,
            "description": complaint.description,
            "category": complaint.category,
            "location": complaint.location,
            "status": complaint.status,
            "user_id": complaint.user_id,
            "created_at": complaint.created_at.isoformat()
        }
    }), 200
# ==========================================
# UPDATE MY COMPLAINT
# ==========================================

@complaint_bp.route("/<int:complaint_id>", methods=["PUT"])
@jwt_required()
def update_complaint(complaint_id):

    user_id = get_jwt_identity()

    complaint = Complaint.query.filter_by(
        id=complaint_id,
        user_id=int(user_id)
    ).first()

    if not complaint:
        return jsonify({
            "message": "Complaint not found"
        }), 404

    data = request.get_json()

    if not data:
        return jsonify({
            "message": "Request body is required"
        }), 400

    if "title" in data:
        complaint.title = data["title"]

    if "description" in data:
        complaint.description = data["description"]

    if "category" in data:
        complaint.category = data["category"]

    if "location" in data:
        complaint.location = data["location"]

    db.session.commit()

    return jsonify({
        "message": "Complaint updated successfully",
        "complaint": {
            "id": complaint.id,
            "title": complaint.title,
            "description": complaint.description,
            "category": complaint.category,
            "location": complaint.location,
            "status": complaint.status,
            "user_id": complaint.user_id,
            "created_at": complaint.created_at.isoformat()
        }
    }), 200
# ==========================================
# UPDATE COMPLAINT STATUS - OFFICER ONLY
# ==========================================

@complaint_bp.route("/<int:complaint_id>/status", methods=["PUT"])
@jwt_required()
def update_complaint_status(complaint_id):

    user_id = get_jwt_identity()

    user = User.query.get(int(user_id))

    if not user:
        return jsonify({
            "message": "User not found"
        }), 404

    if user.role != "Officer":
        return jsonify({
            "message": "Officer access required"
        }), 403

    complaint = Complaint.query.get(complaint_id)

    if not complaint:
        return jsonify({
            "message": "Complaint not found"
        }), 404

    data = request.get_json()

    if not data or not data.get("status"):
        return jsonify({
            "message": "Status is required"
        }), 400

    new_status = data.get("status")

    allowed_statuses = [
        "Pending",
        "In Progress",
        "Resolved"
    ]

    if new_status not in allowed_statuses:
        return jsonify({
            "message": "Invalid status",
            "allowed_statuses": allowed_statuses
        }), 400

    complaint.status = new_status

    db.session.commit()

    return jsonify({
        "message": "Complaint status updated successfully",
        "complaint": {
            "id": complaint.id,
            "title": complaint.title,
            "status": complaint.status,
            "user_id": complaint.user_id
        }
    }), 200