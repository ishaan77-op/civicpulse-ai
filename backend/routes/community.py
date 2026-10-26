"""
Level 2 community API - /api/community/...

Every identity-bearing value (who is supporting, commenting, verifying) is
derived from the JWT on the server. Request bodies never carry a user id,
score, count, or role, and any such field sent by a client is ignored.
"""

import re
from datetime import timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from database.db import db
from models.civic_issue import CivicIssue
from models.community import (
    COMMENT_PUBLIC_STATUSES,
    ImpactScoreEvent,
    IssueComment,
    IssueSupport,
    IssueVerification,
    VERIFICATION_TYPES,
)
from models.complaint import Complaint
from models.user import User
from services import community_service as community
from services import impact_score_service as impact
from services.community_identity import anonymous_handle, public_author
from utils.time_helper import to_iso8601, utc_now

community_bp = Blueprint("community", __name__)

FEED_SORTS = ["recent", "trending", "nearby", "priority"]

COMMENT_MAX_LENGTH = 1000
COMMENT_MIN_LENGTH = 2
COMMENT_RATE_LIMIT = 5              # comments ...
COMMENT_RATE_WINDOW_MINUTES = 10    # ... per this many minutes, per citizen
COMMENTS_PER_PAGE = 20

MODERATION_STATUSES = ["Flagged", "Removed", "Visible"]
MODERATION_DECISIONS = ["Remove", "Restore"]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LINK_PATTERN = re.compile(r"(https?://|www\.)", re.IGNORECASE)
_REPEATED_CHARS = re.compile(r"(.)\1{9,}")


# ==========================================
# Helpers
# ==========================================

def _current_user():
    return User.query.get(int(get_jwt_identity()))


def _require_citizen(user):
    """Supports and verifications are the *community* signal - they come
    from citizens only, so NMC staff can't inflate or deflate them."""
    if not user:
        return jsonify({"message": "User not found"}), 404
    if user.role != "Citizen":
        return jsonify({"message": "Community support and verification come from citizens only"}), 403
    return None


def _require_staff(user):
    if not user or user.role not in ("Officer", "Admin"):
        return jsonify({"message": "Officer or Admin access required"}), 403
    return None


def _public_issue_or_404(issue_id):
    row = community.get_public_issue(issue_id)
    if not row:
        return None, (jsonify({"message": "Civic issue not found"}), 404)
    return row, None


def _int_arg(name, default, minimum, maximum):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _clean_comment(raw):
    content = _CONTROL_CHARS.sub("", str(raw or "")).strip()
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content


def _automatic_flag_reason(content):
    """Lightweight, deterministic pre-screen. It only ever sends a comment
    to the human review queue - it never hides, deletes or penalizes."""
    if _LINK_PATTERN.search(content):
        return "Contains a link"
    if _REPEATED_CHARS.search(content):
        return "Repeated characters"
    letters = [ch for ch in content if ch.isalpha()]
    if len(letters) >= 30 and sum(ch.isupper() for ch in letters) / len(letters) > 0.8:
        return "Mostly capital letters"
    return None


def _serialize_comment(comment, author, viewer):
    return {
        "id": comment.id,
        "civic_issue_id": comment.civic_issue_id,
        "author": public_author(author, viewer.id if viewer else None),
        "content": comment.content,
        "created_at": to_iso8601(comment.created_at),
        "updated_at": to_iso8601(comment.updated_at),
        "edited": comment.edited,
        "can_edit": bool(viewer and author and viewer.id == author.id),
    }


def _community_snapshot(issue_id, viewer_id):
    supported, verified = community.viewer_state([issue_id], viewer_id)
    return {
        "supporters": community.support_counts([issue_id]).get(issue_id, 0),
        "comments": community.comment_counts([issue_id]).get(issue_id, 0),
        "verification": dict(community.verification_counts([issue_id])[issue_id]),
        "viewer": {
            "supported": issue_id in supported,
            "verification": verified.get(issue_id),
        },
    }


# ==========================================
# FEED
# ==========================================

@community_bp.route("/feed", methods=["GET"])
@jwt_required()
def get_feed():
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    sort = request.args.get("sort", "recent")
    if sort not in FEED_SORTS:
        return jsonify({"message": "Invalid sort", "allowed_sorts": FEED_SORTS}), 400

    page = _int_arg("page", 1, 1, 10000)
    per_page = _int_arg("per_page", community.DEFAULT_PER_PAGE, 1, community.MAX_PER_PAGE)

    latitude = longitude = radius_km = None
    if sort == "nearby":
        try:
            latitude = float(request.args["lat"])
            longitude = float(request.args["lng"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"message": "Nearby needs your location (lat and lng)"}), 400
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({"message": "Location coordinates are invalid"}), 400
        try:
            radius_km = float(request.args.get("radius_km", community.NEARBY_DEFAULT_RADIUS_KM))
        except (TypeError, ValueError):
            radius_km = community.NEARBY_DEFAULT_RADIUS_KM
        radius_km = max(0.2, min(community.NEARBY_MAX_RADIUS_KM, radius_km))

    feed = community.build_feed(
        sort=sort,
        page=page,
        per_page=per_page,
        viewer_id=user.id,
        category=request.args.get("category") or None,
        status=request.args.get("status") or None,
        search=request.args.get("q") or None,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
    )
    return jsonify(feed), 200


# ==========================================
# ISSUE DETAIL
# ==========================================

@community_bp.route("/issues/<int:issue_id>", methods=["GET"])
@jwt_required()
def get_issue(issue_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    row, error = _public_issue_or_404(issue_id)
    if error:
        return error

    issue = row[0]
    card = community.serialize_issue_cards([row], user.id)[0]
    card["evidence"] = community.issue_evidence(issue.id)
    card["timeline"] = community.issue_timeline(issue)
    card["disputed"] = issue.id in community.disputed_issue_ids([issue])
    card["viewer"]["can_engage"] = user.role == "Citizen"
    card["viewer"]["can_comment"] = True

    return jsonify({"issue": card}), 200


# ==========================================
# SUPPORT
# ==========================================

@community_bp.route("/issues/<int:issue_id>/support", methods=["POST"])
@jwt_required()
def support_issue(issue_id):
    user = _current_user()
    denied = _require_citizen(user)
    if denied:
        return denied

    row, error = _public_issue_or_404(issue_id)
    if error:
        return error

    if row[0].status == "Resolved":
        return jsonify({
            "message": "This issue is officially resolved. If it is still present, verify it as still existing instead."
        }), 400

    existing = IssueSupport.query.filter_by(civic_issue_id=issue_id, user_id=user.id).first()
    created = False
    if not existing:
        try:
            db.session.add(IssueSupport(civic_issue_id=issue_id, user_id=user.id))
            impact.on_issue_supported(user.id, issue_id)
            db.session.commit()
            created = True
        except IntegrityError:
            # A concurrent duplicate request lost the race to the unique
            # constraint - the citizen's support is already recorded.
            db.session.rollback()

    return jsonify({
        "message": "Support recorded" if created else "You already support this issue",
        "community": _community_snapshot(issue_id, user.id),
    }), 201 if created else 200


@community_bp.route("/issues/<int:issue_id>/support", methods=["DELETE"])
@jwt_required()
def remove_support(issue_id):
    user = _current_user()
    denied = _require_citizen(user)
    if denied:
        return denied

    row, error = _public_issue_or_404(issue_id)
    if error:
        return error

    # Removing support never re-awards later: the support points are
    # once-ever per (citizen, issue), so toggling can't farm the score.
    IssueSupport.query.filter_by(civic_issue_id=issue_id, user_id=user.id).delete()
    db.session.commit()

    return jsonify({
        "message": "Support removed",
        "community": _community_snapshot(issue_id, user.id),
    }), 200


# ==========================================
# VERIFICATION
# ==========================================

@community_bp.route("/issues/<int:issue_id>/verify", methods=["POST"])
@jwt_required()
def verify_issue(issue_id):
    user = _current_user()
    denied = _require_citizen(user)
    if denied:
        return denied

    row, error = _public_issue_or_404(issue_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    verification_type = str(data.get("verification_type") or "").upper()
    if verification_type not in VERIFICATION_TYPES:
        return jsonify({
            "message": "Invalid verification",
            "allowed_verifications": VERIFICATION_TYPES,
        }), 400

    # One active observation per (issue, citizen). Changing your mind
    # updates it in place - it never adds a second vote.
    verification = IssueVerification.query.filter_by(civic_issue_id=issue_id, user_id=user.id).first()
    status_code = 200
    try:
        if verification:
            verification.verification_type = verification_type
            verification.updated_at = utc_now()
        else:
            db.session.add(IssueVerification(
                civic_issue_id=issue_id, user_id=user.id, verification_type=verification_type
            ))
            status_code = 201
        impact.on_issue_verified(user.id, issue_id, verification_type)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        status_code = 200

    return jsonify({
        "message": "Thanks - your observation was recorded. Official status is unchanged; NMC decides that.",
        "community": _community_snapshot(issue_id, user.id),
    }), status_code


@community_bp.route("/issues/<int:issue_id>/verify", methods=["DELETE"])
@jwt_required()
def withdraw_verification(issue_id):
    user = _current_user()
    denied = _require_citizen(user)
    if denied:
        return denied

    row, error = _public_issue_or_404(issue_id)
    if error:
        return error

    IssueVerification.query.filter_by(civic_issue_id=issue_id, user_id=user.id).delete()
    db.session.commit()

    return jsonify({
        "message": "Observation withdrawn",
        "community": _community_snapshot(issue_id, user.id),
    }), 200


# ==========================================
# COMMENTS
# ==========================================

@community_bp.route("/issues/<int:issue_id>/comments", methods=["GET"])
@jwt_required()
def list_comments(issue_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    row, error = _public_issue_or_404(issue_id)
    if error:
        return error

    page = _int_arg("page", 1, 1, 10000)
    per_page = _int_arg("per_page", COMMENTS_PER_PAGE, 1, 50)

    query = db.session.query(IssueComment, User).join(User, User.id == IssueComment.user_id).filter(
        IssueComment.civic_issue_id == issue_id,
        IssueComment.moderation_status.in_(COMMENT_PUBLIC_STATUSES),
    )
    total = query.count()
    rows = query.order_by(IssueComment.created_at.desc(), IssueComment.id.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return jsonify({
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_more": page * per_page < total,
        "comments": [_serialize_comment(comment, author, user) for comment, author in rows],
    }), 200


@community_bp.route("/issues/<int:issue_id>/comments", methods=["POST"])
@jwt_required()
def create_comment(issue_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    row, error = _public_issue_or_404(issue_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    content = _clean_comment(data.get("content"))

    if len(content) < COMMENT_MIN_LENGTH:
        return jsonify({"message": "Comment cannot be empty"}), 400
    if len(content) > COMMENT_MAX_LENGTH:
        return jsonify({"message": f"Comments are limited to {COMMENT_MAX_LENGTH} characters"}), 400

    now = utc_now()
    recent = IssueComment.query.filter(
        IssueComment.user_id == user.id,
        IssueComment.created_at >= now - timedelta(minutes=COMMENT_RATE_WINDOW_MINUTES),
    ).count()
    if recent >= COMMENT_RATE_LIMIT:
        return jsonify({
            "message": "You're commenting very quickly. Please wait a few minutes and try again."
        }), 429

    duplicate = db.session.query(IssueComment.query.filter(
        IssueComment.user_id == user.id,
        IssueComment.civic_issue_id == issue_id,
        IssueComment.content == content,
        IssueComment.created_at >= now - timedelta(hours=24),
    ).exists()).scalar()
    if duplicate:
        return jsonify({"message": "You already posted this comment on this issue"}), 409

    comment = IssueComment(civic_issue_id=issue_id, user_id=user.id, content=content)

    flag_reason = _automatic_flag_reason(content)
    if flag_reason:
        comment.moderation_status = "Flagged"
        comment.flag_source = "Automatic check"
        comment.flag_reason = flag_reason
        comment.flagged_at = now

    db.session.add(comment)
    db.session.flush()

    if user.role == "Citizen":
        impact.on_comment_created(comment)

    db.session.commit()

    return jsonify({
        "message": "Comment posted",
        "comment": _serialize_comment(comment, user, user),
    }), 201


@community_bp.route("/comments/<int:comment_id>", methods=["PUT"])
@jwt_required()
def edit_comment(comment_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    comment = IssueComment.query.get(comment_id)
    # Someone else's comment is reported as not found, not forbidden, so
    # the endpoint can't be used to probe ownership.
    if not comment or comment.user_id != user.id or comment.moderation_status not in COMMENT_PUBLIC_STATUSES:
        return jsonify({"message": "Comment not found"}), 404

    data = request.get_json(silent=True) or {}
    content = _clean_comment(data.get("content"))

    if len(content) < COMMENT_MIN_LENGTH:
        return jsonify({"message": "Comment cannot be empty"}), 400
    if len(content) > COMMENT_MAX_LENGTH:
        return jsonify({"message": f"Comments are limited to {COMMENT_MAX_LENGTH} characters"}), 400

    comment.content = content
    comment.edited = True
    flag_reason = _automatic_flag_reason(content)
    if flag_reason and comment.moderation_status == "Visible":
        comment.moderation_status = "Flagged"
        comment.flag_source = "Automatic check"
        comment.flag_reason = flag_reason
        comment.flagged_at = utc_now()
    db.session.commit()

    return jsonify({"message": "Comment updated", "comment": _serialize_comment(comment, user, user)}), 200


@community_bp.route("/comments/<int:comment_id>", methods=["DELETE"])
@jwt_required()
def delete_comment(comment_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    comment = IssueComment.query.get(comment_id)
    if not comment or comment.user_id != user.id or comment.moderation_status not in COMMENT_PUBLIC_STATUSES:
        return jsonify({"message": "Comment not found"}), 404

    # Soft delete: hidden everywhere, kept for moderation audit.
    comment.moderation_status = "Deleted"
    db.session.commit()

    return jsonify({"message": "Comment deleted"}), 200


@community_bp.route("/comments/<int:comment_id>/report", methods=["POST"])
@jwt_required()
def report_comment(comment_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    comment = IssueComment.query.get(comment_id)
    if not comment or comment.moderation_status not in COMMENT_PUBLIC_STATUSES:
        return jsonify({"message": "Comment not found"}), 404

    if comment.user_id == user.id:
        return jsonify({"message": "You can edit or delete your own comment instead"}), 400

    data = request.get_json(silent=True) or {}
    reason = _clean_comment(data.get("reason"))[:300] or "Reported by a citizen"

    # Reporting only queues the comment for a human decision. It stays
    # visible, and reporting it again changes nothing.
    if comment.moderation_status == "Visible":
        comment.moderation_status = "Flagged"
        comment.flag_source = "Citizen report"
        comment.flag_reason = reason
        comment.flagged_at = utc_now()
        db.session.commit()

    return jsonify({"message": "Thanks - a moderator will review this comment"}), 200


# ==========================================
# MY IMPACT (private to the signed-in citizen)
# ==========================================

@community_bp.route("/me/impact", methods=["GET"])
@jwt_required()
def my_impact():
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    eligible = community.eligible_complaint_filter()

    issues_reported = db.session.query(func.count(func.distinct(Complaint.issue_id))).filter(
        Complaint.user_id == user.id, Complaint.issue_id.isnot(None), eligible
    ).scalar() or 0

    resolved_issues = db.session.query(func.count(func.distinct(Complaint.issue_id))).join(
        CivicIssue, CivicIssue.id == Complaint.issue_id
    ).filter(
        Complaint.user_id == user.id, eligible, CivicIssue.status == "Resolved"
    ).scalar() or 0

    return jsonify({
        "handle": anonymous_handle(user.id),
        "impact_score": impact.get_impact_score(user.id),
        "stats": {
            "issues_reported": issues_reported,
            "issues_supported": IssueSupport.query.filter_by(user_id=user.id).count(),
            "verifications": IssueVerification.query.filter_by(user_id=user.id).count(),
            "comments": IssueComment.query.filter(
                IssueComment.user_id == user.id,
                IssueComment.moderation_status.in_(COMMENT_PUBLIC_STATUSES),
            ).count(),
            "resolved_issues": resolved_issues,
        },
        "breakdown": impact.get_score_breakdown(user.id),
        "rules": impact.public_rules(),
    }), 200


@community_bp.route("/me/activity", methods=["GET"])
@jwt_required()
def my_activity():
    user = _current_user()
    if not user:
        return jsonify({"message": "User not found"}), 404

    limit = _int_arg("limit", 20, 1, 50)
    events = impact.get_recent_events(user.id, limit)

    return jsonify({
        "events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "label": impact.EVENT_LABELS.get(event.event_type, event.event_type),
                "points": event.points,
                "civic_issue_id": event.civic_issue_id,
                "created_at": to_iso8601(event.created_at),
            }
            for event in events
        ]
    }), 200


# ==========================================
# COMMENT MODERATION - OFFICER/ADMIN
# ==========================================

@community_bp.route("/moderation/comments", methods=["GET"])
@jwt_required()
def moderation_queue():
    user = _current_user()
    denied = _require_staff(user)
    if denied:
        return denied

    status = request.args.get("status", "Flagged")
    if status not in MODERATION_STATUSES:
        return jsonify({"message": "Invalid status", "allowed_statuses": MODERATION_STATUSES}), 400

    page = _int_arg("page", 1, 1, 10000)
    per_page = _int_arg("per_page", 25, 1, 100)

    query = db.session.query(IssueComment, User).join(User, User.id == IssueComment.user_id).filter(
        IssueComment.moderation_status == status
    )
    total = query.count()
    rows = query.order_by(
        func.coalesce(IssueComment.flagged_at, IssueComment.created_at).desc()
    ).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "total": total,
        "page": page,
        "has_more": page * per_page < total,
        "comments": [
            {
                **_serialize_comment(comment, author, None),
                # Staff-only audit context. Staff already see reporter ids
                # on complaints in Level 1; name/email are still withheld.
                "author_user_id": author.id,
                "moderation": {
                    "status": comment.moderation_status,
                    "flag_source": comment.flag_source,
                    "flag_reason": comment.flag_reason,
                    "flagged_at": to_iso8601(comment.flagged_at),
                    "moderated_by": comment.moderated_by,
                    "moderated_at": to_iso8601(comment.moderated_at),
                    "moderation_reason": comment.moderation_reason,
                },
            }
            for comment, author in rows
        ],
    }), 200


@community_bp.route("/moderation/comments/<int:comment_id>", methods=["PUT"])
@jwt_required()
def moderate_comment(comment_id):
    user = _current_user()
    denied = _require_staff(user)
    if denied:
        return denied

    comment = IssueComment.query.get(comment_id)
    if not comment or comment.moderation_status == "Deleted":
        return jsonify({"message": "Comment not found"}), 404

    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    reason = _clean_comment(data.get("reason"))[:500]

    if decision not in MODERATION_DECISIONS:
        return jsonify({"message": "Invalid decision", "allowed_decisions": MODERATION_DECISIONS}), 400

    if decision == "Remove":
        if comment.moderation_status == "Removed":
            return jsonify({"message": "This comment has already been removed"}), 400
        if not reason:
            return jsonify({"message": "A reason is required to remove a comment"}), 400
        comment.moderation_status = "Removed"
        impact.on_comment_removed(comment, user.id)
    else:
        if comment.moderation_status == "Visible":
            return jsonify({"message": "This comment is not under review"}), 400
        comment.moderation_status = "Visible"

    # The flag fields are left in place as audit history.
    comment.moderated_by = user.id
    comment.moderated_at = utc_now()
    comment.moderation_reason = reason or None
    db.session.commit()

    return jsonify({"message": f"Comment {'removed' if decision == 'Remove' else 'restored'}"}), 200


# ==========================================
# OFFICER COMMUNITY INTELLIGENCE
# ==========================================

@community_bp.route("/issues/<int:issue_id>/intelligence", methods=["GET"])
@jwt_required()
def issue_intelligence(issue_id):
    user = _current_user()
    denied = _require_staff(user)
    if denied:
        return denied

    issue = CivicIssue.query.get(issue_id)
    if not issue:
        return jsonify({"message": "Civic issue not found"}), 404

    recent_comments = db.session.query(IssueComment, User).join(User, User.id == IssueComment.user_id).filter(
        IssueComment.civic_issue_id == issue_id,
        IssueComment.moderation_status.in_(COMMENT_PUBLIC_STATUSES),
    ).order_by(IssueComment.created_at.desc()).limit(5).all()

    return jsonify({
        "issue_id": issue.id,
        "is_public": community.is_public_issue(issue.id),
        "disputed": issue.id in community.disputed_issue_ids([issue]),
        "community": _community_snapshot(issue.id, None),
        "recent_comments": [_serialize_comment(c, author, None) for c, author in recent_comments],
        "evidence": community.issue_evidence(issue.id),
    }), 200


# ==========================================
# ADMIN COMMUNITY ANALYTICS
# ==========================================

@community_bp.route("/analytics", methods=["GET"])
@jwt_required()
def community_analytics():
    user = _current_user()
    if not user or user.role != "Admin":
        return jsonify({"message": "Admin access required"}), 403

    public_query, _ = community.public_issue_query()
    public_rows = public_query.all()
    public_issues = [row[0] for row in public_rows]
    public_ids = [issue.id for issue in public_issues]

    since = utc_now() - timedelta(days=7)

    participants = set()
    for model in (IssueSupport, IssueVerification, IssueComment):
        participants.update(row[0] for row in db.session.query(func.distinct(model.user_id)).all())

    citizen_scores = db.session.query(
        ImpactScoreEvent.user_id, func.sum(ImpactScoreEvent.points)
    ).join(User, User.id == ImpactScoreEvent.user_id).filter(
        User.role == "Citizen"
    ).group_by(ImpactScoreEvent.user_id).all()
    average_score = round(sum(score for _, score in citizen_scores) / len(citizen_scores), 1) if citizen_scores else 0.0

    verifications = community.verification_counts(public_ids)
    confirmed_unresolved = sum(
        1 for issue in public_issues
        if issue.status != "Resolved"
        and verifications[issue.id]["still_exists"] >= community.DISPUTE_MIN_STILL_EXISTS
    )

    supports = community.support_counts(public_ids)
    comments = community.comment_counts(public_ids)
    by_category = {}
    for issue in public_issues:
        entry = by_category.setdefault(issue.category, {"issues": 0, "supports": 0, "verifications": 0, "comments": 0})
        entry["issues"] += 1
        entry["supports"] += supports.get(issue.id, 0)
        entry["verifications"] += sum(verifications[issue.id].values())
        entry["comments"] += comments.get(issue.id, 0)

    return jsonify({
        "summary": {
            "public_civic_issues": len(public_issues),
            "active_civic_issues": sum(1 for issue in public_issues if issue.status != "Resolved"),
            "resolved_civic_issues": sum(1 for issue in public_issues if issue.status == "Resolved"),
            "total_supports": IssueSupport.query.count(),
            "total_verifications": IssueVerification.query.count(),
            "verifications_last_7_days": IssueVerification.query.filter(IssueVerification.updated_at >= since).count(),
            "total_comments": IssueComment.query.filter(
                IssueComment.moderation_status.in_(COMMENT_PUBLIC_STATUSES)
            ).count(),
            "comments_awaiting_review": IssueComment.query.filter_by(moderation_status="Flagged").count(),
            "community_participants": len(participants),
            "average_impact_score": average_score,
            "citizens_with_impact": len(citizen_scores),
            "community_confirmed_unresolved": confirmed_unresolved,
            "disputed_resolutions": len(community.disputed_issue_ids(public_issues)),
        },
        "engagement_by_category": by_category,
        "definitions": {
            "community_confirmed_unresolved": (
                f"Not officially resolved, and at least {community.DISPUTE_MIN_STILL_EXISTS} citizens "
                f"currently report the issue still present."
            ),
            "disputed_resolutions": (
                f"Officially resolved, but since resolution at least {community.DISPUTE_MIN_STILL_EXISTS} "
                f"citizens (and more than those saying resolved) report it still present."
            ),
            "average_impact_score": "Mean Community Impact Score across citizens with at least one scored event.",
        },
    }), 200
