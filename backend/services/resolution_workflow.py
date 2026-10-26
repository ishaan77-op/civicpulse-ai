"""Shared state transitions for issue-wide field work and final review."""

import os

from sqlalchemy import func, update

from models.civic_issue import CivicIssue
from models.complaint import Complaint
from models.community import CivicIssueStatusChange
from models.resolution_review import ResolutionReview
from database.db import db
from services import community_service as community
from services import impact_score_service as impact
from utils.time_helper import to_iso8601, utc_now


ELIGIBLE_SPAM_STATES = ("NotFlagged", "Rejected")
NO_ELIGIBLE_COMPLAINTS_MESSAGE = (
    "This issue has no eligible complaints to resolve; every linked complaint "
    "was excluded as spam or out of scope"
)


class WorkflowError(ValueError):
    """A workflow rule violation with a client-safe message."""


class StaleReviewError(WorkflowError):
    """The review no longer matches the issue.  Unlike other workflow errors
    the caller must commit: the review's Stale marking is part of the result."""


def eligible_complaints(issue_id):
    return Complaint.query.filter(
        Complaint.issue_id == issue_id,
        Complaint.spam_review_status.in_(ELIGIBLE_SPAM_STATES),
        Complaint.rejection_status != "Rejected",
    ).order_by(Complaint.id.asc()).all()


def moderation_pending_complaints(issue_id):
    return Complaint.query.filter(
        Complaint.issue_id == issue_id,
        Complaint.spam_review_status == "Pending",
    ).order_by(Complaint.id.asc()).all()


def excluded_complaints(issue_id):
    rows = Complaint.query.filter(Complaint.issue_id == issue_id).order_by(
        Complaint.id.asc()
    ).all()
    excluded = []
    for complaint in rows:
        if complaint.spam_review_status == "Confirmed":
            excluded.append((complaint, "Confirmed spam"))
        elif complaint.rejection_status == "Rejected":
            excluded.append((complaint, "Out of scope"))
    return excluded


def ensure_issue_complaint(issue_id, complaint_id):
    complaint = Complaint.query.filter_by(id=complaint_id, issue_id=issue_id).first()
    if not complaint:
        raise WorkflowError("The complaint does not belong to this civic issue")
    return complaint


def stale_reviews_awaiting_resubmission():
    """Stale reviews the Chief Officer should still see.

    A review going stale does not move the issue out of ``Pending Review``, so
    the issue would otherwise vanish from the queue while still showing that
    status.  Only the latest review of an issue counts: once the officer
    resubmits (or returns the issue to field work) the stale one is history.
    """
    latest_ids = db.session.query(func.max(ResolutionReview.id)).group_by(
        ResolutionReview.issue_id
    )
    return ResolutionReview.query.join(
        CivicIssue, ResolutionReview.issue_id == CivicIssue.id
    ).filter(
        ResolutionReview.state == "Stale",
        ResolutionReview.id.in_(latest_ids),
        CivicIssue.status == "Pending Review",
    ).order_by(ResolutionReview.stale_at.asc(), ResolutionReview.id.asc()).all()


def mark_pending_reviews_stale(issue, reason):
    """Keep the original review and evidence; only change its audit state.

    The transition is conditional on the review still being Pending, so it can
    never overwrite a decision committed by a concurrent request.
    """
    ResolutionReview.query.filter_by(issue_id=issue.id, state="Pending").update({
        "state": "Stale",
        "stale_reason": reason,
        "stale_at": utc_now(),
    })


def bump_review_revision(issue, reason):
    """Invalidate all pending review snapshots inside the caller transaction.

    The increment is a single SQL statement, not a read-modify-write of the
    in-memory value, so concurrent bumps cannot overwrite each other.  Running
    it first also takes the database write lock before the Pending reviews are
    read and staled.
    """
    db.session.execute(
        update(CivicIssue)
        .where(CivicIssue.id == issue.id)
        .values(review_revision=CivicIssue.review_revision + 1)
    )
    db.session.refresh(issue, ["review_revision"])
    mark_pending_reviews_stale(issue, reason)


def lock_issue_at_revision(issue_id, revision):
    """Take the write lock and check, atomically, that the issue is unchanged.

    SQLite has no row locks and a plain SELECT does not start a write
    transaction, so facts read before the first write can be outdated by the
    time the transaction commits.  This no-op UPDATE both acquires the write
    lock (on SQLite, the database's single writer; elsewhere, the row lock)
    and only matches while ``review_revision`` equals ``revision``.  Every
    change that affects a review bumps the revision, so after this returns
    True nothing can change the issue until the caller commits or rolls back.
    """
    matched = CivicIssue.query.filter(
        CivicIssue.id == issue_id, CivicIssue.review_revision == revision
    ).update(
        {CivicIssue.review_revision: CivicIssue.review_revision},
        synchronize_session=False,
    )
    return matched == 1


def change_issue_status(issue, new_status, changed_by):
    """Apply an official issue status change and its existing side effects.

    The caller remains responsible for committing, so status history,
    notifications, rewards, and review decisions succeed or fail together.
    """
    old_status = issue.status
    if old_status == new_status:
        return False

    issue.status = new_status
    db.session.add(CivicIssueStatusChange(
        civic_issue_id=issue.id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
    ))
    if new_status == "Resolved":
        impact.on_issue_resolved(issue)
    community.notify_issue_status_changed(issue, new_status)
    return True


def validate_review_coverage(issue, review):
    pending_moderation = moderation_pending_complaints(issue.id)
    if pending_moderation:
        raise WorkflowError(
            "Final review is blocked while linked complaints await spam moderation"
        )

    eligible = eligible_complaints(issue.id)
    if not eligible:
        raise WorkflowError(NO_ELIGIBLE_COMPLAINTS_MESSAGE)
    eligible_ids = {complaint.id for complaint in eligible}
    dispositions = review.complaint_dispositions
    disposition_ids = {row.complaint_id for row in dispositions}
    if disposition_ids != eligible_ids:
        raise WorkflowError(
            "The review must account for every eligible complaint linked to this issue"
        )
    for disposition in dispositions:
        if disposition.disposition not in ("Addressed", "Duplicate Covered"):
            raise WorkflowError(
                "A review with additional work required cannot be approved"
            )
        ensure_issue_complaint(issue.id, disposition.complaint_id)
    return eligible


def approve_review(issue, review, chief_officer_id):
    """Atomically prepare an issue-wide approval in the current transaction.

    The write lock is taken before anything is validated, so the eligibility
    that is checked is the eligibility that gets resolved.  The caller
    commits on success and on StaleReviewError, and rolls back otherwise.
    """
    if not lock_issue_at_revision(issue.id, review.issue_revision):
        ResolutionReview.query.filter_by(id=review.id, state="Pending").update({
            "state": "Stale",
            "stale_reason": "Issue information changed after review submission",
            "stale_at": utc_now(),
        })
        raise StaleReviewError("This review is stale and cannot be approved")

    # Drop anything loaded before the lock; every read from here is current.
    db.session.expire_all()
    eligible = validate_review_coverage(issue, review)

    # The conditional transition makes a duplicate/retried decision harmless.
    transitioned = ResolutionReview.query.filter_by(
        id=review.id, state="Pending"
    ).update({
        "state": "Approved",
        "reviewed_by": chief_officer_id,
        "reviewed_at": utc_now(),
        "rejection_reason": None,
    }, synchronize_session=False)
    if transitioned != 1:
        raise WorkflowError("This review has already been decided")

    for complaint in eligible:
        complaint.status = "Resolved"
    change_issue_status(issue, "Resolved", chief_officer_id)
    return eligible


# ==========================================
# Citizen-safe view of a complaint's resolution progress
# ==========================================

# Internal review state -> what a citizen is told.  A Stale review is one the
# officer must redo, so to the citizen the work is still awaiting verification.
CITIZEN_REVIEW_STATES = {
    "Pending": "awaiting_review",
    "Stale": "awaiting_review",
    "Superseded": "awaiting_review",
    "Rejected": "returned",
    "Approved": "approved",
}


def _upload_url_if_present(filename, upload_folder):
    """URL for a stored upload, or None if there is no usable file.

    Names come from our own database, but they are still confined to a bare
    file name inside the upload folder before being checked or linked.
    """
    if not filename or os.path.basename(filename) != filename:
        return None
    if not os.path.isfile(os.path.join(upload_folder, filename)):
        return None
    return f"/uploads/{filename}"


def citizen_resolution_view(complaint, upload_folder):
    """The only resolution data a citizen may see about their complaint.

    This is an allow-list, not a filtered staff payload.  Completion evidence
    (photo and report) appears only for an *approved* review of an issue that
    is currently Resolved.  Pending, stale and returned work is reported by
    status and date alone: no photo, note, rejection reason, disposition,
    GPS, or staff identity ever leaves this function.  The original report
    photo is always taken from the complaint itself and never replaced.
    """
    issue = complaint.issue
    eligible = (
        complaint.spam_review_status in ELIGIBLE_SPAM_STATES
        and complaint.rejection_status != "Rejected"
    )
    view = {
        "complaint_id": complaint.id,
        "state": "none",
        "issue_status": issue.status if issue else None,
        "before": {
            "image_url": _upload_url_if_present(complaint.image_filename, upload_folder),
            "reported_at": to_iso8601(complaint.created_at),
        },
        "work_submitted_at": None,
        "returned_at": None,
        "approved_at": None,
        "after": None,
    }
    if not issue:
        return view
    if not eligible:
        # Held for moderation, or excluded as spam / out of scope: this report
        # was not part of any resolution, so none of the issue's work is shown.
        view["state"] = "not_applicable"
        return view

    latest = ResolutionReview.query.filter_by(issue_id=issue.id).order_by(
        ResolutionReview.id.desc()
    ).first()
    if not latest:
        return view

    state = CITIZEN_REVIEW_STATES.get(latest.state, "awaiting_review")
    if state == "approved":
        if issue.status != "Resolved":
            # Reopened since approval: the old photo is no longer proof of
            # the current state.
            return view
        view["state"] = "approved"
        view["work_submitted_at"] = to_iso8601(latest.submitted_at)
        view["approved_at"] = to_iso8601(latest.reviewed_at)
        view["after"] = {
            "image_url": _upload_url_if_present(latest.image_filename, upload_folder),
            "report": latest.completion_note,
        }
        return view

    view["state"] = state
    view["work_submitted_at"] = to_iso8601(latest.submitted_at)
    if state == "returned":
        view["returned_at"] = to_iso8601(latest.reviewed_at)
    return view
