from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.db import db
from models.notification import Notification
from utils.time_helper import to_iso8601

notification_bp = Blueprint("notification", __name__)


def serialize_notification(notification):
    return {
        "id": notification.id,
        "complaint_id": notification.complaint_id,
        "message": notification.message,
        "spam_count_at_time": notification.spam_count_at_time,
        "is_read": notification.is_read,
        "created_at": to_iso8601(notification.created_at),
    }


# ==========================================
# GET MY NOTIFICATIONS
# ==========================================

@notification_bp.route("/", methods=["GET"])
@jwt_required()
def get_notifications():
    user_id = get_jwt_identity()

    query = Notification.query.filter_by(user_id=int(user_id))

    if request.args.get("unread_only") == "true":
        query = query.filter_by(is_read=False)

    notifications = query.order_by(Notification.created_at.desc()).all()

    return jsonify({
        "notifications": [serialize_notification(n) for n in notifications]
    }), 200


# ==========================================
# MARK NOTIFICATION AS READ
# ==========================================

@notification_bp.route("/<int:notification_id>/read", methods=["PUT"])
@jwt_required()
def mark_notification_read(notification_id):
    user_id = get_jwt_identity()

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=int(user_id)
    ).first()

    if not notification:
        return jsonify({"message": "Notification not found"}), 404

    notification.is_read = True
    db.session.commit()

    return jsonify({
        "message": "Notification marked as read",
        "notification": serialize_notification(notification)
    }), 200
