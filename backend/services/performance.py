"""Ratings, corrective follow-ups, and the Chief Officer supervisory overview.

Policy encoded here (confirmed product decisions):
  * Only a Chief Officer rates, and only *approved* resolution work.  A rating
    is a separate decision: it never changes a review or an issue.
  * A 1- or 2-star rating opens exactly one corrective follow-up for that job.
    The follow-up has its own workflow and never touches the issue's status.
  * Nothing here penalises, suspends, or demotes anyone.

Concurrency follows the rest of the project: SQLite has no row locks and a
SELECT does not start a write transaction, so every mutation first takes the
write lock with a conditional UPDATE that also verifies the state it relies
on, then re-reads.
"""

from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import func

from database.db import db
from models.civic_issue import CivicIssue
from models.complaint import Complaint
from models.performance import (
    FOLLOW_UP_STATES,
    LOW_RATING_MAX,
    OPEN_FOLLOW_UP_STATES,
    FollowUpEvent,
    ResolutionFollowUp,
    ResolutionRating,
)
from models.notification import Notification
from models.resolution_review import ResolutionReview
from models.user import User
from models.ward import Ward, WardOfficerAssignment
from models.work_update import IssueWorkUpdate
from services.resolution_workflow import ELIGIBLE_SPAM_STATES, stale_reviews_awaiting_resubmission
from utils.time_helper import to_iso8601, utc_now

MAX_EXPLANATION = 2000
MAX_NOTE = 2000
ISSUE_STATUSES = ("Pending", "In Progress", "Pending Review", "Resolved")
COMPLAINT_STATUSES = ("Pending", "In Progress", "Resolved")
TREND_WEEKS = 8


class PerformanceError(ValueError):
    """A rule violation with a client-safe message and HTTP status."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def clean_text(value, field, maximum, required=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise PerformanceError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise PerformanceError(f"{field} must be text")
    value = value.strip()
    if len(value) > maximum:
        raise PerformanceError(f"{field} must be at most {maximum} characters")
    return value


# ==========================================
# Notifications (existing in-app Notification table)
# ==========================================

def work_label(issue):
    place = issue.location_label or "no location recorded"
    return f"{issue.category}, {place}"


def notify(user_id, message):
    """Queue an in-app notification in the caller's transaction.  It commits or
    rolls back with the change that caused it, so a retried or lost request can
    never leave a duplicate or an orphan.  Messages never carry rating
    explanations or notes; those are read inside the authorised screens."""
    db.session.add(Notification(user_id=user_id, message=message))


def _chief_recipients(follow_up):
    """The Chief Officer who last assigned the case, else every Chief Officer."""
    last = FollowUpEvent.query.filter(
        FollowUpEvent.follow_up_id == follow_up.id,
        FollowUpEvent.event_type.in_(("Assigned", "Reassigned")),
    ).order_by(FollowUpEvent.id.desc()).first()
    if last:
        actor = db.session.get(User, last.actor_id)
        if actor and actor.role == "Chief Officer":
            return [actor.id]
    return [chief.id for chief in User.query.filter_by(role="Chief Officer").all()]


# ==========================================
# Ratings
# ==========================================

def effective_ratings_query():
    """Ratings that have not been superseded by a revision."""
    revised = db.session.query(ResolutionRating.supersedes_rating_id).filter(
        ResolutionRating.supersedes_rating_id.isnot(None)
    )
    return ResolutionRating.query.filter(~ResolutionRating.id.in_(revised))


def latest_rating(review_id):
    return ResolutionRating.query.filter_by(resolution_review_id=review_id).order_by(
        ResolutionRating.id.desc()
    ).first()


def _lock_approved_review(review_id):
    """Take the write lock and confirm the review is (still) Approved.

    The update writes the same value back: the review itself is not altered.
    """
    return ResolutionReview.query.filter(
        ResolutionReview.id == review_id, ResolutionReview.state == "Approved"
    ).update({ResolutionReview.state: ResolutionReview.state}, synchronize_session=False) == 1


def create_rating(review, chief, stars, explanation, revises_rating_id):
    """Append a rating (or a revision) for approved work; may open a follow-up (never closes, moves or deletes one).

    Runs in the caller's transaction; the caller commits.  Raises PerformanceError.
    """
    if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= 5:
        raise PerformanceError("stars must be a whole number from 1 to 5")
    explanation = clean_text(explanation, "explanation", MAX_EXPLANATION)
    low = stars <= LOW_RATING_MAX
    if low and not explanation:
        raise PerformanceError("An explanation is required for a rating of 1 or 2 stars")

    if not _lock_approved_review(review.id):
        raise PerformanceError("Only approved work can be rated", status=409)
    db.session.expire_all()

    previous = latest_rating(review.id)
    if previous is None:
        if revises_rating_id is not None:
            raise PerformanceError("There is no earlier rating to revise", status=409)
    else:
        if revises_rating_id is None:
            raise PerformanceError(
                f"This work is already rated; submit a revision of rating {previous.id}", status=409
            )
        if revises_rating_id != previous.id:
            raise PerformanceError("That rating has already been revised; reload and try again", status=409)
        if not explanation:
            raise PerformanceError("A revision needs an explanation of why the rating changed")

    rating = ResolutionRating(
        resolution_review_id=review.id,
        rated_officer_id=review.submitted_by,  # from the work record, never from the client
        rated_by=chief.id,
        stars=stars,
        explanation=explanation,
        needs_follow_up=low,
        supersedes_rating_id=previous.id if previous else None,
    )
    db.session.add(rating)
    db.session.flush()

    # One corrective case per job.  A revision never moves, closes, or deletes an
    # existing case (a raised rating leaves it for the Chief Officer to work
    # through); a revision that lowers the rating opens the case if none exists.
    follow_up = ResolutionFollowUp.query.filter_by(resolution_review_id=review.id).first()
    if low and follow_up is None:
        follow_up = ResolutionFollowUp(
            resolution_review_id=review.id, rating_id=rating.id, issue_id=review.issue_id,
            created_by=chief.id, status="Awaiting Assignment",
        )
        db.session.add(follow_up)
        db.session.flush()
        add_event(follow_up, "Created", None, "Awaiting Assignment", chief.id,
                  note=f"Opened by a {stars}-star rating")

    verb = "updated to" if previous else "received"
    notify(review.submitted_by,
           f"Your completed work ({work_label(review.issue)}) {verb} a {stars}-star rating from the Chief Officer. "
           "Open 'My ratings & corrections' to read the feedback.")
    return rating


# ==========================================
# Follow-ups
# ==========================================

def add_event(follow_up, event_type, from_status, to_status, actor_id, officer_id=None, note=None, image=None):
    event = FollowUpEvent(
        follow_up_id=follow_up.id, event_type=event_type, from_status=from_status,
        to_status=to_status, actor_id=actor_id, officer_id=officer_id, note=note, image_filename=image,
    )
    db.session.add(event)
    return event


def _transition(follow_up_id, expected_status, expected_officer_id, **changes):
    """Compare-and-swap the follow-up's state; True if this call won."""
    return ResolutionFollowUp.query.filter(
        ResolutionFollowUp.id == follow_up_id,
        ResolutionFollowUp.status == expected_status,
        ResolutionFollowUp.assigned_officer_id == expected_officer_id,
    ).update(changes, synchronize_session=False) == 1


def assign_follow_up(follow_up, chief, officer_id, reason):
    if isinstance(officer_id, bool) or not isinstance(officer_id, int):
        raise PerformanceError("officer_id must be a whole number")
    reason = clean_text(reason, "reason", 500)
    officer = db.session.get(User, officer_id)
    if not officer:
        raise PerformanceError("Officer not found", status=404)
    if officer.role != "Officer":
        raise PerformanceError("Only users with the Officer role can be assigned a correction")
    if officer.is_suspended:
        raise PerformanceError("A suspended Officer cannot be assigned a correction")

    old_status, old_officer = follow_up.status, follow_up.assigned_officer_id
    if old_status not in ("Awaiting Assignment", "Assigned"):
        raise PerformanceError(f"A follow-up that is '{old_status}' cannot be (re)assigned", status=409)
    if old_officer == officer_id:
        raise PerformanceError("This Officer is already assigned to the follow-up", status=409)

    if not _transition(follow_up.id, old_status, old_officer, status="Assigned", assigned_officer_id=officer_id):
        raise PerformanceError("The follow-up changed while assigning; reload and try again", status=409)
    db.session.expire_all()
    follow_up = db.session.get(ResolutionFollowUp, follow_up.id)
    add_event(follow_up, "Reassigned" if old_officer else "Assigned", old_status, "Assigned",
              chief.id, officer_id=officer_id, note=reason)
    label = work_label(follow_up.issue)
    notify(officer_id, f"A corrective follow-up has been assigned to you ({label}). "
                       "Open 'My ratings & corrections' to see what is needed.")
    if old_officer:
        notify(old_officer, f"The corrective follow-up for {label} was reassigned to another Officer.")
    return follow_up


def submit_correction(follow_up, officer, note, image_filename):
    note = clean_text(note, "note", MAX_NOTE, required=True)
    if follow_up.assigned_officer_id != officer.id:
        raise PerformanceError("Follow-up not found", status=404)
    if not _transition(follow_up.id, "Assigned", officer.id, status="Correction Submitted"):
        raise PerformanceError("This follow-up is not awaiting a correction", status=409)
    db.session.expire_all()
    follow_up = db.session.get(ResolutionFollowUp, follow_up.id)
    add_event(follow_up, "CorrectionSubmitted", "Assigned", "Correction Submitted",
              officer.id, officer_id=officer.id, note=note, image=image_filename)
    for recipient in _chief_recipients(follow_up):
        notify(recipient, f"{officer.name} submitted a correction for {work_label(follow_up.issue)}; it awaits your verification.")
    return follow_up


def verify_follow_up(follow_up, chief, decision, note):
    note = clean_text(note, "note", MAX_NOTE)
    if decision not in ("Close", "Return"):
        raise PerformanceError("decision must be Close or Return")
    if decision == "Return" and not note:
        raise PerformanceError("A note explaining what is still needed is required to return the correction")
    officer_id = follow_up.assigned_officer_id
    if decision == "Close":
        won = _transition(follow_up.id, "Correction Submitted", officer_id, status="Closed", closed_at=utc_now())
        target, event_type = "Closed", "Closed"
    else:
        won = _transition(follow_up.id, "Correction Submitted", officer_id, status="Assigned")
        target, event_type = "Assigned", "CorrectionReturned"
    if not won:
        raise PerformanceError("This follow-up has no submitted correction awaiting verification", status=409)
    db.session.expire_all()
    follow_up = db.session.get(ResolutionFollowUp, follow_up.id)
    add_event(follow_up, event_type, "Correction Submitted", target, chief.id, officer_id=officer_id, note=note)
    label = work_label(follow_up.issue)
    if decision == "Close":
        notify(officer_id, f"Your correction for {label} was verified and the follow-up is closed.")
    else:
        notify(officer_id, f"Your correction for {label} was returned by the Chief Officer for more work. "
                           "Open 'My ratings & corrections' for the details.")
    return follow_up


# ==========================================
# Supervisory overview (read-only, municipality-wide)
# ==========================================

def parse_day(value, field, end_of_day=False):
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise PerformanceError(f"{field} must be a date like 2026-01-31") from None
    if end_of_day:
        day += timedelta(days=1)  # inclusive end date -> exclusive bound
    return day


def _window(column, start, end):
    conditions = []
    if start is not None:
        conditions.append(column >= start)
    if end is not None:
        conditions.append(column < end)
    return conditions


def _zero_filled(rows, known):
    counts = {key: 0 for key in known}
    other = 0
    for key, count in rows:
        if key in counts:
            counts[key] = count
        else:
            other += count
    if other:
        counts["Other"] = other
    return counts


def _week_start(moment):
    day = moment.date()
    return day - timedelta(days=day.weekday())


def build_overview(ward_id=None, officer_id=None, start=None, end=None):
    """Metric definitions (also returned to the client under ``definitions``):

    * issues / complaints are counted separately and are never interchangeable.
      Complaint counts exclude confirmed spam and out-of-scope rejections.
    * Pending Review is an issue status of its own and is never merged into
      Pending or In Progress.
    * Wards: only the ward <-> Officer assignment records exist.  Complaints and
      issues are not linked to wards, so no ward-level issue/complaint figure is
      produced.  Per-Officer activity is municipality-wide, not ward-limited.
    * Work submissions are activity counts, not caseload: Officers are not
      assigned issues, so the number says what they did, not what they owe.
    * Stale and superseded reviews are not rejected work.  ``pending_decision``
      awaits the Chief Officer; ``stale_awaiting_resubmission`` awaits the Officer.
    * Resolution time = issue created_at -> reviewed_at of its latest Approved
      review, for currently Resolved issues.  ``updated_at`` is never used.
    * Trends use real submitted_at / reviewed_at timestamps, bucketed by week.
    * No SLA or overdue classification exists; none is computed.
    """
    officers_query = User.query.filter_by(role="Officer")
    selected_ward = None
    if ward_id is not None:
        selected_ward = db.session.get(Ward, ward_id)
        if not selected_ward:
            raise PerformanceError("Ward not found", status=404)
    if officer_id is not None:
        target = db.session.get(User, officer_id)
        if not target or target.role != "Officer":
            raise PerformanceError("Officer not found", status=404)

    all_officers = officers_query.order_by(User.name.asc(), User.id.asc()).all()
    active_assignments = WardOfficerAssignment.query.filter_by(ended_at=None).all()
    wards_of = {}
    officers_of = {}
    for row in active_assignments:
        wards_of.setdefault(row.officer_id, set()).add(row.ward_id)
        officers_of.setdefault(row.ward_id, set()).add(row.officer_id)

    officers = all_officers
    if selected_ward is not None:
        officers = [o for o in officers if selected_ward.id in wards_of.get(o.id, set())]
    if officer_id is not None:
        officers = [o for o in officers if o.id == officer_id]
    shown_ids = {o.id for o in officers}
    # Review/rating/work figures follow the officer filter only (a ward filter
    # narrows who is listed; it does not claim work happened "in" the ward).
    work_ids = {officer_id} if officer_id is not None else None

    def by_officer(column):
        return [] if work_ids is None else [column.in_(work_ids)]

    # ----- wards
    ward_rows = Ward.query.filter_by(is_active=True).order_by(Ward.name.asc(), Ward.id.asc()).all()
    if selected_ward is not None:
        ward_rows = [w for w in ward_rows if w.id == selected_ward.id]
    users_by_id = {o.id: o for o in all_officers}

    def brief(user):
        return {"id": user.id, "name": user.name, "email": user.email, "is_suspended": user.is_suspended}

    wards = {
        "active_total": Ward.query.filter_by(is_active=True).count(),
        "items": [
            {
                "id": w.id, "name": w.name, "code": w.code,
                "officers": [brief(users_by_id[i]) for i in sorted(officers_of.get(w.id, set())) if i in users_by_id],
            }
            for w in ward_rows
        ],
        "work_by_ward": {
            "available": False,
            "reason": "Complaints and issues are not linked to wards, so work cannot be attributed to a ward.",
        },
    }

    # ----- reviews (by submitting officer)
    review_window = _window(ResolutionReview.submitted_at, start, end) + by_officer(ResolutionReview.submitted_by)
    state_counts = dict(db.session.query(ResolutionReview.state, func.count(ResolutionReview.id)).filter(
        *review_window).group_by(ResolutionReview.state).all())
    current = by_officer(ResolutionReview.submitted_by)
    pending_decision = ResolutionReview.query.filter(ResolutionReview.state == "Pending", *current).count()
    stale_waiting = [r for r in stale_reviews_awaiting_resubmission()
                     if work_ids is None or r.submitted_by in work_ids]
    reviews = {
        "submitted": sum(state_counts.values()),
        "approved": state_counts.get("Approved", 0),
        "rejected": state_counts.get("Rejected", 0),
        "superseded": state_counts.get("Superseded", 0),
        "stale_total": state_counts.get("Stale", 0),
        "resubmissions": ResolutionReview.query.filter(
            ResolutionReview.supersedes_review_id.isnot(None), *review_window).count(),
        "pending_decision": pending_decision,
        "stale_awaiting_resubmission": len(stale_waiting),
    }

    update_window = _window(IssueWorkUpdate.created_at, start, end) + by_officer(IssueWorkUpdate.officer_id)
    work = {
        "work_updates": IssueWorkUpdate.query.filter(*update_window).count(),
        "issues_with_work_updates": db.session.query(func.count(func.distinct(IssueWorkUpdate.issue_id))).filter(
            *update_window).scalar() or 0,
        "review_submissions": reviews["submitted"],
        "issues_with_review_submissions": db.session.query(func.count(func.distinct(ResolutionReview.issue_id))).filter(
            *review_window).scalar() or 0,
        "note": "Submissions are activity. One issue can have many; they are not unique issues and not caseload.",
    }

    # ----- issues and complaints (current state, municipality-wide)
    issue_rows = db.session.query(CivicIssue.status, func.count(CivicIssue.id)).group_by(CivicIssue.status).all()
    eligible = db.and_(Complaint.spam_review_status.in_(ELIGIBLE_SPAM_STATES), Complaint.rejection_status != "Rejected")
    complaint_rows = db.session.query(Complaint.status, func.count(Complaint.id)).filter(eligible).group_by(
        Complaint.status).all()
    issues = {"total": sum(c for _, c in issue_rows), "by_status": _zero_filled(issue_rows, ISSUE_STATUSES)}
    complaints = {
        "eligible_total": sum(c for _, c in complaint_rows),
        "by_status": _zero_filled(complaint_rows, COMPLAINT_STATUSES),
        "eligible_without_issue_link": Complaint.query.filter(eligible, Complaint.issue_id.is_(None)).count(),
        "excluded_confirmed_spam": Complaint.query.filter(Complaint.spam_review_status == "Confirmed").count(),
        "excluded_out_of_scope": Complaint.query.filter(Complaint.rejection_status == "Rejected").count(),
    }

    # ----- ratings (effective = not superseded)
    rating_window = _window(ResolutionRating.created_at, start, end) + by_officer(ResolutionRating.rated_officer_id)
    effective = effective_ratings_query().filter(*rating_window)
    stars_rows = dict(db.session.query(ResolutionRating.stars, func.count(ResolutionRating.id)).filter(
        ResolutionRating.id.in_(effective.with_entities(ResolutionRating.id))).group_by(ResolutionRating.stars).all())
    ratings = {
        "effective_total": sum(stars_rows.values()),
        "low_total": sum(c for s, c in stars_rows.items() if s <= LOW_RATING_MAX),
        "by_stars": {str(s): stars_rows.get(s, 0) for s in range(1, 6)},
        "revisions": ResolutionRating.query.filter(ResolutionRating.supersedes_rating_id.isnot(None),
                                                   *rating_window).count(),
        "approved_not_yet_rated": ResolutionReview.query.filter(
            ResolutionReview.state == "Approved", *current,
            ~ResolutionReview.id.in_(db.session.query(ResolutionRating.resolution_review_id))).count(),
    }

    # ----- follow-ups
    follow_ups_q = ResolutionFollowUp.query.join(
        ResolutionReview, ResolutionReview.id == ResolutionFollowUp.resolution_review_id
    ).filter(*_window(ResolutionFollowUp.created_at, start, end), *by_officer(ResolutionReview.submitted_by))
    follow_ups = {
        "total": follow_ups_q.count(),
        "by_status": _zero_filled(
            follow_ups_q.with_entities(ResolutionFollowUp.status, func.count(ResolutionFollowUp.id)).group_by(
                ResolutionFollowUp.status).all(), FOLLOW_UP_STATES),
    }

    # ----- resolution time (valid history only)
    latest_approved = db.session.query(
        ResolutionReview.issue_id, func.max(ResolutionReview.id).label("review_id")
    ).filter(ResolutionReview.state == "Approved").group_by(ResolutionReview.issue_id).subquery()
    resolved_issues = CivicIssue.query.filter_by(status="Resolved").all()
    approved_by_issue = {
        review.issue_id: review for review in ResolutionReview.query.filter(
            ResolutionReview.id.in_(db.session.query(latest_approved.c.review_id))).all()
    }
    hours, excluded = [], 0
    for issue in resolved_issues:
        review = approved_by_issue.get(issue.id)
        if review is None or review.reviewed_at is None or issue.created_at is None:
            excluded += 1
            continue
        if work_ids is not None and review.submitted_by not in work_ids:
            continue
        if (start and review.reviewed_at < start) or (end and review.reviewed_at >= end):
            continue
        elapsed = (review.reviewed_at - issue.created_at).total_seconds() / 3600
        if elapsed >= 0:
            hours.append(elapsed)
    resolution_time = {
        "available": bool(hours),
        "sample_size": len(hours),
        "average_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "median_hours": round(median(hours), 1) if hours else None,
        "excluded_resolved_without_approved_review": excluded,
        "basis": "issue created_at to the latest Approved review's reviewed_at; resolved issues without an "
                 "approved review (legacy data) are excluded and counted",
    }

    # ----- trends (real timestamps, weekly)
    today = utc_now().replace(tzinfo=None)
    first_week = _week_start(today) - timedelta(weeks=TREND_WEEKS - 1)
    since = datetime.combine(first_week, datetime.min.time())
    submitted = {}
    approved = {}
    for review in ResolutionReview.query.filter(ResolutionReview.submitted_at >= since, *current).all():
        key = _week_start(review.submitted_at)
        submitted[key] = submitted.get(key, 0) + 1
    for review in ResolutionReview.query.filter(
            ResolutionReview.state == "Approved", ResolutionReview.reviewed_at >= since, *current).all():
        key = _week_start(review.reviewed_at)
        approved[key] = approved.get(key, 0) + 1
    weeks = [first_week + timedelta(weeks=i) for i in range(TREND_WEEKS)]
    trends = {
        "available": True,
        "bucket": "week (Monday start, UTC)",
        "weeks": [{"week_start": day.isoformat(), "reviews_submitted": submitted.get(day, 0),
                   "reviews_approved": approved.get(day, 0)} for day in weeks],
    }

    # ----- per-officer activity
    work_counts = dict(db.session.query(IssueWorkUpdate.officer_id, func.count(IssueWorkUpdate.id)).filter(
        *_window(IssueWorkUpdate.created_at, start, end)).group_by(IssueWorkUpdate.officer_id).all())
    review_counts = {}
    for who, state, count in db.session.query(
            ResolutionReview.submitted_by, ResolutionReview.state, func.count(ResolutionReview.id)).filter(
            *_window(ResolutionReview.submitted_at, start, end)).group_by(
            ResolutionReview.submitted_by, ResolutionReview.state).all():
        review_counts.setdefault(who, {})[state] = count
    rating_counts = {}
    for who, stars, count in db.session.query(
            ResolutionRating.rated_officer_id, ResolutionRating.stars, func.count(ResolutionRating.id)).filter(
            ResolutionRating.id.in_(effective_ratings_query().filter(
                *_window(ResolutionRating.created_at, start, end)).with_entities(ResolutionRating.id))).group_by(
            ResolutionRating.rated_officer_id, ResolutionRating.stars).all():
        rating_counts.setdefault(who, {})[stars] = count
    open_corrections = dict(db.session.query(
        ResolutionFollowUp.assigned_officer_id, func.count(ResolutionFollowUp.id)).filter(
        ResolutionFollowUp.status.in_(("Assigned", "Correction Submitted")),
        ResolutionFollowUp.assigned_officer_id.isnot(None)).group_by(ResolutionFollowUp.assigned_officer_id).all())
    officer_items = []
    for officer in officers:
        states = review_counts.get(officer.id, {})
        stars = rating_counts.get(officer.id, {})
        officer_items.append({
            **brief(officer),
            "ward_ids": sorted(wards_of.get(officer.id, set())),
            "assignment_status": "Assigned" if wards_of.get(officer.id) else "Unassigned",
            "work_updates": work_counts.get(officer.id, 0),
            "reviews_submitted": sum(states.values()),
            "reviews_approved": states.get("Approved", 0),
            "reviews_rejected": states.get("Rejected", 0),
            "ratings_received": sum(stars.values()),
            "low_ratings_received": sum(c for s, c in stars.items() if s <= LOW_RATING_MAX),
            "open_corrections_assigned": open_corrections.get(officer.id, 0),
        })
    officers_section = {
        "total": len(all_officers),
        "suspended": sum(1 for o in all_officers if o.is_suspended),
        "assigned_to_a_ward": sum(1 for o in all_officers if wards_of.get(o.id)),
        "unassigned": sum(1 for o in all_officers if not wards_of.get(o.id)),
        "shown": len(officer_items),
        "items": officer_items,
        "note": "Activity counts are municipality-wide and are not a caseload: Officers are not assigned issues.",
    }

    return {
        "scope": "municipality",
        "generated_at": to_iso8601(utc_now()),
        "filters": {
            "ward_id": ward_id, "officer_id": officer_id,
            "from": start.date().isoformat() if start else None,
            "to": (end - timedelta(days=1)).date().isoformat() if end else None,
            "applies_to": {
                "ward_id": "wards and officers lists only (issues and complaints are not linked to wards)",
                "officer_id": "officer-attributed figures: reviews, ratings, follow-ups, resolution time, trends",
                "date_range": "event counts (reviews submitted, ratings, follow-ups, activity); not current-state counts",
            },
        },
        "wards": wards,
        "officers": officers_section,
        "issues": issues,
        "complaints": complaints,
        "reviews": reviews,
        "work": work,
        "ratings": ratings,
        "follow_ups": follow_ups,
        "resolution_time": resolution_time,
        "trends": trends,
        "definitions": {
            "issues_vs_complaints": "An issue groups one or more complaints; the two are counted separately.",
            "pending_review": "Issues whose completed work awaits (or awaited) Chief Officer review; kept separate from Pending.",
            "stale": "A stale review was withdrawn by new information; it is not rejected work.",
            "work_updates": "Field-work log entries by the Officer; not a measure of caseload.",
            "overdue": "Not computed: no approved SLA policy exists.",
        },
    }


# ==========================================
# Directory detail views (read-only, municipality-wide)
# ==========================================

def issue_brief(issue):
    return {"id": issue.id, "category": issue.category,
            "location_label": issue.location_label, "status": issue.status}


def _user_brief(user):
    return {"id": user.id, "name": user.name, "email": user.email, "is_suspended": user.is_suspended}


def _activity_for(officer_ids):
    """Municipality-wide activity per Officer (never ward-limited)."""
    if not officer_ids:
        return {}
    ids = list(officer_ids)
    updates = dict(db.session.query(IssueWorkUpdate.officer_id, func.count(IssueWorkUpdate.id)).filter(
        IssueWorkUpdate.officer_id.in_(ids)).group_by(IssueWorkUpdate.officer_id).all())
    reviews = {}
    for who, state, count in db.session.query(
            ResolutionReview.submitted_by, ResolutionReview.state, func.count(ResolutionReview.id)).filter(
            ResolutionReview.submitted_by.in_(ids)).group_by(ResolutionReview.submitted_by, ResolutionReview.state).all():
        reviews.setdefault(who, {})[state] = count
    return {
        oid: {
            "work_updates": updates.get(oid, 0),
            "reviews_submitted": sum(reviews.get(oid, {}).values()),
            "reviews_approved": reviews.get(oid, {}).get("Approved", 0),
            "reviews_rejected": reviews.get(oid, {}).get("Rejected", 0),
        }
        for oid in ids
    }


def ward_detail(ward):
    """A ward's assignment record, read-only.  Admin notes on assignments (who
    assigned, reasons) are deliberately left out.  Activity shown for each
    Officer is municipality-wide: an assignment does not tie their work to the
    ward, and complaints/issues have no ward link."""
    rows = WardOfficerAssignment.query.filter_by(ward_id=ward.id).order_by(
        WardOfficerAssignment.assigned_at.desc(), WardOfficerAssignment.id.desc()).all()
    active_ids = {row.officer_id for row in rows if row.ended_at is None}
    activity = _activity_for(active_ids)
    return {
        "ward": {"id": ward.id, "name": ward.name, "code": ward.code, "is_active": ward.is_active,
                 "deactivated_at": to_iso8601(ward.deactivated_at)},
        "assignments": [
            {
                "id": row.id,
                "officer": {**_user_brief(row.officer), "role": row.officer.role},
                "assigned_at": to_iso8601(row.assigned_at),
                "ended_at": to_iso8601(row.ended_at),
                "is_active": row.ended_at is None,
            }
            for row in rows
        ],
        "active_officer_activity": {str(oid): counts for oid, counts in activity.items()},
        "note": "Activity is each Officer's municipality-wide total, not work done in this ward. "
                "Issues and complaints are not linked to wards, so no ward-level work figure exists.",
    }


def officer_detail(officer, state=None, limit=50, offset=0):
    """Everything the Chief Officer may see about one Officer, from reliable records."""
    assignments = WardOfficerAssignment.query.filter_by(officer_id=officer.id).order_by(
        WardOfficerAssignment.assigned_at.desc(), WardOfficerAssignment.id.desc()).all()
    reviews_q = ResolutionReview.query.filter_by(submitted_by=officer.id)
    state_counts = dict(db.session.query(ResolutionReview.state, func.count(ResolutionReview.id)).filter(
        ResolutionReview.submitted_by == officer.id).group_by(ResolutionReview.state).all())
    stale_waiting = [r for r in stale_reviews_awaiting_resubmission() if r.submitted_by == officer.id]
    distinct_review_issues = db.session.query(func.count(func.distinct(ResolutionReview.issue_id))).filter(
        ResolutionReview.submitted_by == officer.id).scalar() or 0
    updates = IssueWorkUpdate.query.filter_by(officer_id=officer.id)
    distinct_update_issues = db.session.query(func.count(func.distinct(IssueWorkUpdate.issue_id))).filter(
        IssueWorkUpdate.officer_id == officer.id).scalar() or 0

    listing = reviews_q
    if state:
        listing = listing.filter(ResolutionReview.state == state)
    total = listing.count()
    page = listing.order_by(ResolutionReview.submitted_at.desc(), ResolutionReview.id.desc()).offset(offset).limit(limit).all()
    ids = [r.id for r in page]
    ratings = {r.resolution_review_id: r for r in effective_ratings_query().filter(
        ResolutionRating.resolution_review_id.in_(ids)).all()} if ids else {}
    cases = {f.resolution_review_id: f for f in ResolutionFollowUp.query.filter(
        ResolutionFollowUp.resolution_review_id.in_(ids)).all()} if ids else {}

    stars_rows = dict(db.session.query(ResolutionRating.stars, func.count(ResolutionRating.id)).filter(
        ResolutionRating.rated_officer_id == officer.id,
        ResolutionRating.id.in_(effective_ratings_query().with_entities(ResolutionRating.id))).group_by(
        ResolutionRating.stars).all())
    follow_rows = db.session.query(ResolutionFollowUp.status, func.count(ResolutionFollowUp.id)).join(
        ResolutionReview, ResolutionReview.id == ResolutionFollowUp.resolution_review_id).filter(
        ResolutionReview.submitted_by == officer.id).group_by(ResolutionFollowUp.status).all()
    assigned_rows = db.session.query(ResolutionFollowUp.status, func.count(ResolutionFollowUp.id)).filter(
        ResolutionFollowUp.assigned_officer_id == officer.id).group_by(ResolutionFollowUp.status).all()

    return {
        "officer": {**_user_brief(officer), "role": officer.role},
        "wards": [
            {"ward_id": row.ward_id, "name": row.ward.name, "code": row.ward.code,
             "ward_is_active": row.ward.is_active, "assigned_at": to_iso8601(row.assigned_at),
             "ended_at": to_iso8601(row.ended_at), "is_active": row.ended_at is None}
            for row in assignments
        ],
        "work": {
            "work_updates": updates.count(),
            "issues_with_work_updates": distinct_update_issues,
            "review_submissions": sum(state_counts.values()),
            "issues_with_review_submissions": distinct_review_issues,
            "approved": state_counts.get("Approved", 0),
            "rejected": state_counts.get("Rejected", 0),
            "pending_decision": state_counts.get("Pending", 0),
            "stale_awaiting_resubmission": len(stale_waiting),
            "stale_total": state_counts.get("Stale", 0),
            "superseded": state_counts.get("Superseded", 0),
            "note": "Submissions are activity, not unique issues or caseload.",
        },
        "ratings": {
            "effective_total": sum(stars_rows.values()),
            "low_total": sum(c for st, c in stars_rows.items() if st <= LOW_RATING_MAX),
            "by_stars": {str(st): stars_rows.get(st, 0) for st in range(1, 6)},
        },
        "follow_ups": {
            "on_this_officers_work": _zero_filled(follow_rows, FOLLOW_UP_STATES),
            "assigned_to_this_officer": _zero_filled(assigned_rows, FOLLOW_UP_STATES),
        },
        "submissions": {
            "total": total, "limit": limit, "offset": offset,
            "items": [
                {
                    "resolution_review_id": review.id,
                    "issue": issue_brief(review.issue),
                    "state": review.state,
                    "submitted_at": to_iso8601(review.submitted_at),
                    "reviewed_at": to_iso8601(review.reviewed_at),
                    "stale_at": to_iso8601(review.stale_at),
                    "supersedes_review_id": review.supersedes_review_id,
                    "rating": ({"id": ratings[review.id].id, "stars": ratings[review.id].stars}
                               if review.id in ratings else None),
                    "follow_up": ({"id": cases[review.id].id, "status": cases[review.id].status}
                                  if review.id in cases else None),
                }
                for review in page
            ],
        },
    }
