from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import db
from models.civic_issue import CivicIssue
from models.complaint import Complaint
from models.notification import Notification
from models.user import User
from routes.complaints import serialize_complaint
from utils.time_helper import to_iso8601, utc_now

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
    # Historical/rejected view: pass rejection_status=Rejected to see the
    # out-of-scope queue instead of the default active queue.
    rejection_status = request.args.get("rejection_status")

    # Confirmed spam is moderation history, not an active work item - kept
    # out of the officer/admin work queue while the row itself (and its
    # spam audit trail) is preserved. Same treatment for a complaint
    # rejected as out-of-scope (a separate, non-spam moderation outcome).
    query = Complaint.query.filter(Complaint.spam_review_status != "Confirmed")

    if rejection_status == "Rejected":
        query = query.filter(Complaint.rejection_status == "Rejected")
    else:
        query = query.filter(Complaint.rejection_status != "Rejected")

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


PRIORITY_WEIGHTS = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1,
}


@officer_bp.route("/heatmap", methods=["GET"])
@jwt_required()
def get_heatmap_data():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    status = request.args.get("status")
    category = request.args.get("category")

    query = Complaint.query.filter(
        Complaint.latitude.isnot(None),
        Complaint.longitude.isnot(None),
        Complaint.spam_review_status != "Confirmed",
        Complaint.rejection_status != "Rejected",
    )

    if status:
        query = query.filter(Complaint.status == status)
    if category:
        query = query.filter(Complaint.category == category)

    complaints = query.all()

    points = [
        {
            "latitude": c.latitude,
            "longitude": c.longitude,
            "weight": PRIORITY_WEIGHTS.get(c.ai_priority, 1),
            "status": c.status,
            "category": c.category,
            "priority": c.ai_priority,
        }
        for c in complaints
    ]

    return jsonify({"points": points}), 200


@officer_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_officer_stats():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    active = Complaint.query.filter(
        Complaint.spam_review_status != "Confirmed",
        Complaint.rejection_status != "Rejected",
    )

    total = active.count()
    pending = active.filter(Complaint.status == "Pending").count()
    in_progress = active.filter(Complaint.status == "In Progress").count()
    resolved = active.filter(Complaint.status == "Resolved").count()

    return jsonify({
        "total_complaints": total,
        "pending": pending,
        "in_progress": in_progress,
        "resolved": resolved
    }), 200


# ==========================================
# SPAM / MISREPORT MODERATION - OFFICER/ADMIN ONLY
# ==========================================

SPAM_SUSPENSION_THRESHOLD = 5

ALLOWED_SPAM_REVIEW_STATUSES = ["NotFlagged", "Pending", "Confirmed", "Rejected"]
ALLOWED_SPAM_DECISIONS = ["Confirmed", "Rejected"]


@officer_bp.route("/spam", methods=["GET"])
@jwt_required()
def get_spam_reports():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    status = request.args.get("status", "Pending")

    if status not in ALLOWED_SPAM_REVIEW_STATUSES:
        return jsonify({
            "message": "Invalid status",
            "allowed_statuses": ALLOWED_SPAM_REVIEW_STATUSES
        }), 400

    complaints = Complaint.query.filter(
        Complaint.spam_review_status == status
    ).order_by(Complaint.created_at.desc()).all()

    return jsonify({
        "total": len(complaints),
        "complaints": [
            serialize_complaint(c, include_spam=True) for c in complaints
        ]
    }), 200


@officer_bp.route("/spam/<int:complaint_id>/review", methods=["PUT"])
@jwt_required()
def review_spam_report(complaint_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"message": "Complaint not found"}), 404

    data = request.get_json()
    decision = data.get("decision") if data else None

    if decision not in ALLOWED_SPAM_DECISIONS:
        return jsonify({
            "message": "Invalid decision",
            "allowed_decisions": ALLOWED_SPAM_DECISIONS
        }), 400

    if complaint.spam_review_status != "Pending":
        return jsonify({
            "message": f"This complaint has already been reviewed (status: {complaint.spam_review_status})"
        }), 400

    complaint.spam_review_status = decision
    complaint.spam_reviewed_by = user.id
    complaint.spam_reviewed_at = utc_now()

    # Only a CONFIRMED decision ever increments the reported user's spam
    # count. A Rejected decision still reports the user's current standing
    # back to the reviewer, but never mutates it.
    reported_user = User.query.get(complaint.user_id)

    if decision == "Confirmed" and reported_user:
        reported_user.spam_count += 1
        if reported_user.spam_count >= SPAM_SUSPENSION_THRESHOLD:
            reported_user.is_suspended = True

        # A confirmed-spam report was never real corroborating evidence for
        # its civic issue - stop counting it, but keep the complaint's own
        # link intact (nothing about the complaint or the issue is deleted).
        if complaint.issue and complaint.issue.report_count > 0:
            complaint.issue.report_count -= 1

        remaining = max(0, SPAM_SUSPENSION_THRESHOLD - reported_user.spam_count)

        if reported_user.is_suspended:
            message = (
                f'🚩 Complaint Declined & Flagged — Your complaint "{complaint.title}" was '
                f"reviewed and confirmed as a misreport/spam. Confirmed spam incidents: "
                f"{reported_user.spam_count}/{SPAM_SUSPENSION_THRESHOLD}. Your account has been "
                f"suspended according to system rules."
            )
        else:
            message = (
                f'🚩 Complaint Declined & Flagged — Your complaint "{complaint.title}" was '
                f"reviewed and determined to be a misreport/spam. Confirmed spam incidents: "
                f"{reported_user.spam_count}/{SPAM_SUSPENSION_THRESHOLD}. Remaining incidents "
                f"before suspension: {remaining}. Please ensure future complaints contain "
                f"accurate information and relevant evidence."
            )

        db.session.add(Notification(
            user_id=reported_user.id,
            complaint_id=complaint.id,
            message=message,
            spam_count_at_time=reported_user.spam_count
        ))

    db.session.commit()

    return jsonify({
        "message": f"Report marked as {decision}",
        "complaint": serialize_complaint(complaint, include_spam=True),
        "reported_user": {
            "id": reported_user.id,
            "spam_count": reported_user.spam_count,
            "is_suspended": reported_user.is_suspended
        } if reported_user else None
    }), 200


@officer_bp.route("/spam/<int:complaint_id>/reopen", methods=["PUT"])
@jwt_required()
def reopen_spam_review(complaint_id):
    """Corrects a mistaken human decision (either direction) by sending an
    already-reviewed report back to Pending review, so another authorized
    reviewer can decide again. Never touches a report that hasn't been
    decided yet - AI flagging alone was never a decision to undo."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    complaint = Complaint.query.get(complaint_id)
    if not complaint:
        return jsonify({"message": "Complaint not found"}), 404

    if complaint.spam_review_status not in ("Confirmed", "Rejected"):
        return jsonify({
            "message": f"Only a reviewed report can be reopened (status: {complaint.spam_review_status})"
        }), 400

    was_confirmed = complaint.spam_review_status == "Confirmed"
    reported_user = User.query.get(complaint.user_id) if was_confirmed else None

    if was_confirmed and reported_user:
        # Reverse only the effects that came from THIS complaint's
        # confirmation - never any other confirmed report against the same
        # citizen, and never the AI analysis/flag/reason, which stays as
        # the original evidence regardless of the human decision.
        if reported_user.spam_count > 0:
            reported_user.spam_count -= 1
        reported_user.is_suspended = reported_user.spam_count >= SPAM_SUSPENSION_THRESHOLD

        if complaint.issue:
            complaint.issue.report_count += 1

    complaint.spam_review_status = "Pending"
    complaint.spam_reopened_by = user.id
    complaint.spam_reopened_at = utc_now()

    db.session.commit()

    return jsonify({
        "message": "Report reopened for review",
        "complaint": serialize_complaint(complaint, include_spam=True),
        "reported_user": {
            "id": reported_user.id,
            "spam_count": reported_user.spam_count,
            "is_suspended": reported_user.is_suspended
        } if reported_user else None
    }), 200


# ==========================================
# ISSUE CLUSTERS - OFFICER/ADMIN ONLY
# ==========================================

ALLOWED_ISSUE_STATUSES = ["Pending", "In Progress", "Resolved"]


def serialize_issue(issue):
    return {
        "id": issue.id,
        "category": issue.category,
        "location_label": issue.location_label,
        "latitude": issue.latitude,
        "longitude": issue.longitude,
        "status": issue.status,
        "report_count": issue.report_count,
        "ai_summary": issue.ai_summary,
        "created_at": to_iso8601(issue.created_at),
        "updated_at": to_iso8601(issue.updated_at),
    }


@officer_bp.route("/issues", methods=["GET"])
@jwt_required()
def get_issues():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    status = request.args.get("status")
    category = request.args.get("category")
    sort = request.args.get("sort", "report_count")

    query = CivicIssue.query

    if status:
        query = query.filter(CivicIssue.status == status)
    if category:
        query = query.filter(CivicIssue.category == category)

    if sort == "recent":
        query = query.order_by(CivicIssue.created_at.desc())
    else:
        query = query.order_by(CivicIssue.report_count.desc())

    issues = query.all()

    return jsonify({
        "total": len(issues),
        "issues": [serialize_issue(i) for i in issues]
    }), 200


@officer_bp.route("/issues/<int:issue_id>/complaints", methods=["GET"])
@jwt_required()
def get_issue_complaints(issue_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    issue = CivicIssue.query.get(issue_id)
    if not issue:
        return jsonify({"message": "Issue not found"}), 404

    complaints = Complaint.query.filter_by(issue_id=issue_id).order_by(
        Complaint.created_at.desc()
    ).all()

    return jsonify({
        "issue": serialize_issue(issue),
        "complaints": [serialize_complaint(c) for c in complaints]
    }), 200


@officer_bp.route("/issues/<int:issue_id>/status", methods=["PUT"])
@jwt_required()
def update_issue_status(issue_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if not user or user.role not in ["Officer", "Admin"]:
        return jsonify({"message": "Officer or Admin access required"}), 403

    issue = CivicIssue.query.get(issue_id)
    if not issue:
        return jsonify({"message": "Issue not found"}), 404

    data = request.get_json()
    if not data or not data.get("status"):
        return jsonify({"message": "Status is required"}), 400

    new_status = data.get("status")

    if new_status not in ALLOWED_ISSUE_STATUSES:
        return jsonify({
            "message": "Invalid status",
            "allowed_statuses": ALLOWED_ISSUE_STATUSES
        }), 400

    # Deliberately does NOT cascade-write every member complaint's own
    # status - the issue is the operational work item, but each citizen's
    # individual complaint history/status is preserved as-is. Citizens see
    # this issue's status via their complaint's `civic_issue` field
    # instead.
    issue.status = new_status
    db.session.commit()

    return jsonify({
        "message": "Issue status updated successfully",
        "issue": serialize_issue(issue)
    }), 200
