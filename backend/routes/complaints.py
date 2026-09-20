import os
import uuid

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from database.db import db
from models.complaint import Complaint
from models.notification import Notification
from models.user import User
from services.ai_service import analyze_complaint
from services.issue_clustering import get_or_create_issue_for_complaint
from utils.time_helper import to_iso8601, utc_now


complaint_bp = Blueprint("complaint", __name__)

REJECTION_REASONS = [
    "Private Property",
    "Private Society / Apartment",
    "Outside NMC Jurisdiction",
    "Not a Municipal Responsibility",
    "Other",
]


def serialize_complaint(complaint, ai_analysis=None, include_spam=False):
    data = {
        "id": complaint.id,
        "title": complaint.title,
        "description": complaint.description,
        "category": complaint.category,
        "location": complaint.location,
        "latitude": complaint.latitude,
        "longitude": complaint.longitude,
        "status": complaint.status,
        "user_id": complaint.user_id,
        "image_filename": complaint.image_filename,
        "image_url": f"/uploads/{complaint.image_filename}" if complaint.image_filename else None,
        "created_at": to_iso8601(complaint.created_at),
        "ai_analysis": ai_analysis or {
            "priority": complaint.ai_priority,
            "department": complaint.ai_department,
            "visual_observation": complaint.ai_visual_observation,
            "summary": complaint.ai_summary
        },
        # Non-sensitive: lets a citizen see that their report was grouped
        # with a wider civic issue and its current status, without ever
        # rewriting complaint.status itself.
        "civic_issue": {
            "id": complaint.issue.id,
            "status": complaint.issue.status,
            "report_count": complaint.issue.report_count
        } if complaint.issue else None,
        # Not spam - a genuine complaint can still be outside NMC/government
        # jurisdiction. Shown to the reporting citizen too (that's the whole
        # point), just without the internal reviewer/reopen audit trail
        # below, which is Officer/Admin only.
        "rejection": {
            "status": "Rejected - Out of Scope",
            "reason": complaint.rejection_reason,
            "explanation": complaint.rejection_explanation,
            "reviewed_at": to_iso8601(complaint.rejected_at),
        } if complaint.rejection_status == "Rejected" else None
    }

    # Spam/misreport moderation internals are restricted to Officer/Admin
    # moderation endpoints - never exposed to the reporting citizen.
    if include_spam:
        data["spam_review"] = {
            "ai_spam_flag": complaint.ai_spam_flag,
            "ai_spam_reason": complaint.ai_spam_reason,
            "ai_spam_confidence": complaint.ai_spam_confidence,
            "spam_review_status": complaint.spam_review_status,
            "spam_reviewed_by": complaint.spam_reviewed_by,
            "spam_reviewed_at": to_iso8601(complaint.spam_reviewed_at),
            "spam_reopened_by": complaint.spam_reopened_by,
            "spam_reopened_at": to_iso8601(complaint.spam_reopened_at),
        }
        data["rejection_audit"] = {
            "rejection_status": complaint.rejection_status,
            "rejection_reason": complaint.rejection_reason,
            "rejection_explanation": complaint.rejection_explanation,
            "rejected_by": complaint.rejected_by,
            "rejected_at": to_iso8601(complaint.rejected_at),
            "rejection_reopened_by": complaint.rejection_reopened_by,
            "rejection_reopened_at": to_iso8601(complaint.rejection_reopened_at),
        }

    return data


# ==========================================
# CREATE COMPLAINT
# ==========================================

@complaint_bp.route("/", methods=["POST"])
@jwt_required()
def create_complaint():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user:
        return jsonify({"message": "User not found"}), 404

    # Complaint submission is a Citizen-only action. Officers/Admins work
    # complaints, they don't file them - enforced here, not just hidden
    # in the UI.
    if user.role != "Citizen":
        return jsonify({"message": "Only citizens can submit complaints"}), 403

    data = request.form

    if not data:
        return jsonify({"message": "Request body is required"}), 400

    title = data.get("title")
    description = data.get("description")
    address = data.get("address")
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if not title or not description or latitude is None or longitude is None:
        return jsonify({
            "message": "Title, description and a confirmed map location are required"
        }), 400

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return jsonify({"message": "Location coordinates are invalid"}), 400

    location = address or f"{latitude:.6f}, {longitude:.6f}"

    image = request.files.get("image")

    if not image or not image.filename:
        return jsonify({
            "message": "A camera photo of the issue is required"
        }), 400

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

    # AI-detected likely mismatch/spam signal. Only ever set from a
    # *successful* AI analysis (this line only runs once ai_result exists) -
    # an AI/API failure never reaches here and is handled above as a plain
    # technical failure, never as spam. A missing/falsy spam_flag from the
    # AI (including a response that omits it) defaults to "not flagged".
    spam_flagged = bool(ai_result.get("spam_flag"))

    complaint = Complaint(
        title=title,
        description=description,
        category=ai_result.get("category", "Other"),
        location=location,
        latitude=latitude,
        longitude=longitude,
        user_id=int(user_id),
        image_filename=unique_filename if image_path else None,
        ai_priority=ai_result.get("priority"),
        ai_department=ai_result.get("department"),
        ai_visual_observation=ai_result.get("visual_observation"),
        ai_summary=ai_result.get("summary"),
        ai_spam_flag=spam_flagged,
        ai_spam_reason=ai_result.get("spam_reason") if spam_flagged else None,
        ai_spam_confidence=ai_result.get("spam_confidence") if spam_flagged else None,
        spam_review_status="Pending" if spam_flagged else "NotFlagged"
    )

    # Duplicate/same-issue correlation. Purely additive: it only groups
    # this complaint with a likely-matching CivicIssue (or starts a new
    # one) so officers see one work item instead of many duplicate-looking
    # complaints. It never rejects, flags, punishes, suspends, or deletes
    # anything, and never touches spam_count - that stays a fully separate,
    # human-reviewed process.
    issue = get_or_create_issue_for_complaint(
        category=complaint.category,
        latitude=latitude,
        longitude=longitude,
        ai_summary=complaint.ai_summary,
        description=description,
        location_label=location
    )
    db.session.add(issue)
    db.session.flush()
    complaint.issue_id = issue.id

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

    # Confirmed-spam complaints are moderation history, not active civic
    # complaints - excluded here so they never appear in the citizen's own
    # active list, while the row (and its spam reason/audit trail) is kept.
    complaints = Complaint.query.filter(
        Complaint.user_id == int(user_id),
        Complaint.spam_review_status != "Confirmed"
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
    if "latitude" in data and "longitude" in data:
        try:
            complaint.latitude = float(data["latitude"])
            complaint.longitude = float(data["longitude"])
        except (TypeError, ValueError):
            return jsonify({"message": "Location coordinates are invalid"}), 400

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


# ==========================================
# REJECT / OUT OF SCOPE - OFFICER/ADMIN ONLY
#
# Conceptually separate from spam moderation (routes/officers.py): a
# complaint here can be entirely genuine but simply outside NMC/government
# jurisdiction. This never touches spam_count, is_suspended, or
# spam_review_status, and never uses the Confirmed-spam workflow.
# ==========================================

@complaint_bp.route("/<int:complaint_id>/reject", methods=["PUT"])
@jwt_required()
def reject_out_of_scope(complaint_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user:
        return jsonify({"message": "User not found"}), 404

    if user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"message": "Complaint not found"}), 404

    if complaint.rejection_status == "Rejected":
        return jsonify({
            "message": "This complaint has already been rejected as out of scope"
        }), 400

    data = request.get_json() or {}
    reason = data.get("reason")
    explanation = (data.get("explanation") or "").strip()

    if reason not in REJECTION_REASONS:
        return jsonify({
            "message": "A valid rejection reason is required",
            "allowed_reasons": REJECTION_REASONS
        }), 400

    if reason == "Other" and not explanation:
        return jsonify({
            "message": "An explanation is required when the reason is Other"
        }), 400

    complaint.rejection_status = "Rejected"
    complaint.rejection_reason = reason
    complaint.rejection_explanation = explanation or None
    complaint.rejected_by = user.id
    complaint.rejected_at = utc_now()

    # This complaint was never real corroborating evidence for its civic
    # issue - stop counting it, but keep the complaint's own link intact
    # (nothing about the complaint or the issue is deleted). Mirrors the
    # same adjustment made for a Confirmed spam decision in routes/officers.py.
    if complaint.issue and complaint.issue.report_count > 0:
        complaint.issue.report_count -= 1

    db.session.add(Notification(
        user_id=complaint.user_id,
        complaint_id=complaint.id,
        message=(
            f'Your complaint "{complaint.title}" was reviewed but rejected because it is outside '
            f"municipal/government jurisdiction. Reason: {reason}."
        )
    ))

    db.session.commit()

    return jsonify({
        "message": "Complaint rejected as out of scope",
        "complaint": serialize_complaint(complaint, include_spam=True)
    }), 200


@complaint_bp.route("/<int:complaint_id>/reopen-rejection", methods=["PUT"])
@jwt_required()
def reopen_rejected_complaint(complaint_id):
    """Corrects a mistaken out-of-scope rejection by sending the complaint
    back into active review. Never erases the previous decision - the
    rejection reason/reviewer stay in place as audit history, alongside the
    new reopened_by/reopened_at stamp. Mirrors the spam reopen endpoint in
    routes/officers.py."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user:
        return jsonify({"message": "User not found"}), 404

    if user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"message": "Complaint not found"}), 404

    if complaint.rejection_status != "Rejected":
        return jsonify({
            "message": f"Only a rejected complaint can be reopened (status: {complaint.rejection_status})"
        }), 400

    if complaint.issue:
        complaint.issue.report_count += 1

    complaint.rejection_status = "NotRejected"
    complaint.rejection_reopened_by = user.id
    complaint.rejection_reopened_at = utc_now()

    db.session.commit()

    return jsonify({
        "message": "Complaint reopened for review",
        "complaint": serialize_complaint(complaint, include_spam=True)
    }), 200