"""Chief Officer supervision: overview, ratings, and corrective follow-ups,
plus the Officer's own view of their ratings and assigned corrections.

Authorization is by the account's current role in the database, never by
anything in the request.  Admins are deliberately *not* granted access to
ratings, follow-ups, or the supervisory overview: that needs an explicit
policy decision, so every endpoint here answers 403 to an Admin.
"""

import os
import uuid

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from database.db import db
from models.performance import FOLLOW_UP_STATES, FollowUpEvent, ResolutionFollowUp, ResolutionRating
from models.resolution_review import REVIEW_STATES, ResolutionReview
from models.user import User
from models.ward import Ward
from services import performance as perf
from services.performance import PerformanceError
from utils.time_helper import to_iso8601
from utils.upload_validation import UploadError, save_upload, validate_image_upload

supervision_bp = Blueprint("supervision", __name__)


def _role_or_denied(role, message):
    user = User.query.get(int(get_jwt_identity()))
    if not user or user.role != role:
        return None, (jsonify({"message": message}), 403)
    return user, None


def _chief():
    return _role_or_denied("Chief Officer", "Chief Officer access required")


def _officer():
    return _role_or_denied("Officer", "Officer access required")


def _int_arg(name, default=None):
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        raise PerformanceError(f"{name} must be a whole number") from None


def _limit():
    return max(1, min(_int_arg("limit", 50), 200))


def _offset():
    return max(0, _int_arg("offset", 0))


def _page(query):
    """Apply limit/offset and return (rows, meta) so clients can page; the
    total is of the filtered set, not the page."""
    limit, offset = _limit(), _offset()
    return query.offset(offset).limit(limit).all(), {"total": query.order_by(None).count(), "limit": limit, "offset": offset}


def _fail(error):
    return jsonify({"message": str(error)}), error.status


def _safe_remove(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            current_app.logger.warning("Could not remove a failed follow-up upload")


_EVIDENCE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _evidence_path(follow_up, event, audience):
    prefix = "/chief-officer" if audience == "chief" else "/officers/me"
    return f"{prefix}/follow-ups/{follow_up.id}/events/{event.id}/image"


def _serve_correction_image(follow_up, event_id):
    """Send one correction photo of this follow-up, or 404.

    The file name comes only from the database row of an event that belongs to
    this follow-up; nothing from the request names a file or path. The 404 is
    the same for a missing event, a foreign event and a missing file, so a
    caller learns nothing about records they cannot see."""
    event = FollowUpEvent.query.filter_by(id=event_id, follow_up_id=follow_up.id, event_type="CorrectionSubmitted").first()
    name = event.image_filename if event else None
    folder = current_app.config["PRIVATE_UPLOAD_FOLDER"]
    mimetype = _EVIDENCE_TYPES.get(os.path.splitext(name or "")[1].lower())
    if (not name or not mimetype or name != os.path.basename(name) or name.startswith(".")
            or not os.path.isfile(os.path.join(folder, name))):
        return jsonify({"message": "Evidence not found"}), 404
    response = send_from_directory(folder, name, mimetype=mimetype, conditional=False)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _name(user):
    return {"id": user.id, "name": user.name} if user else None


def _issue_brief(issue):
    return {
        "id": issue.id, "category": issue.category,
        "location_label": issue.location_label, "status": issue.status,
    }


def _effective_ids(review_ids):
    if not review_ids:
        return set()
    return {r.id for r in perf.effective_ratings_query().filter(
        ResolutionRating.resolution_review_id.in_(review_ids)).all()}


def serialize_rating(rating, effective_ids, audience="chief"):
    data = {
        "id": rating.id,
        "resolution_review_id": rating.resolution_review_id,
        "issue": _issue_brief(rating.review.issue),
        "stars": rating.stars,
        "explanation": rating.explanation,
        "needs_follow_up": rating.needs_follow_up,
        "is_effective": rating.id in effective_ids,
        "supersedes_rating_id": rating.supersedes_rating_id,
        "created_at": to_iso8601(rating.created_at),
    }
    if audience == "chief":
        data["rated_officer"] = _name(rating.rated_officer)
        data["rated_by"] = _name(rating.rater)
    return data


def serialize_follow_up(follow_up, audience="chief", detail=False):
    rating = follow_up.rating
    data = {
        "id": follow_up.id,
        "status": follow_up.status,
        "resolution_review_id": follow_up.resolution_review_id,
        "issue": _issue_brief(follow_up.issue),
        "rating": {"stars": rating.stars, "explanation": rating.explanation},
        "assigned_officer": _name(follow_up.assigned_officer),
        "created_at": to_iso8601(follow_up.created_at),
        "updated_at": to_iso8601(follow_up.updated_at),
        "closed_at": to_iso8601(follow_up.closed_at),
    }
    if audience == "chief":
        data["rated_officer"] = _name(follow_up.review.submitter)
    if detail:
        data["events"] = [
            {
                "id": event.id,
                "event_type": event.event_type,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "note": event.note,
                # Correction photos are staff-only: never a public /uploads URL, only the
                # authenticated endpoint below (path is relative to the API root).
                "image_path": _evidence_path(follow_up, event, audience) if event.image_filename else None,
                "created_at": to_iso8601(event.created_at),
                # Staff names are for the Chief Officer; an Officer sees the role only.
                **({"actor": _name(event.actor), "officer": _name(event.officer)} if audience == "chief"
                   else {"actor_role": event.actor.role}),
            }
            for event in follow_up.events
        ]
    return data


# ==========================================
# Overview
# ==========================================

@supervision_bp.route("/chief-officer/overview", methods=["GET"])
@jwt_required()
def overview():
    _chief_user, denied = _chief()
    if denied:
        return denied
    try:
        start = perf.parse_day(request.args.get("from"), "from")
        end = perf.parse_day(request.args.get("to"), "to", end_of_day=True)
        if start and end and end <= start:
            raise PerformanceError("'to' must not be before 'from'")
        data = perf.build_overview(
            ward_id=_int_arg("ward_id"), officer_id=_int_arg("officer_id"), start=start, end=end
        )
    except PerformanceError as error:
        return _fail(error)
    return jsonify(data), 200


# ==========================================
# Directory detail views
# ==========================================

@supervision_bp.route("/chief-officer/wards/<int:ward_id>", methods=["GET"])
@jwt_required()
def ward_view(ward_id):
    _chief_user, denied = _chief()
    if denied:
        return denied
    ward = db.session.get(Ward, ward_id)
    if not ward:
        return jsonify({"message": "Ward not found"}), 404
    return jsonify(perf.ward_detail(ward)), 200


@supervision_bp.route("/chief-officer/officers/<int:officer_id>", methods=["GET"])
@jwt_required()
def officer_view(officer_id):
    _chief_user, denied = _chief()
    if denied:
        return denied
    officer = db.session.get(User, officer_id)
    if not officer or officer.role != "Officer":
        return jsonify({"message": "Officer not found"}), 404
    state = request.args.get("state")
    if state and state not in REVIEW_STATES:
        return jsonify({"message": "Unknown review state", "allowed_states": list(REVIEW_STATES)}), 400
    try:
        limit, offset = _limit(), _offset()
    except PerformanceError as error:
        return _fail(error)
    return jsonify(perf.officer_detail(officer, state=state, limit=limit, offset=offset)), 200


# ==========================================
# Approved work and ratings
# ==========================================

@supervision_bp.route("/chief-officer/approved-work", methods=["GET"])
@jwt_required()
def approved_work():
    _chief_user, denied = _chief()
    if denied:
        return denied
    try:
        officer_id = _int_arg("officer_id")
        start = perf.parse_day(request.args.get("from"), "from")
        end = perf.parse_day(request.args.get("to"), "to", end_of_day=True)
        _limit(), _offset()  # validate paging arguments up front
    except PerformanceError as error:
        return _fail(error)
    rated = request.args.get("rated")

    query = ResolutionReview.query.filter(ResolutionReview.state == "Approved")
    if officer_id is not None:
        query = query.filter(ResolutionReview.submitted_by == officer_id)
    if start:
        query = query.filter(ResolutionReview.reviewed_at >= start)
    if end:
        query = query.filter(ResolutionReview.reviewed_at < end)
    rated_ids = db.session.query(ResolutionRating.resolution_review_id)
    if rated == "true":
        query = query.filter(ResolutionReview.id.in_(rated_ids))
    elif rated == "false":
        query = query.filter(~ResolutionReview.id.in_(rated_ids))
    reviews, page = _page(query.order_by(ResolutionReview.reviewed_at.desc(), ResolutionReview.id.desc()))

    ids = [r.id for r in reviews]
    effective = {r.resolution_review_id: r for r in perf.effective_ratings_query().filter(
        ResolutionRating.resolution_review_id.in_(ids)).all()} if ids else {}
    follow_ups = {f.resolution_review_id: f for f in ResolutionFollowUp.query.filter(
        ResolutionFollowUp.resolution_review_id.in_(ids)).all()} if ids else {}
    return jsonify({"approved_work": [
        {
            "resolution_review_id": review.id,
            "issue": _issue_brief(review.issue),
            "officer": _name(review.submitter),
            "submitted_at": to_iso8601(review.submitted_at),
            "approved_at": to_iso8601(review.reviewed_at),
            # The submission being judged, so the rating is made with the evidence in view.
            "evidence": {
                "completion_note": review.completion_note,
                "image_url": f"/uploads/{review.image_filename}",
                "dispositions": len(review.complaint_dispositions),
            },
            "rating": ({"id": effective[review.id].id, "stars": effective[review.id].stars}
                       if review.id in effective else None),
            "follow_up": ({"id": follow_ups[review.id].id, "status": follow_ups[review.id].status}
                          if review.id in follow_ups else None),
        }
        for review in reviews
    ], **page}), 200


@supervision_bp.route("/chief-officer/resolution-reviews/<int:review_id>/rating", methods=["POST"])
@jwt_required()
def rate_review(review_id):
    chief, denied = _chief()
    if denied:
        return denied
    review = db.session.get(ResolutionReview, review_id)
    if not review:
        return jsonify({"message": "Resolution review not found"}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"message": "Request body is required"}), 400
    revises = data.get("revises_rating_id")
    if revises is not None and (isinstance(revises, bool) or not isinstance(revises, int)):
        return jsonify({"message": "revises_rating_id must be a whole number"}), 400

    try:
        # Only stars, explanation and the revision pointer are read from the client;
        # the rated officer comes from the review, the rater from the token.
        rating = perf.create_rating(review, chief, data.get("stars"), data.get("explanation"), revises)
        db.session.commit()
    except PerformanceError as error:
        db.session.rollback()
        return _fail(error)
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "This work was rated at the same moment; reload and try again"}), 409
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to save a rating")
        return jsonify({"message": "Could not save the rating"}), 500

    follow_up = ResolutionFollowUp.query.filter_by(resolution_review_id=review_id).first()
    return jsonify({
        "message": "Rating saved",
        "rating": serialize_rating(rating, _effective_ids([review_id])),
        "follow_up": serialize_follow_up(follow_up) if follow_up else None,
    }), 201


@supervision_bp.route("/chief-officer/resolution-reviews/<int:review_id>/ratings", methods=["GET"])
@jwt_required()
def review_ratings(review_id):
    _chief_user, denied = _chief()
    if denied:
        return denied
    if not db.session.get(ResolutionReview, review_id):
        return jsonify({"message": "Resolution review not found"}), 404
    ratings = ResolutionRating.query.filter_by(resolution_review_id=review_id).order_by(ResolutionRating.id.asc()).all()
    effective = _effective_ids([review_id])
    return jsonify({"ratings": [serialize_rating(r, effective) for r in ratings]}), 200


@supervision_bp.route("/chief-officer/ratings", methods=["GET"])
@jwt_required()
def list_ratings():
    _chief_user, denied = _chief()
    if denied:
        return denied
    try:
        officer_id = _int_arg("officer_id")
        stars = _int_arg("stars")
        _limit(), _offset()
        start = perf.parse_day(request.args.get("from"), "from")
        end = perf.parse_day(request.args.get("to"), "to", end_of_day=True)
    except PerformanceError as error:
        return _fail(error)
    query = ResolutionRating.query if request.args.get("history") == "true" else perf.effective_ratings_query()
    if officer_id is not None:
        query = query.filter(ResolutionRating.rated_officer_id == officer_id)
    if stars is not None:
        query = query.filter(ResolutionRating.stars == stars)
    if start:
        query = query.filter(ResolutionRating.created_at >= start)
    if end:
        query = query.filter(ResolutionRating.created_at < end)
    ratings, page = _page(query.order_by(ResolutionRating.created_at.desc(), ResolutionRating.id.desc()))
    effective = _effective_ids([r.resolution_review_id for r in ratings])
    return jsonify({"ratings": [serialize_rating(r, effective) for r in ratings], **page}), 200


# ==========================================
# Follow-ups (Chief Officer)
# ==========================================

@supervision_bp.route("/chief-officer/follow-ups", methods=["GET"])
@jwt_required()
def list_follow_ups():
    _chief_user, denied = _chief()
    if denied:
        return denied
    status = request.args.get("status")
    if status and status not in FOLLOW_UP_STATES:
        return jsonify({"message": "Unknown status", "allowed_statuses": list(FOLLOW_UP_STATES)}), 400
    try:
        assigned = _int_arg("assigned_officer_id")
        rated_officer = _int_arg("rated_officer_id")
        stars = _int_arg("stars")
        _limit(), _offset()
    except PerformanceError as error:
        return _fail(error)
    query = ResolutionFollowUp.query
    if status:
        query = query.filter(ResolutionFollowUp.status == status)
    if assigned is not None:
        query = query.filter(ResolutionFollowUp.assigned_officer_id == assigned)
    if rated_officer is not None:
        query = query.join(ResolutionReview, ResolutionReview.id == ResolutionFollowUp.resolution_review_id).filter(
            ResolutionReview.submitted_by == rated_officer)
    if stars is not None:
        query = query.join(ResolutionRating, ResolutionRating.id == ResolutionFollowUp.rating_id).filter(
            ResolutionRating.stars == stars)
    rows, page = _page(query.order_by(ResolutionFollowUp.updated_at.desc(), ResolutionFollowUp.id.desc()))
    return jsonify({"follow_ups": [serialize_follow_up(f) for f in rows], **page}), 200


@supervision_bp.route("/chief-officer/follow-ups/<int:follow_up_id>", methods=["GET"])
@jwt_required()
def follow_up_detail(follow_up_id):
    _chief_user, denied = _chief()
    if denied:
        return denied
    follow_up = db.session.get(ResolutionFollowUp, follow_up_id)
    if not follow_up:
        return jsonify({"message": "Follow-up not found"}), 404
    return jsonify({"follow_up": serialize_follow_up(follow_up, detail=True)}), 200


@supervision_bp.route("/chief-officer/follow-ups/<int:follow_up_id>/events/<int:event_id>/image", methods=["GET"])
@jwt_required()
def follow_up_event_image(follow_up_id, event_id):
    _chief_user, denied = _chief()
    if denied:
        return denied
    follow_up = db.session.get(ResolutionFollowUp, follow_up_id)
    if not follow_up:
        return jsonify({"message": "Evidence not found"}), 404
    return _serve_correction_image(follow_up, event_id)


def _follow_up_mutation(follow_up_id, action):
    chief, denied = _chief()
    if denied:
        return denied
    follow_up = db.session.get(ResolutionFollowUp, follow_up_id)
    if not follow_up:
        return jsonify({"message": "Follow-up not found"}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"message": "Request body is required"}), 400
    try:
        updated = action(follow_up, chief, data)
        db.session.commit()
    except PerformanceError as error:
        db.session.rollback()
        return _fail(error)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to update a follow-up")
        return jsonify({"message": "Could not update the follow-up"}), 500
    db.session.expire_all()
    updated = db.session.get(ResolutionFollowUp, updated.id)
    return jsonify({"message": "Follow-up updated", "follow_up": serialize_follow_up(updated, detail=True)}), 200


@supervision_bp.route("/chief-officer/follow-ups/<int:follow_up_id>/assign", methods=["PUT"])
@jwt_required()
def assign_follow_up(follow_up_id):
    return _follow_up_mutation(
        follow_up_id,
        lambda f, chief, data: perf.assign_follow_up(f, chief, data.get("officer_id"), data.get("reason")),
    )


@supervision_bp.route("/chief-officer/follow-ups/<int:follow_up_id>/verify", methods=["PUT"])
@jwt_required()
def verify_follow_up(follow_up_id):
    return _follow_up_mutation(
        follow_up_id,
        lambda f, chief, data: perf.verify_follow_up(f, chief, data.get("decision"), data.get("note")),
    )


# ==========================================
# Officer: own ratings and assigned corrections
# ==========================================

@supervision_bp.route("/officers/me/ratings", methods=["GET"])
@jwt_required()
def my_ratings():
    officer, denied = _officer()
    if denied:
        return denied
    try:
        _limit(), _offset()
    except PerformanceError as error:
        return _fail(error)
    ratings, page = _page(ResolutionRating.query.filter_by(rated_officer_id=officer.id).order_by(
        ResolutionRating.created_at.desc(), ResolutionRating.id.desc()))
    effective = _effective_ids([r.resolution_review_id for r in ratings])
    follow_ups = {f.resolution_review_id: f for f in ResolutionFollowUp.query.filter(
        ResolutionFollowUp.resolution_review_id.in_([r.resolution_review_id for r in ratings])).all()} if ratings else {}
    items = []
    for rating in ratings:
        item = serialize_rating(rating, effective, audience="officer")
        follow_up = follow_ups.get(rating.resolution_review_id)
        # Only the correction assigned to *this* officer is linked from here.
        item["follow_up"] = ({"id": follow_up.id, "status": follow_up.status}
                             if follow_up and follow_up.assigned_officer_id == officer.id else None)
        items.append(item)
    return jsonify({"ratings": items, **page}), 200


@supervision_bp.route("/officers/me/follow-ups", methods=["GET"])
@jwt_required()
def my_follow_ups():
    officer, denied = _officer()
    if denied:
        return denied
    try:
        _limit(), _offset()
    except PerformanceError as error:
        return _fail(error)
    query = ResolutionFollowUp.query.filter_by(assigned_officer_id=officer.id)
    status = request.args.get("status")
    if status:
        if status not in FOLLOW_UP_STATES:
            return jsonify({"message": "Unknown status", "allowed_statuses": list(FOLLOW_UP_STATES)}), 400
        query = query.filter(ResolutionFollowUp.status == status)
    # Open corrections first, so one never sinks onto a later page behind newer closed cases.
    rows, page = _page(query.order_by(
        (ResolutionFollowUp.status == "Closed").asc(),
        ResolutionFollowUp.updated_at.desc(), ResolutionFollowUp.id.desc(),
    ))
    return jsonify({"follow_ups": [serialize_follow_up(f, audience="officer", detail=True) for f in rows], **page}), 200


@supervision_bp.route("/officers/me/follow-ups/<int:follow_up_id>", methods=["GET"])
@jwt_required()
def my_follow_up(follow_up_id):
    officer, denied = _officer()
    if denied:
        return denied
    follow_up = ResolutionFollowUp.query.filter_by(id=follow_up_id, assigned_officer_id=officer.id).first()
    if not follow_up:
        return jsonify({"message": "Follow-up not found"}), 404
    data = serialize_follow_up(follow_up, audience="officer", detail=True)
    review = follow_up.review
    # The Officer's own submission, as context for the correction.
    data["work"] = {
        "submitted_at": to_iso8601(review.submitted_at),
        "approved_at": to_iso8601(review.reviewed_at),
        "completion_note": review.completion_note,
        "image_url": f"/uploads/{review.image_filename}",
        "by_this_officer": review.submitted_by == officer.id,
    }
    return jsonify({"follow_up": data}), 200


@supervision_bp.route("/officers/me/follow-ups/<int:follow_up_id>/events/<int:event_id>/image", methods=["GET"])
@jwt_required()
def my_follow_up_event_image(follow_up_id, event_id):
    officer, denied = _officer()
    if denied:
        return denied
    # Same record-level rule as the case itself: only the Officer it is assigned to.
    follow_up = ResolutionFollowUp.query.filter_by(id=follow_up_id, assigned_officer_id=officer.id).first()
    if not follow_up:
        return jsonify({"message": "Evidence not found"}), 404
    return _serve_correction_image(follow_up, event_id)


@supervision_bp.route("/officers/me/follow-ups/<int:follow_up_id>/submit-correction", methods=["POST"])
@jwt_required()
def submit_correction(follow_up_id):
    officer, denied = _officer()
    if denied:
        return denied
    follow_up = ResolutionFollowUp.query.filter_by(id=follow_up_id, assigned_officer_id=officer.id).first()
    if not follow_up:
        return jsonify({"message": "Follow-up not found"}), 404
    if follow_up.status != "Assigned":
        return jsonify({"message": "This follow-up is not awaiting a correction"}), 409

    note = request.form.get("note")
    try:
        note = perf.clean_text(note, "note", perf.MAX_NOTE, required=True)
    except PerformanceError as error:
        return _fail(error)

    image = request.files.get("image")
    saved_path, filename = None, None
    try:
        if image and image.filename:
            original = validate_image_upload(image, current_app.config["MAX_UPLOAD_BYTES"])
            filename = f"{uuid.uuid4().hex}_{original}"
            saved_path = save_upload(image, current_app.config["PRIVATE_UPLOAD_FOLDER"], filename)
        updated = perf.submit_correction(follow_up, officer, note, filename)
        db.session.commit()
    except UploadError as error:
        return jsonify({"message": error.message}), error.status_code
    except PerformanceError as error:
        db.session.rollback()
        _safe_remove(saved_path)
        return _fail(error)
    except Exception:
        db.session.rollback()
        _safe_remove(saved_path)
        current_app.logger.exception("Failed to submit a correction")
        return jsonify({"message": "Could not submit the correction"}), 500

    db.session.expire_all()
    updated = db.session.get(ResolutionFollowUp, updated.id)
    return jsonify({
        "message": "Correction submitted",
        "follow_up": serialize_follow_up(updated, audience="officer", detail=True),
    }), 200
