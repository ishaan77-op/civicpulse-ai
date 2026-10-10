"""
Resolution Review routes — Feature 2: Chief Officer Review & Final Resolution.

Officer endpoints:
  POST /api/officers/complaints/<id>/resolution-review
      Submit a final-resolution request (completion note + evidence photo).
      Sets complaint.status → "Pending Review".

  GET  /api/officers/complaints/<id>/resolution-review
      Retrieve the current resolution review for a complaint (Officer or
      Chief Officer). Includes the latest review and its decision.

Chief Officer endpoints (role == "Chief Officer" only):
  GET  /api/chief-officer/resolution-queue
      List all complaints currently awaiting final review.

  PUT  /api/chief-officer/resolution-reviews/<review_id>/decide
      Approve or reject a pending resolution request.
      Approve → complaint.status = "Resolved"
      Reject  → complaint.status = "In Progress", stores rejection_note.

Security guarantees (all enforced server-side):
  - Only Officers can submit resolution requests.
  - Only Chief Officers can approve/reject.
  - A submitting Officer cannot approve their own request.
  - A request that has already been decided cannot be approved twice.
  - Timestamps and reviewer identities always come from the server.
"""
import os
import uuid

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from database.db import db
from models.complaint import Complaint
from models.resolution_review import ResolutionReview, REVIEW_DECISIONS
from models.user import User
from routes.complaints import serialize_complaint
from utils.time_helper import to_iso8601, utc_now


resolution_bp = Blueprint("resolution", __name__)


# ---------------------------------------------------------------------------
# Helper: serialize a ResolutionReview for API responses
# ---------------------------------------------------------------------------

def serialize_review(rv):
    return {
        "id": rv.id,
        "complaint_id": rv.complaint_id,
        "submitted_by": rv.submitted_by,
        "officer_name": rv.officer.name if rv.officer else None,
        "completion_note": rv.completion_note,
        "image_filename": rv.image_filename,
        "image_url": f"/uploads/{rv.image_filename}" if rv.image_filename else None,
        "latitude": rv.latitude,
        "longitude": rv.longitude,
        "submitted_at": to_iso8601(rv.submitted_at),
        "decision": rv.decision,
        "reviewed_by": rv.reviewed_by,
        "reviewer_name": rv.reviewer.name if rv.reviewer else None,
        "rejection_note": rv.rejection_note,
        "reviewed_at": to_iso8601(rv.reviewed_at),
    }


# ---------------------------------------------------------------------------
# POST  /officers/complaints/<id>/resolution-review
# Officer submits final-resolution request
# ---------------------------------------------------------------------------

@resolution_bp.route("/officers/complaints/<int:complaint_id>/resolution-review", methods=["POST"])
@jwt_required()
def submit_resolution_review(complaint_id):
    """Submit a final-resolution evidence request for Chief Officer review.

    Accepts multipart/form-data so a final evidence photo can be included.
    The complaint status advances to "Pending Review".
    A new submission is blocked if one is already pending (officer must wait
    for the Chief Officer to decide before re-submitting).
    """
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"message": "Complaint not found"}), 404

    if complaint.spam_review_status == "Confirmed":
        return jsonify({"message": "Cannot submit resolution for a complaint confirmed as spam"}), 400

    # Reject if a review is already pending — the Chief Officer must decide
    # before the officer can re-submit.
    existing_pending = ResolutionReview.query.filter_by(
        complaint_id=complaint_id, decision=None
    ).first()
    if existing_pending:
        return jsonify({
            "message": "A resolution review is already pending for this complaint. "
                       "Wait for the Chief Officer's decision before re-submitting."
        }), 400

    data = request.form
    completion_note = (data.get("completion_note") or "").strip()
    if not completion_note:
        return jsonify({"message": "A completion note is required"}), 400

    # Final evidence photo is mandatory for resolution requests.
    image = request.files.get("image")
    if not image or not image.filename:
        return jsonify({"message": "A final evidence photo is required"}), 400

    original_filename = secure_filename(image.filename)
    unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
    upload_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    os.makedirs(upload_folder, exist_ok=True)
    image.save(os.path.join(upload_folder, unique_filename))

    latitude = None
    longitude = None
    lat_raw = data.get("latitude")
    lng_raw = data.get("longitude")
    if lat_raw is not None and lng_raw is not None:
        try:
            latitude = float(lat_raw)
            longitude = float(lng_raw)
        except (TypeError, ValueError):
            return jsonify({"message": "GPS coordinates are invalid"}), 400

    rv = ResolutionReview(
        complaint_id=complaint_id,
        submitted_by=user.id,
        completion_note=completion_note,
        image_filename=unique_filename,
        latitude=latitude,
        longitude=longitude,
        submitted_at=utc_now(),
    )

    # Advance complaint to "Pending Review" so officers and Chief Officers
    # know it is awaiting final sign-off. The complaint must NOT become
    # "Resolved" here — that only happens on Chief Officer approval.
    complaint.status = "Pending Review"

    db.session.add(rv)
    db.session.commit()

    return jsonify({
        "message": "Resolution review submitted. Awaiting Chief Officer approval.",
        "review": serialize_review(rv),
        "complaint": serialize_complaint(complaint),
    }), 201


# ---------------------------------------------------------------------------
# GET  /officers/complaints/<id>/resolution-review
# Officer or Chief Officer retrieves the current review for a complaint
# ---------------------------------------------------------------------------

@resolution_bp.route("/officers/complaints/<int:complaint_id>/resolution-review", methods=["GET"])
@jwt_required()
def get_resolution_review(complaint_id):
    """Return the most recent resolution review for a complaint.

    Accessible by Officers (to see status of their own submission) and
    Chief Officers (to review the evidence). Citizens cannot access this.
    """
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Chief Officer", "Admin"]:
        return jsonify({"message": "Officer, Chief Officer, or Admin access required"}), 403

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"message": "Complaint not found"}), 404

    # Return the most recent review (ordered by submission time descending).
    review = (
        ResolutionReview.query
        .filter_by(complaint_id=complaint_id)
        .order_by(ResolutionReview.submitted_at.desc())
        .first()
    )

    return jsonify({
        "complaint_id": complaint_id,
        "review": serialize_review(review) if review else None,
    }), 200


# ---------------------------------------------------------------------------
# GET  /chief-officer/resolution-queue
# Chief Officer retrieves all complaints awaiting final review
# ---------------------------------------------------------------------------

@resolution_bp.route("/chief-officer/resolution-queue", methods=["GET"])
@jwt_required()
def get_resolution_queue():
    """Return all complaints currently in the 'Pending Review' state,
    including their pending resolution review data.

    Only accessible by Chief Officers.
    """
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role != "Chief Officer":
        return jsonify({"message": "Chief Officer access required"}), 403

    # Find all pending (undecided) resolution reviews.
    pending_reviews = (
        ResolutionReview.query
        .filter_by(decision=None)
        .order_by(ResolutionReview.submitted_at.asc())
        .all()
    )

    return jsonify({
        "total": len(pending_reviews),
        "queue": [
            {
                "review": serialize_review(rv),
                "complaint": serialize_complaint(rv.complaint),
            }
            for rv in pending_reviews
        ],
    }), 200


# ---------------------------------------------------------------------------
# PUT  /chief-officer/resolution-reviews/<review_id>/decide
# Chief Officer approves or rejects a pending resolution request
# ---------------------------------------------------------------------------

@resolution_bp.route(
    "/chief-officer/resolution-reviews/<int:review_id>/decide",
    methods=["PUT"]
)
@jwt_required()
def decide_resolution_review(review_id):
    """Approve or reject a pending final-resolution request.

    On approval:
      - complaint.status → "Resolved"
    On rejection:
      - complaint.status → "In Progress" (officer must re-submit evidence)
      - rejection_note is stored (required when rejecting)

    Security:
      - Only "Chief Officer" role can call this.
      - The submitting officer cannot review their own request.
      - A request already decided cannot be decided again (no double-approval).
    """
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role != "Chief Officer":
        return jsonify({"message": "Chief Officer access required"}), 403

    rv = ResolutionReview.query.get(review_id)
    if not rv:
        return jsonify({"message": "Resolution review not found"}), 404

    # Prevent double-approval / double-rejection.
    if rv.decision is not None:
        return jsonify({
            "message": f"This review has already been decided: {rv.decision}"
        }), 400

    # Prevent self-review: the submitting officer cannot be the reviewer.
    if rv.submitted_by == user.id:
        return jsonify({
            "message": "The submitting Officer cannot review their own resolution request"
        }), 403

    data = request.get_json()
    if not data:
        return jsonify({"message": "Request body is required"}), 400

    decision = (data.get("decision") or "").strip()
    if decision not in REVIEW_DECISIONS:
        return jsonify({
            "message": "Invalid decision",
            "allowed_decisions": REVIEW_DECISIONS,
        }), 400

    rejection_note = (data.get("rejection_note") or "").strip()
    if decision == "Rejected" and not rejection_note:
        return jsonify({"message": "A rejection note is required when rejecting a resolution request"}), 400

    rv.decision = decision
    rv.reviewed_by = user.id
    rv.reviewed_at = utc_now()

    complaint = rv.complaint

    if decision == "Approved":
        complaint.status = "Resolved"
        rv.rejection_note = None
    else:
        # Revert to "In Progress" so the Officer can perform corrective work
        # and re-submit evidence.
        complaint.status = "In Progress"
        rv.rejection_note = rejection_note

    db.session.commit()

    return jsonify({
        "message": f"Resolution review {decision.lower()}.",
        "review": serialize_review(rv),
        "complaint": serialize_complaint(complaint),
    }), 200
