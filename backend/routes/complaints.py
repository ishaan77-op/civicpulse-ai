import os
import uuid

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from database.db import db
from models.complaint import Complaint
from models.user import User
from services.ai_service import analyze_complaint


complaint_bp = Blueprint("complaint", __name__)


def serialize_complaint(complaint, ai_analysis=None):
    return {
        "id": complaint.id,
        "title": complaint.title,
        "description": complaint.description,
        "category": complaint.category,
        "location": complaint.location,
        "status": complaint.status,
        "user_id": complaint.user_id,
        "image_filename": complaint.image_filename,
        "image_url": f"/uploads/{complaint.image_filename}" if complaint.image_filename else None,
        "created_at": complaint.created_at.isoformat() if complaint.created_at else None,
        "ai_analysis": ai_analysis or {
            "priority": complaint.ai_priority,
            "department": complaint.ai_department,
            "visual_observation": complaint.ai_visual_observation,
            "summary": complaint.ai_summary
        }
    }


# ==========================================
# CREATE COMPLAINT
# ==========================================

@complaint_bp.route("/", methods=["POST"])
@jwt_required()
def create_complaint():
    data = request.form

    if not data:
        return jsonify({"message": "Request body is required"}), 400

    title = data.get("title")
    description = data.get("description")
    location = data.get("location")

    if not title or not description or not location:
        return jsonify({"message": "Title, description and location are required"}), 400

    image = request.files.get("image")
    image_path = None
    unique_filename = None

    if image and image.filename:
        original_filename = secure_filename(image.filename)
        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
        upload_folder = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "uploads"
        )
        os.makedirs(upload_folder, exist_ok=True)
        image_path = os.path.join(upload_folder, unique_filename)
        image.save(image_path)

    try:
        ai_result = analyze_complaint(
            title,
            description,
            location,
            image_path
        )
    except Exception as e:
        print("AI ANALYSIS ERROR:", str(e))
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        return jsonify({
            "message": "AI analysis failed",
            "error": str(e)
        }), 500

    user_id = get_jwt_identity()

    complaint = Complaint(
        title=title,
        description=description,
        category=ai_result.get("category", "Other"),
        location=location,
        user_id=int(user_id),
        image_filename=unique_filename if image_path else None,
        ai_priority=ai_result.get("priority"),
        ai_department=ai_result.get("department"),
        ai_visual_observation=ai_result.get("visual_observation"),
        ai_summary=ai_result.get("summary")
    )

    db.session.add(complaint)
    db.session.commit()

    return jsonify({
        "message": "Complaint created successfully",
        "complaint": serialize_complaint(complaint, ai_result)
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
        "complaints": [serialize_complaint(c) for c in complaints]
    }), 200


# ==========================================
# GET SINGLE COMPLAINT
# ==========================================

@complaint_bp.route("/<int:complaint_id>", methods=["GET"])
@jwt_required()
def get_complaint(complaint_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user and user.role in ["Officer", "Admin"]:
        complaint = Complaint.query.get(complaint_id)
    else:
        complaint = Complaint.query.filter_by(
            id=complaint_id,
            user_id=int(user_id)
        ).first()

    if not complaint:
        return jsonify({"message": "Complaint not found"}), 404

    return jsonify({"complaint": serialize_complaint(complaint)}), 200


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
        return jsonify({"message": "Complaint not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"message": "Request body is required"}), 400

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
        "complaint": serialize_complaint(complaint)
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
        return jsonify({"message": "User not found"}), 404

    if user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"message": "Complaint not found"}), 404

    data = request.get_json()
    if not data or not data.get("status"):
        return jsonify({"message": "Status is required"}), 400

    new_status = data.get("status")
    allowed_statuses = ["Pending", "In Progress", "Resolved"]

    if new_status not in allowed_statuses:
        return jsonify({
            "message": "Invalid status",
            "allowed_statuses": allowed_statuses
        }), 400

    complaint.status = new_status
    db.session.commit()

    return jsonify({
        "message": "Complaint status updated successfully",
        "complaint": serialize_complaint(complaint)
    }), 200