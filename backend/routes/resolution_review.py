"""Officer field-work and Chief Officer issue-resolution workflow routes."""

import hashlib
import json
import os
import uuid

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from database.db import db
from models.civic_issue import CivicIssue
from models.complaint import Complaint
from models.resolution_review import (
    COMPLAINT_DISPOSITIONS,
    ResolutionReview,
    ResolutionReviewComplaintDisposition,
)
from models.user import User
from models.work_update import ALLOWED_WORK_UPDATE_STATUSES, IssueWorkUpdate
from routes.complaints import serialize_complaint
from routes.officers import serialize_issue
from services.resolution_workflow import (
    NO_ELIGIBLE_COMPLAINTS_MESSAGE,
    StaleReviewError,
    WorkflowError,
    approve_review,
    bump_review_revision,
    change_issue_status,
    eligible_complaints,
    ensure_issue_complaint,
    excluded_complaints,
    lock_issue_at_revision,
    moderation_pending_complaints,
    stale_reviews_awaiting_resubmission,
    validate_review_coverage,
)
from utils.private_files import send_private_image
from utils.time_helper import to_iso8601, utc_now
from utils.upload_validation import (
    UploadError,
    save_upload,
    upload_sha256,
    validate_image_upload,
)
from utils.validators import ValidationError, parse_optional_coordinates


resolution_bp = Blueprint("resolution", __name__)
WORKER_ROLES = ("Officer", "Admin")
STAFF_VIEWER_ROLES = ("Officer", "Admin", "Chief Officer")


def _current_user():
    identity = get_jwt_identity()
    return User.query.get(int(identity)) if identity is not None else None


def _require_roles(roles, message):
    user = _current_user()
    if not user or user.role not in roles:
        return None, (jsonify({"message": message}), 403)
    return user, None


def _safe_remove(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            current_app.logger.warning("Could not remove failed workflow upload")


def _parse_optional_complaint_id(raw_value):
    if raw_value in (None, ""):
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        raise WorkflowError("Complaint ID must be a whole number") from None


def _work_fingerprint(issue_id, complaint_id, status, note, latitude, longitude, image_digest):
    payload = {
        "issue_id": issue_id,
        "complaint_id": complaint_id,
        "status": status,
        "note": note,
        "latitude": latitude,
        "longitude": longitude,
        "image_sha256": image_digest,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def serialize_work_update(update):
    return {
        "id": update.id,
        "issue_id": update.issue_id,
        "complaint_id": update.complaint_id,
        "officer_id": update.officer_id,
        "status": update.status,
        "note": update.note,
        "image_path": f"/issues/{update.issue_id}/work-updates/{update.id}/image" if update.image_filename else None,
        "latitude": update.latitude,
        "longitude": update.longitude,
        "created_at": to_iso8601(update.created_at),
    }


def serialize_review(review, include_dispositions=True):
    data = {
        "id": review.id,
        "issue_id": review.issue_id,
        "submitted_by": review.submitted_by,
        "completion_note": review.completion_note,
        "image_path": f"/issues/{review.issue_id}/resolution-reviews/{review.id}/image",
        "latitude": review.latitude,
        "longitude": review.longitude,
        "issue_revision": review.issue_revision,
        "state": review.state,
        "submitted_at": to_iso8601(review.submitted_at),
        "reviewed_by": review.reviewed_by,
        "reviewed_at": to_iso8601(review.reviewed_at),
        "rejection_reason": review.rejection_reason,
        "stale_reason": review.stale_reason,
        "stale_at": to_iso8601(review.stale_at),
        "supersedes_review_id": review.supersedes_review_id,
    }
    if include_dispositions:
        data["dispositions"] = [
            {
                "complaint_id": row.complaint_id,
                "disposition": row.disposition,
                "note": row.note,
                "created_at": to_iso8601(row.created_at),
            }
            for row in review.complaint_dispositions
        ]
    return data


def _issue_context(issue):
    all_complaints = Complaint.query.filter_by(issue_id=issue.id).order_by(
        Complaint.created_at.asc()
    ).all()
    excluded = {complaint.id: reason for complaint, reason in excluded_complaints(issue.id)}
    pending_moderation = {complaint.id for complaint in moderation_pending_complaints(issue.id)}
    return {
        "issue": serialize_issue(issue),
        "complaints": [serialize_complaint(complaint) for complaint in all_complaints],
        "review_checklist": [
            {
                "complaint_id": complaint.id,
                "eligible": complaint.id not in excluded and complaint.id not in pending_moderation,
                "excluded_reason": excluded.get(complaint.id),
                "blocked_reason": "Awaiting spam moderation" if complaint.id in pending_moderation else None,
            }
            for complaint in all_complaints
        ],
    }


@resolution_bp.route("/issues/<int:issue_id>/work-updates", methods=["POST"])
@jwt_required()
def create_work_update(issue_id):
    officer, denied = _require_roles(WORKER_ROLES, "Officer or Admin access required")
    if denied:
        return denied
    issue = CivicIssue.query.get(issue_id)
    if not issue:
        return jsonify({"message": "Issue not found"}), 404

    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key or len(key) > 128:
        return jsonify({"message": "A valid Idempotency-Key header is required"}), 400

    note = (request.form.get("note") or "").strip()
    status = (request.form.get("status") or "In Progress").strip()
    if not note:
        return jsonify({"message": "A progress note is required"}), 400
    if status not in ALLOWED_WORK_UPDATE_STATUSES:
        return jsonify({"message": "Invalid work-update status", "allowed_statuses": list(ALLOWED_WORK_UPDATE_STATUSES)}), 400

    try:
        complaint_id = _parse_optional_complaint_id(request.form.get("complaint_id"))
        if complaint_id is not None:
            ensure_issue_complaint(issue.id, complaint_id)
        latitude, longitude = parse_optional_coordinates(
            request.form.get("latitude"), request.form.get("longitude")
        )
    except (WorkflowError, ValidationError) as error:
        return jsonify({"message": str(error)}), 400

    image = request.files.get("image")
    image_digest = None
    original_filename = None
    if image and image.filename:
        try:
            original_filename = validate_image_upload(image, current_app.config["MAX_UPLOAD_BYTES"])
            image_digest = upload_sha256(image)
        except UploadError as error:
            return jsonify({"message": error.message}), error.status_code

    fingerprint = _work_fingerprint(
        issue.id, complaint_id, status, note, latitude, longitude, image_digest
    )
    existing = IssueWorkUpdate.query.filter_by(
        officer_id=officer.id, idempotency_key=key
    ).first()
    if existing:
        if existing.request_fingerprint == fingerprint:
            return jsonify({"message": "Work update already recorded", "work_update": serialize_work_update(existing)}), 200
        return jsonify({"message": "Idempotency-Key was already used with a different work update"}), 409

    saved_path = None
    try:
        filename = None
        if original_filename:
            filename = f"{uuid.uuid4().hex}_{original_filename}"
            saved_path = save_upload(image, current_app.config["PRIVATE_UPLOAD_FOLDER"], filename)

        update = IssueWorkUpdate(
            issue_id=issue.id,
            complaint_id=complaint_id,
            officer_id=officer.id,
            status=status,
            note=note,
            image_filename=filename,
            latitude=latitude,
            longitude=longitude,
            idempotency_key=key,
            request_fingerprint=fingerprint,
        )
        db.session.add(update)
        if status == "In Progress":
            change_issue_status(issue, "In Progress", officer.id)
        bump_review_revision(issue, "Field-work evidence or progress changed")
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        _safe_remove(saved_path)
        existing = IssueWorkUpdate.query.filter_by(
            officer_id=officer.id, idempotency_key=key
        ).first()
        if existing and existing.request_fingerprint == fingerprint:
            return jsonify({"message": "Work update already recorded", "work_update": serialize_work_update(existing)}), 200
        return jsonify({"message": "Idempotency-Key was already used with a different work update"}), 409
    except Exception:
        db.session.rollback()
        _safe_remove(saved_path)
        current_app.logger.exception("Failed to create issue work update")
        return jsonify({"message": "Could not record the work update"}), 500

    return jsonify({"message": "Work update recorded", "work_update": serialize_work_update(update)}), 201


@resolution_bp.route("/issues/<int:issue_id>/work-updates", methods=["GET"])
@jwt_required()
def list_work_updates(issue_id):
    _viewer, denied = _require_roles(STAFF_VIEWER_ROLES, "Staff access required")
    if denied:
        return denied
    if not CivicIssue.query.get(issue_id):
        return jsonify({"message": "Issue not found"}), 404
    updates = IssueWorkUpdate.query.filter_by(issue_id=issue_id).order_by(
        IssueWorkUpdate.created_at.asc(), IssueWorkUpdate.id.asc()
    ).all()
    return jsonify({"work_updates": [serialize_work_update(update) for update in updates]}), 200


@resolution_bp.route("/issues/<int:issue_id>/work-updates/<int:update_id>/image", methods=["GET"])
@jwt_required()
def work_update_image(issue_id, update_id):
    """A field-work photo. Staff only; the file is chosen from the stored record, never the request."""
    _viewer, denied = _require_roles(STAFF_VIEWER_ROLES, "Staff access required")
    if denied:
        return denied
    update = IssueWorkUpdate.query.filter_by(id=update_id, issue_id=issue_id).first()
    return send_private_image(
        update.image_filename if update else None,
        current_app.config["PRIVATE_UPLOAD_FOLDER"], current_app.config["UPLOAD_FOLDER"],
        not_found="Photo not found",
    )


@resolution_bp.route("/issues/<int:issue_id>/resolution-reviews", methods=["POST"])
@jwt_required()
def submit_resolution_review(issue_id):
    officer, denied = _require_roles(WORKER_ROLES, "Officer or Admin access required")
    if denied:
        return denied
    issue = CivicIssue.query.get(issue_id)
    if not issue:
        return jsonify({"message": "Issue not found"}), 404

    note = (request.form.get("completion_note") or "").strip()
    if not note:
        return jsonify({"message": "A completion note is required"}), 400
    image = request.files.get("image")
    if not image or not image.filename:
        return jsonify({"message": "Final evidence photo is required"}), 400
    try:
        original_filename = validate_image_upload(image, current_app.config["MAX_UPLOAD_BYTES"])
        latitude, longitude = parse_optional_coordinates(
            request.form.get("latitude"), request.form.get("longitude")
        )
        raw_dispositions = json.loads(request.form.get("dispositions") or "")
    except UploadError as error:
        return jsonify({"message": error.message}), error.status_code
    except (ValidationError, json.JSONDecodeError):
        return jsonify({"message": "Valid dispositions and GPS coordinates are required"}), 400

    if not isinstance(raw_dispositions, list):
        return jsonify({"message": "Dispositions must be a list"}), 400

    try:
        pending_moderation = moderation_pending_complaints(issue.id)
        if pending_moderation:
            raise WorkflowError("Final review is blocked while linked complaints await spam moderation")
        eligible_ids = {complaint.id for complaint in eligible_complaints(issue.id)}
        if not eligible_ids:
            raise WorkflowError(NO_ELIGIBLE_COMPLAINTS_MESSAGE)
        provided_ids = set()
        normalized_dispositions = []
        for item in raw_dispositions:
            if not isinstance(item, dict):
                raise WorkflowError("Each complaint disposition must be an object")
            complaint_id = _parse_optional_complaint_id(item.get("complaint_id"))
            if complaint_id is None or complaint_id in provided_ids:
                raise WorkflowError("Each eligible complaint requires one disposition")
            ensure_issue_complaint(issue.id, complaint_id)
            disposition = (item.get("disposition") or "").strip()
            disposition_note = (item.get("note") or "").strip()
            if disposition not in COMPLAINT_DISPOSITIONS or not disposition_note:
                raise WorkflowError("Each disposition requires an allowed value and a note")
            if disposition == "Additional Work Required":
                raise WorkflowError("Complete outstanding work before requesting final review")
            provided_ids.add(complaint_id)
            normalized_dispositions.append((complaint_id, disposition, disposition_note))
        if provided_ids != eligible_ids:
            raise WorkflowError("The submission must account for every eligible linked complaint")

        raw_supersedes = request.form.get("supersedes_review_id")
        supersedes_id = _parse_optional_complaint_id(raw_supersedes)
        pending = ResolutionReview.query.filter_by(issue_id=issue.id, state="Pending").first()
        superseded_review = None
        if pending:
            if supersedes_id != pending.id or pending.submitted_by != officer.id:
                raise WorkflowError("A resolution review is already awaiting Chief Officer decision")
            superseded_review = pending
        elif supersedes_id is not None:
            superseded_review = ResolutionReview.query.filter_by(
                id=supersedes_id, issue_id=issue.id, submitted_by=officer.id
            ).first()
            if not superseded_review:
                raise WorkflowError("The review to supersede does not belong to this officer and issue")
    except WorkflowError as error:
        return jsonify({"message": str(error)}), 400

    saved_path = None
    try:
        filename = f"{uuid.uuid4().hex}_{original_filename}"
        saved_path = save_upload(image, current_app.config["PRIVATE_UPLOAD_FOLDER"], filename)
        # Eligibility above was read against this revision; if the issue has
        # changed since, the dispositions may no longer cover it.
        if not lock_issue_at_revision(issue.id, issue.review_revision):
            raise WorkflowError("The issue changed while the review was being prepared; please review it again")
        if superseded_review and superseded_review.state == "Pending":
            superseded_review.state = "Superseded"
            db.session.flush()
        review = ResolutionReview(
            issue_id=issue.id,
            submitted_by=officer.id,
            completion_note=note,
            image_filename=filename,
            latitude=latitude,
            longitude=longitude,
            issue_revision=issue.review_revision,
            supersedes_review_id=superseded_review.id if superseded_review else None,
        )
        db.session.add(review)
        db.session.flush()
        for complaint_id, disposition, disposition_note in normalized_dispositions:
            db.session.add(ResolutionReviewComplaintDisposition(
                resolution_review_id=review.id,
                complaint_id=complaint_id,
                disposition=disposition,
                note=disposition_note,
            ))
        change_issue_status(issue, "Pending Review", officer.id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        _safe_remove(saved_path)
        return jsonify({"message": "A resolution review is already awaiting Chief Officer decision"}), 409
    except WorkflowError as error:
        db.session.rollback()
        _safe_remove(saved_path)
        return jsonify({"message": str(error)}), 409
    except Exception:
        db.session.rollback()
        _safe_remove(saved_path)
        current_app.logger.exception("Failed to submit resolution review")
        return jsonify({"message": "Could not submit the resolution review"}), 500

    return jsonify({"message": "Resolution review submitted", "review": serialize_review(review)}), 201


@resolution_bp.route("/issues/<int:issue_id>/resolution-reviews", methods=["GET"])
@jwt_required()
def list_resolution_reviews(issue_id):
    _viewer, denied = _require_roles(STAFF_VIEWER_ROLES, "Staff access required")
    if denied:
        return denied
    issue = CivicIssue.query.get(issue_id)
    if not issue:
        return jsonify({"message": "Issue not found"}), 404
    reviews = ResolutionReview.query.filter_by(issue_id=issue.id).order_by(
        ResolutionReview.submitted_at.desc(), ResolutionReview.id.desc()
    ).all()
    data = _issue_context(issue)
    data["reviews"] = [serialize_review(review) for review in reviews]
    return jsonify(data), 200


@resolution_bp.route("/issues/<int:issue_id>/resolution-reviews/<int:review_id>/image", methods=["GET"])
@jwt_required()
def resolution_review_image(issue_id, review_id):
    """A completion-evidence photo, in any review state. Staff only.

    Citizens see the approved photo through ``/complaints/<id>/resolution-evidence/after-image``,
    which applies the citizen allow-list; they never reach this route."""
    _viewer, denied = _require_roles(STAFF_VIEWER_ROLES, "Staff access required")
    if denied:
        return denied
    review = ResolutionReview.query.filter_by(id=review_id, issue_id=issue_id).first()
    return send_private_image(
        review.image_filename if review else None,
        current_app.config["PRIVATE_UPLOAD_FOLDER"], current_app.config["UPLOAD_FOLDER"],
        not_found="Photo not found",
    )


@resolution_bp.route("/chief-officer/resolution-queue", methods=["GET"])
@jwt_required()
def resolution_queue():
    _chief, denied = _require_roles(("Chief Officer",), "Chief Officer access required")
    if denied:
        return denied
    reviews = ResolutionReview.query.filter_by(state="Pending").order_by(
        ResolutionReview.submitted_at.asc(), ResolutionReview.id.asc()
    ).all()
    # "queue" keeps its meaning: reviews awaiting a decision.  "stale" lists
    # reviews that were withdrawn by new information while their issue is
    # still Pending Review; they cannot be approved, only resubmitted.
    return jsonify({
        "queue": [
            {**_issue_context(review.issue), "review": serialize_review(review)}
            for review in reviews
        ],
        "stale": [
            {**_issue_context(review.issue), "review": serialize_review(review)}
            for review in stale_reviews_awaiting_resubmission()
        ],
    }), 200


@resolution_bp.route("/chief-officer/resolution-reviews/<int:review_id>/decision", methods=["PUT"])
@jwt_required()
def decide_resolution_review(review_id):
    chief, denied = _require_roles(("Chief Officer",), "Chief Officer access required")
    if denied:
        return denied
    review = ResolutionReview.query.get(review_id)
    if not review:
        return jsonify({"message": "Resolution review not found"}), 404
    if review.submitted_by == chief.id:
        return jsonify({"message": "The submitting officer cannot decide this review"}), 403
    if review.state != "Pending":
        return jsonify({"message": f"This review is already {review.state.lower()}"}), 409

    data = request.get_json() or {}
    decision = (data.get("decision") or "").strip()
    if decision not in ("Approved", "Rejected"):
        return jsonify({"message": "Decision must be Approved or Rejected"}), 400

    issue = review.issue
    if decision == "Rejected":
        reason = (data.get("rejection_reason") or "").strip()
        if len(reason) < 10:
            return jsonify({"message": "A meaningful rejection reason is required"}), 400
        try:
            transitioned = ResolutionReview.query.filter_by(
                id=review.id, state="Pending"
            ).update({
                "state": "Rejected",
                "reviewed_by": chief.id,
                "reviewed_at": utc_now(),
                "rejection_reason": reason,
            }, synchronize_session=False)
            if transitioned != 1:
                raise WorkflowError("This review has already been decided")
            change_issue_status(issue, "In Progress", chief.id)
            db.session.commit()
        except WorkflowError as error:
            db.session.rollback()
            return jsonify({"message": str(error)}), 409
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to reject resolution review")
            return jsonify({"message": "Could not decide the resolution review"}), 500
        return jsonify({"message": "Resolution review rejected"}), 200

    try:
        approve_review(issue, review, chief.id)
        db.session.commit()
    except StaleReviewError as error:
        # The review's Stale marking is the outcome; keep it.
        db.session.commit()
        return jsonify({"message": str(error)}), 409
    except WorkflowError as error:
        db.session.rollback()
        return jsonify({"message": str(error)}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to approve resolution review")
        return jsonify({"message": "Could not decide the resolution review"}), 500

    refreshed = db.session.get(ResolutionReview, review_id)
    return jsonify({
        "message": "Resolution review approved",
        "review": serialize_review(refreshed),
        "issue": serialize_issue(issue),
    }), 200
