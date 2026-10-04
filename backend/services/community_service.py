"""
Community feed intelligence - everything the community API needs that is
not request handling: which civic issues are public, batched aggregation of
community signals, feed ranking, the factual issue timeline, and the
community notifications.

Privacy rule for everything in this module: a serialized issue never
contains a user id, name, email, or a complaint's free-text title or
description (a citizen wrote those for NMC, not for the public). Public
text is limited to the AI summary/observation, category and location.
"""

import math
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import case, func

from database.db import db
from models.civic_issue import CivicIssue
from models.community import (
    CivicIssueStatusChange,
    COMMENT_PUBLIC_STATUSES,
    IssueComment,
    IssueSupport,
    IssueVerification,
)
from models.complaint import Complaint
from models.notification import Notification
from services.issue_clustering import haversine_distance_meters
from utils.time_helper import to_iso8601, utc_now

# ==========================================
# Configuration
# ==========================================

PRIORITY_WEIGHTS = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
PRIORITY_BY_WEIGHT = {weight: name for name, weight in PRIORITY_WEIGHTS.items()}

DEFAULT_PER_PAGE = 10
MAX_PER_PAGE = 30

NEARBY_DEFAULT_RADIUS_KM = 3
NEARBY_MAX_RADIUS_KM = 25

# Trending = recent civic activity, not virality. Every signal is counted
# over the same window and the per-signal weights are returned alongside
# each issue so the ranking is explainable.
TRENDING_WINDOW_DAYS = 7
TRENDING_WEIGHTS = {
    "reports": 3,
    "supports": 2,
    "verifications": 2,
    "comments": 1,
}

# A Resolved issue whose community signal since resolution points the
# other way is surfaced to officers as "disputed" (advisory only).
DISPUTE_MIN_STILL_EXISTS = 3

ELIGIBLE_SPAM_STATES = ("NotFlagged", "Rejected")


def eligible_complaint_filter():
    """A complaint is public community evidence only once it is a genuine,
    in-scope report: not AI-flagged-and-awaiting-review, not confirmed
    spam, not rejected as out of scope."""
    return db.and_(
        Complaint.spam_review_status.in_(ELIGIBLE_SPAM_STATES),
        Complaint.rejection_status != "Rejected",
    )


def _priority_subquery():
    weight = case(
        *[(Complaint.ai_priority == name, value) for name, value in PRIORITY_WEIGHTS.items()],
        else_=0,
    )
    return db.session.query(
        Complaint.issue_id.label("issue_id"),
        func.max(weight).label("priority_weight"),
        func.count(Complaint.id).label("public_reports"),
        func.min(Complaint.created_at).label("first_reported_at"),
    ).filter(
        Complaint.issue_id.isnot(None),
        eligible_complaint_filter(),
    ).group_by(Complaint.issue_id).subquery()


def public_issue_query():
    """CivicIssues visible in the community - i.e. those with at least one
    eligible complaint. The inner join itself enforces that."""
    sq = _priority_subquery()
    query = db.session.query(CivicIssue, sq.c.priority_weight, sq.c.public_reports, sq.c.first_reported_at).join(
        sq, sq.c.issue_id == CivicIssue.id
    )
    return query, sq


def get_public_issue(issue_id):
    query, _ = public_issue_query()
    return query.filter(CivicIssue.id == issue_id).first()


def is_public_issue(issue_id):
    return db.session.query(
        Complaint.query.filter(Complaint.issue_id == issue_id, eligible_complaint_filter()).exists()
    ).scalar()


# ==========================================
# Batched aggregation (one grouped query per signal, for a whole page)
# ==========================================

def support_counts(issue_ids, since=None):
    if not issue_ids:
        return {}
    query = db.session.query(IssueSupport.civic_issue_id, func.count(IssueSupport.id)).filter(
        IssueSupport.civic_issue_id.in_(issue_ids)
    )
    if since is not None:
        query = query.filter(IssueSupport.created_at >= since)
    return dict(query.group_by(IssueSupport.civic_issue_id).all())


def comment_counts(issue_ids, since=None):
    if not issue_ids:
        return {}
    query = db.session.query(IssueComment.civic_issue_id, func.count(IssueComment.id)).filter(
        IssueComment.civic_issue_id.in_(issue_ids),
        IssueComment.moderation_status.in_(COMMENT_PUBLIC_STATUSES),
    )
    if since is not None:
        query = query.filter(IssueComment.created_at >= since)
    return dict(query.group_by(IssueComment.civic_issue_id).all())


def verification_counts(issue_ids, since=None):
    result = defaultdict(lambda: {"still_exists": 0, "resolved": 0, "not_sure": 0})
    if not issue_ids:
        return result
    query = db.session.query(
        IssueVerification.civic_issue_id,
        IssueVerification.verification_type,
        func.count(IssueVerification.id),
    ).filter(IssueVerification.civic_issue_id.in_(issue_ids))
    if since is not None:
        query = query.filter(IssueVerification.updated_at >= since)
    for issue_id, vtype, count in query.group_by(
        IssueVerification.civic_issue_id, IssueVerification.verification_type
    ).all():
        result[issue_id][vtype.lower()] = count
    return result


def viewer_state(issue_ids, viewer_id):
    if not issue_ids or viewer_id is None:
        return set(), {}
    supported = {
        row[0] for row in db.session.query(IssueSupport.civic_issue_id).filter(
            IssueSupport.civic_issue_id.in_(issue_ids),
            IssueSupport.user_id == viewer_id,
        ).all()
    }
    verified = dict(db.session.query(IssueVerification.civic_issue_id, IssueVerification.verification_type).filter(
        IssueVerification.civic_issue_id.in_(issue_ids),
        IssueVerification.user_id == viewer_id,
    ).all())
    return supported, verified


def cover_images(issue_ids):
    """Earliest eligible photo per issue."""
    if not issue_ids:
        return {}
    rows = db.session.query(Complaint.issue_id, Complaint.image_filename).filter(
        Complaint.issue_id.in_(issue_ids),
        Complaint.image_filename.isnot(None),
        eligible_complaint_filter(),
    ).order_by(Complaint.created_at.asc()).all()
    covers = {}
    for issue_id, filename in rows:
        covers.setdefault(issue_id, f"/uploads/{filename}")
    return covers


def departments(issue_ids):
    """Most common AI-assigned department among an issue's eligible reports."""
    if not issue_ids:
        return {}
    rows = db.session.query(Complaint.issue_id, Complaint.ai_department, func.count(Complaint.id)).filter(
        Complaint.issue_id.in_(issue_ids),
        Complaint.ai_department.isnot(None),
        eligible_complaint_filter(),
    ).group_by(Complaint.issue_id, Complaint.ai_department).all()
    best = {}
    for issue_id, dept, count in rows:
        if issue_id not in best or count > best[issue_id][1]:
            best[issue_id] = (dept, count)
    return {issue_id: dept for issue_id, (dept, _) in best.items()}


def last_resolved_at(issue_ids):
    if not issue_ids:
        return {}
    return dict(db.session.query(
        CivicIssueStatusChange.civic_issue_id, func.max(CivicIssueStatusChange.created_at)
    ).filter(
        CivicIssueStatusChange.civic_issue_id.in_(issue_ids),
        CivicIssueStatusChange.new_status == "Resolved",
    ).group_by(CivicIssueStatusChange.civic_issue_id).all())


def disputed_issue_ids(issues):
    """Officially Resolved issues where, since that resolution, more
    citizens report the problem still present than resolved. Falls back to
    updated_at for issues resolved before status history existed."""
    resolved = [issue for issue in issues if issue.status == "Resolved"]
    if not resolved:
        return set()
    resolved_at = last_resolved_at([i.id for i in resolved])
    disputed = set()
    for issue in resolved:
        since = resolved_at.get(issue.id) or issue.updated_at
        rows = dict(db.session.query(IssueVerification.verification_type, func.count(IssueVerification.id)).filter(
            IssueVerification.civic_issue_id == issue.id,
            IssueVerification.updated_at >= since,
        ).group_by(IssueVerification.verification_type).all())
        still = rows.get("STILL_EXISTS", 0)
        if still >= DISPUTE_MIN_STILL_EXISTS and still > rows.get("RESOLVED", 0):
            disputed.add(issue.id)
    return disputed


# ==========================================
# Serialization
# ==========================================

def short_location(label):
    if not label:
        return "Nashik"
    parts = [part.strip() for part in label.split(",") if part.strip()]
    return ", ".join(parts[:2]) if parts else "Nashik"


def issue_title(issue):
    return f"{issue.category} near {short_location(issue.location_label)}"


def serialize_issue_cards(rows, viewer_id=None, extras=None):
    """rows: [(CivicIssue, priority_weight, public_reports, first_reported_at)]"""
    issue_ids = [row[0].id for row in rows]
    supports = support_counts(issue_ids)
    comments = comment_counts(issue_ids)
    verifications = verification_counts(issue_ids)
    covers = cover_images(issue_ids)
    depts = departments(issue_ids)
    supported, verified = viewer_state(issue_ids, viewer_id)
    extras = extras or {}

    cards = []
    for issue, priority_weight, public_reports, first_reported_at in rows:
        card = {
            "id": issue.id,
            "title": issue_title(issue),
            "category": issue.category,
            "location_label": issue.location_label,
            "latitude": issue.latitude,
            "longitude": issue.longitude,
            "summary": issue.ai_summary,
            "image_url": covers.get(issue.id),
            "report_count": public_reports,
            "first_reported_at": to_iso8601(first_reported_at or issue.created_at),
            "updated_at": to_iso8601(issue.updated_at),
            "official": {
                "status": issue.status,
                "priority": PRIORITY_BY_WEIGHT.get(priority_weight),
                "department": depts.get(issue.id),
            },
            "community": {
                "supporters": supports.get(issue.id, 0),
                "comments": comments.get(issue.id, 0),
                "verification": dict(verifications[issue.id]),
            },
            "viewer": {
                "supported": issue.id in supported,
                "verification": verified.get(issue.id),
            },
        }
        card.update(extras.get(issue.id, {}))
        cards.append(card)
    return cards


# ==========================================
# Feed
# ==========================================

def _apply_filters(query, category=None, status=None, search=None):
    if category:
        query = query.filter(CivicIssue.category == category)
    if status:
        query = query.filter(CivicIssue.status == status)
    if search:
        like = f"%{search.strip()[:100]}%"
        query = query.filter(db.or_(
            CivicIssue.ai_summary.ilike(like),
            CivicIssue.location_label.ilike(like),
            CivicIssue.category.ilike(like),
        ))
    return query


def _paginate_list(items, page, per_page):
    start = (page - 1) * per_page
    return items[start:start + per_page], len(items)


def build_feed(sort, page, per_page, viewer_id, category=None, status=None, search=None,
               latitude=None, longitude=None, radius_km=None):
    query, sq = public_issue_query()
    query = _apply_filters(query, category, status, search)
    extras = {}

    if sort == "nearby":
        radius_m = radius_km * 1000
        # Cheap bounding-box prefilter in SQL, exact distance in Python.
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * max(math.cos(math.radians(latitude)), 0.01))
        candidates = query.filter(
            CivicIssue.latitude.between(latitude - lat_delta, latitude + lat_delta),
            CivicIssue.longitude.between(longitude - lng_delta, longitude + lng_delta),
        ).all()
        with_distance = []
        for row in candidates:
            distance = haversine_distance_meters(latitude, longitude, row[0].latitude, row[0].longitude)
            if distance <= radius_m:
                with_distance.append((distance, row))
        with_distance.sort(key=lambda pair: pair[0])
        page_rows, total = _paginate_list(with_distance, page, per_page)
        extras = {row[0].id: {"distance_m": round(distance)} for distance, row in page_rows}
        rows = [row for _, row in page_rows]

    elif sort == "trending":
        since = utc_now() - timedelta(days=TRENDING_WINDOW_DAYS)
        candidates = query.filter(CivicIssue.status != "Resolved").all()
        ids = [row[0].id for row in candidates]
        signals = {
            "supports": support_counts(ids, since),
            "verifications": {
                issue_id: sum(counts.values()) for issue_id, counts in verification_counts(ids, since).items()
            },
            "comments": comment_counts(ids, since),
            "reports": dict(db.session.query(Complaint.issue_id, func.count(Complaint.id)).filter(
                Complaint.issue_id.in_(ids), Complaint.created_at >= since, eligible_complaint_filter()
            ).group_by(Complaint.issue_id).all()) if ids else {},
        }
        scored = []
        for row in candidates:
            issue, priority_weight = row[0], row[1] or 0
            activity = {name: signals[name].get(issue.id, 0) for name in TRENDING_WEIGHTS}
            activity_score = sum(activity[name] * weight for name, weight in TRENDING_WEIGHTS.items())
            if activity_score == 0:
                continue
            score = activity_score + priority_weight
            scored.append((score, issue.updated_at, row, activity))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        page_items, total = _paginate_list(scored, page, per_page)
        extras = {
            row[0].id: {"trending": {"score": score, "window_days": TRENDING_WINDOW_DAYS, "recent_activity": activity}}
            for score, _, row, activity in page_items
        }
        rows = [row for _, _, row, _ in page_items]

    elif sort == "priority":
        query = query.filter(sq.c.priority_weight >= PRIORITY_WEIGHTS["High"]).order_by(
            sq.c.priority_weight.desc(), CivicIssue.updated_at.desc(), CivicIssue.id.desc()
        )
        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()

    else:  # recent
        query = query.order_by(CivicIssue.updated_at.desc(), CivicIssue.id.desc())
        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "sort": sort,
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_more": page * per_page < total,
        "issues": serialize_issue_cards(rows, viewer_id, extras),
    }


# ==========================================
# Issue detail: evidence + factual timeline
# ==========================================

def issue_evidence(issue_id, limit=6):
    complaints = Complaint.query.filter(
        Complaint.issue_id == issue_id,
        Complaint.image_filename.isnot(None),
        eligible_complaint_filter(),
    ).order_by(Complaint.created_at.asc()).limit(limit).all()
    return [
        {
            "image_url": f"/uploads/{c.image_filename}",
            "observation": c.ai_visual_observation,
            "reported_at": to_iso8601(c.created_at),
        }
        for c in complaints
    ]


def issue_timeline(issue):
    """Only events that are actually recorded in the database."""
    events = []

    complaints = Complaint.query.filter(
        Complaint.issue_id == issue.id, eligible_complaint_filter()
    ).order_by(Complaint.created_at.asc()).limit(50).all()

    for index, complaint in enumerate(complaints):
        if index == 0:
            events.append({
                "at": to_iso8601(complaint.created_at),
                "kind": "reported",
                "label": "Issue first reported",
                "detail": None,
            })
            # AI analysis runs synchronously as part of submission, so it
            # completed at the moment the report was stored.
            if complaint.ai_priority or complaint.ai_summary:
                detail = ", ".join(filter(None, [
                    f"Category: {complaint.category}" if complaint.category else None,
                    f"Priority: {complaint.ai_priority}" if complaint.ai_priority else None,
                    f"Department: {complaint.ai_department}" if complaint.ai_department else None,
                ]))
                events.append({
                    "at": to_iso8601(complaint.created_at),
                    "kind": "ai",
                    "label": "AI analysis completed",
                    "detail": detail or None,
                })
        else:
            events.append({
                "at": to_iso8601(complaint.created_at),
                "kind": "report_added",
                "label": "Another citizen reported this issue",
                "detail": None,
            })

    for change in CivicIssueStatusChange.query.filter_by(civic_issue_id=issue.id).order_by(
        CivicIssueStatusChange.created_at.asc()
    ).all():
        events.append({
            "at": to_iso8601(change.created_at),
            "kind": "official",
            "label": f"Official status changed to {change.new_status}",
            "detail": f"Previously {change.old_status}" if change.old_status else None,
        })

    latest_verification = db.session.query(func.max(IssueVerification.updated_at)).filter(
        IssueVerification.civic_issue_id == issue.id
    ).scalar()
    if latest_verification:
        counts = verification_counts([issue.id])[issue.id]
        events.append({
            "at": to_iso8601(latest_verification),
            "kind": "community",
            "label": "Latest community verification",
            "detail": (
                f"{counts['still_exists']} still present · {counts['resolved']} resolved · "
                f"{counts['not_sure']} not sure"
            ),
        })

    events.sort(key=lambda event: event["at"] or "")
    return events


# ==========================================
# Notifications - deliberately few. Never for individual supports,
# verifications, or comments; only for things a citizen would want to know.
# ==========================================

NOTIFY_ON_STATUSES = ("In Progress", "Resolved")


def notify_complaint_grouped(complaint):
    """Tell a citizen their report joined a civic issue other citizens had
    already reported. Skipped while the report awaits spam review."""
    if not complaint.issue_id or complaint.spam_review_status != "NotFlagged":
        return
    others = db.session.query(func.count(func.distinct(Complaint.user_id))).filter(
        Complaint.issue_id == complaint.issue_id,
        Complaint.user_id != complaint.user_id,
        eligible_complaint_filter(),
    ).scalar() or 0
    if others == 0:
        return
    db.session.add(Notification(
        user_id=complaint.user_id,
        complaint_id=complaint.id,
        message=(
            f'Your report "{complaint.title}" was grouped with an existing civic issue that '
            f"{others} other citizen{'s' if others != 1 else ''} also reported. You can follow its "
            f"progress and community updates in the Community feed."
        ),
    ))


def notify_issue_status_changed(issue, new_status):
    """One notification per affected citizen per official status change:
    reporters of the issue, plus citizens who publicly supported it."""
    if new_status not in NOTIFY_ON_STATUSES:
        return

    label = issue_title(issue)
    reporters = dict(db.session.query(Complaint.user_id, func.max(Complaint.id)).filter(
        Complaint.issue_id == issue.id, eligible_complaint_filter()
    ).group_by(Complaint.user_id).all())
    supporters = {
        row[0] for row in db.session.query(IssueSupport.user_id).filter_by(civic_issue_id=issue.id).all()
    }

    for user_id, complaint_id in reporters.items():
        if new_status == "Resolved":
            message = (
                f"✅ The civic issue you reported ({label}) has been officially marked Resolved by NMC. "
                f"Thank you - your report contributed to this resolution. If it is still present, "
                f"you can say so in the Community feed."
            )
        else:
            message = f"🔧 NMC has started work on the civic issue you reported ({label}). Status: In Progress."
        db.session.add(Notification(user_id=user_id, complaint_id=complaint_id, message=message))

    for user_id in supporters - set(reporters):
        db.session.add(Notification(
            user_id=user_id,
            message=f"A civic issue you support ({label}) is now officially {new_status}.",
        ))
