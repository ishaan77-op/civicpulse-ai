"""
Community Impact Score - a civic reputation metric, not a popularity score.

Single source of truth for every scoring rule. Nothing outside this module
(and certainly nothing in the frontend) decides point values: routes call
the `on_*` hooks below after an action has already been validated and
authorized server-side, and the score is always derived as SUM(points) over
the append-only ImpactScoreEvent ledger.

Anti-farming rules enforced here:
  - support / verification points: once ever per (citizen, issue), backed by
    a unique `dedupe_key` in the database;
  - complaint / evidence / comment points: at most one live award per
    (citizen, issue), so duplicate complaints or comment floods earn nothing;
  - daily caps on the low-value engagement events;
  - negative points only from a confirmed, auditable human decision (a
    Confirmed spam review or a moderator removing a comment) - never from an
    AI flag alone;
  - corrections (e.g. a spam decision reopened) are compensating rows, so
    the full history stays auditable.

The weights are starting values - adjust them here, and only here.
"""

import json

from sqlalchemy import func

from database.db import db
from models.community import ImpactScoreEvent
from models.complaint import Complaint
from utils.time_helper import utc_now

# ==========================================
# Configuration
# ==========================================

WEIGHTS = {
    "VALID_COMPLAINT": 5,
    "USEFUL_EVIDENCE": 3,
    "ISSUE_SUPPORT": 1,
    "ISSUE_VERIFICATION": 2,
    "CONSTRUCTIVE_COMMENT": 1,
    "ISSUE_RESOLVED": 10,
    "CONFIRMED_SPAM": -10,
}

# Compensating event types. Their points are always derived from what is
# being reversed, never configured independently.
VALID_COMPLAINT_REVOKED = "VALID_COMPLAINT_REVOKED"
USEFUL_EVIDENCE_REVOKED = "USEFUL_EVIDENCE_REVOKED"
CONFIRMED_SPAM_REVERSED = "CONFIRMED_SPAM_REVERSED"
COMMENT_REMOVED = "COMMENT_REMOVED"

# Max number of *scored* events of a type per citizen per UTC day. The
# action itself still succeeds past the cap - it just stops earning points.
DAILY_CAPS = {
    "ISSUE_SUPPORT": 20,
    "ISSUE_VERIFICATION": 10,
    "CONSTRUCTIVE_COMMENT": 5,
}

# A comment has to say something to count as a contribution.
MIN_CONSTRUCTIVE_COMMENT_LENGTH = 20

EVENT_LABELS = {
    "VALID_COMPLAINT": "Valid complaint reported",
    "USEFUL_EVIDENCE": "Corroborating evidence added to an existing issue",
    "ISSUE_SUPPORT": "Supported a civic issue",
    "ISSUE_VERIFICATION": "Verified an issue on the ground",
    "CONSTRUCTIVE_COMMENT": "Constructive comment",
    "ISSUE_RESOLVED": "Reported an issue that NMC resolved",
    "CONFIRMED_SPAM": "Report confirmed as spam by a reviewer",
    VALID_COMPLAINT_REVOKED: "Complaint points withdrawn after spam review",
    USEFUL_EVIDENCE_REVOKED: "Evidence points withdrawn after spam review",
    CONFIRMED_SPAM_REVERSED: "Spam decision reversed on re-review",
    COMMENT_REMOVED: "Comment removed by a moderator",
}

# Complaint moderation states that count as a genuine civic report.
ELIGIBLE_SPAM_STATES = ("NotFlagged", "Rejected")


# ==========================================
# Internals
# ==========================================

def _record(user_id, event_type, points, civic_issue_id=None, complaint_id=None,
            comment_id=None, dedupe_key=None, metadata=None):
    event = ImpactScoreEvent(
        user_id=user_id,
        event_type=event_type,
        points=points,
        civic_issue_id=civic_issue_id,
        complaint_id=complaint_id,
        comment_id=comment_id,
        dedupe_key=dedupe_key,
        event_metadata=json.dumps(metadata) if metadata else None,
    )
    db.session.add(event)
    return event


def _net_points(user_id, event_types, **filters):
    query = db.session.query(func.coalesce(func.sum(ImpactScoreEvent.points), 0)).filter(
        ImpactScoreEvent.user_id == user_id,
        ImpactScoreEvent.event_type.in_(event_types),
    )
    for column, value in filters.items():
        query = query.filter(getattr(ImpactScoreEvent, column) == value)
    return int(query.scalar() or 0)


def _dedupe_exists(dedupe_key):
    return db.session.query(
        ImpactScoreEvent.query.filter_by(dedupe_key=dedupe_key).exists()
    ).scalar()


def _daily_cap_reached(user_id, event_type):
    cap = DAILY_CAPS.get(event_type)
    if cap is None:
        return False
    day_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    count = ImpactScoreEvent.query.filter(
        ImpactScoreEvent.user_id == user_id,
        ImpactScoreEvent.event_type == event_type,
        ImpactScoreEvent.created_at >= day_start,
    ).count()
    return count >= cap


def _is_eligible(complaint):
    return (
        complaint.spam_review_status in ELIGIBLE_SPAM_STATES
        and complaint.rejection_status != "Rejected"
    )


# ==========================================
# Hooks - call AFTER the action is validated/authorized. None of them
# commit; the caller commits alongside its own change.
# ==========================================

def on_complaint_validated(complaint):
    """A complaint counts as a genuine report: either created without an AI
    spam flag, or a human reviewer rejected the AI's spam flag. Awards at
    most one live VALID_COMPLAINT per (citizen, issue) - filing duplicates
    of the same issue earns nothing extra - plus USEFUL_EVIDENCE when the
    report corroborates an issue another citizen already reported."""
    if not complaint.issue_id or not _is_eligible(complaint):
        return

    user_id = complaint.user_id
    issue_id = complaint.issue_id

    if _net_points(user_id, ["VALID_COMPLAINT", VALID_COMPLAINT_REVOKED], civic_issue_id=issue_id) <= 0:
        _record(user_id, "VALID_COMPLAINT", WEIGHTS["VALID_COMPLAINT"],
                civic_issue_id=issue_id, complaint_id=complaint.id)

    corroborates_someone_else = db.session.query(
        Complaint.query.filter(
            Complaint.issue_id == issue_id,
            Complaint.user_id != user_id,
            Complaint.id != complaint.id,
            Complaint.created_at <= (complaint.created_at or utc_now()),
            Complaint.spam_review_status.in_(ELIGIBLE_SPAM_STATES),
            Complaint.rejection_status != "Rejected",
        ).exists()
    ).scalar()

    if corroborates_someone_else and _net_points(
        user_id, ["USEFUL_EVIDENCE", USEFUL_EVIDENCE_REVOKED], civic_issue_id=issue_id
    ) <= 0:
        _record(user_id, "USEFUL_EVIDENCE", WEIGHTS["USEFUL_EVIDENCE"],
                civic_issue_id=issue_id, complaint_id=complaint.id)


def on_spam_confirmed(complaint, reviewer_id):
    """Only ever called for a human Confirmed spam decision."""
    user_id = complaint.user_id

    if _net_points(user_id, ["CONFIRMED_SPAM", CONFIRMED_SPAM_REVERSED], complaint_id=complaint.id) == 0:
        _record(user_id, "CONFIRMED_SPAM", WEIGHTS["CONFIRMED_SPAM"],
                civic_issue_id=complaint.issue_id, complaint_id=complaint.id,
                metadata={"reviewed_by": reviewer_id})

    # Withdraw anything this specific complaint earned while it was
    # considered genuine (e.g. a decision that was reopened and flipped).
    for award, revoke in (("VALID_COMPLAINT", VALID_COMPLAINT_REVOKED),
                          ("USEFUL_EVIDENCE", USEFUL_EVIDENCE_REVOKED)):
        earned = _net_points(user_id, [award, revoke], complaint_id=complaint.id)
        if earned > 0:
            _record(user_id, revoke, -earned, civic_issue_id=complaint.issue_id,
                    complaint_id=complaint.id, metadata={"reviewed_by": reviewer_id})


def on_spam_decision_reopened(complaint, was_confirmed, reviewer_id):
    if not was_confirmed:
        return
    penalty = _net_points(complaint.user_id, ["CONFIRMED_SPAM", CONFIRMED_SPAM_REVERSED],
                          complaint_id=complaint.id)
    if penalty < 0:
        _record(complaint.user_id, CONFIRMED_SPAM_REVERSED, -penalty,
                civic_issue_id=complaint.issue_id, complaint_id=complaint.id,
                metadata={"reopened_by": reviewer_id})


def on_issue_supported(user_id, issue_id):
    key = f"support:{issue_id}:{user_id}"
    if _dedupe_exists(key) or _daily_cap_reached(user_id, "ISSUE_SUPPORT"):
        return
    _record(user_id, "ISSUE_SUPPORT", WEIGHTS["ISSUE_SUPPORT"],
            civic_issue_id=issue_id, dedupe_key=key)


def on_issue_verified(user_id, issue_id, verification_type):
    key = f"verify:{issue_id}:{user_id}"
    if _dedupe_exists(key) or _daily_cap_reached(user_id, "ISSUE_VERIFICATION"):
        return
    _record(user_id, "ISSUE_VERIFICATION", WEIGHTS["ISSUE_VERIFICATION"],
            civic_issue_id=issue_id, dedupe_key=key,
            metadata={"verification_type": verification_type})


def on_comment_created(comment):
    if len(comment.content) < MIN_CONSTRUCTIVE_COMMENT_LENGTH:
        return
    if comment.moderation_status != "Visible":
        return
    if _net_points(comment.user_id, ["CONSTRUCTIVE_COMMENT", COMMENT_REMOVED],
                   civic_issue_id=comment.civic_issue_id) > 0:
        return
    if _daily_cap_reached(comment.user_id, "CONSTRUCTIVE_COMMENT"):
        return
    _record(comment.user_id, "CONSTRUCTIVE_COMMENT", WEIGHTS["CONSTRUCTIVE_COMMENT"],
            civic_issue_id=comment.civic_issue_id, comment_id=comment.id)


def on_comment_removed(comment, moderator_id):
    earned = _net_points(comment.user_id, ["CONSTRUCTIVE_COMMENT", COMMENT_REMOVED],
                         comment_id=comment.id)
    if earned > 0:
        _record(comment.user_id, COMMENT_REMOVED, -earned,
                civic_issue_id=comment.civic_issue_id, comment_id=comment.id,
                metadata={"moderated_by": moderator_id})


def on_issue_resolved(issue):
    """Rewards every citizen whose genuine report is part of an issue that
    NMC officially resolved - once per (citizen, issue), even if the issue
    is later reopened and resolved again."""
    reporter_rows = db.session.query(Complaint.user_id, func.min(Complaint.id)).filter(
        Complaint.issue_id == issue.id,
        Complaint.spam_review_status.in_(ELIGIBLE_SPAM_STATES),
        Complaint.rejection_status != "Rejected",
    ).group_by(Complaint.user_id).all()

    for user_id, complaint_id in reporter_rows:
        key = f"resolved:{issue.id}:{user_id}"
        if _dedupe_exists(key):
            continue
        _record(user_id, "ISSUE_RESOLVED", WEIGHTS["ISSUE_RESOLVED"],
                civic_issue_id=issue.id, complaint_id=complaint_id, dedupe_key=key)


# ==========================================
# Reads
# ==========================================

def get_impact_score(user_id):
    return int(db.session.query(func.coalesce(func.sum(ImpactScoreEvent.points), 0)).filter(
        ImpactScoreEvent.user_id == user_id
    ).scalar() or 0)


def get_score_breakdown(user_id):
    rows = db.session.query(
        ImpactScoreEvent.event_type,
        func.count(ImpactScoreEvent.id),
        func.sum(ImpactScoreEvent.points),
    ).filter(ImpactScoreEvent.user_id == user_id).group_by(ImpactScoreEvent.event_type).all()

    return [
        {
            "event_type": event_type,
            "label": EVENT_LABELS.get(event_type, event_type),
            "count": count,
            "points": int(points or 0),
        }
        for event_type, count, points in rows
    ]


def get_recent_events(user_id, limit=20):
    events = ImpactScoreEvent.query.filter_by(user_id=user_id).order_by(
        ImpactScoreEvent.created_at.desc(), ImpactScoreEvent.id.desc()
    ).limit(limit).all()
    return events


def public_rules():
    """The scoring rules, as shown to citizens - transparency is part of
    what makes the score trustworthy."""
    return {
        "weights": [
            {"event_type": key, "label": EVENT_LABELS[key], "points": value}
            for key, value in WEIGHTS.items()
        ],
        "daily_caps": DAILY_CAPS,
        "min_constructive_comment_length": MIN_CONSTRUCTIVE_COMMENT_LENGTH,
    }
