"""
Lightweight duplicate/same-issue correlation.

This is a "likely same issue" signal, not a source of truth. It only ever
attaches a complaint to a CivicIssue (or creates a new one) - it never
flags, rejects, punishes, suspends, or deletes anything, and it must never
touch a user's spam_count. Spam determination stays a fully separate,
human-reviewed process.

Deliberately dependency-free (haversine distance + stdlib text similarity)
to stay within the project's "no unnecessary frameworks" constraint.
"""

import math
from datetime import timedelta
from difflib import SequenceMatcher

from database.db import db
from models.civic_issue import CivicIssue
from utils.time_helper import utc_now

MATCH_RADIUS_METERS = 150
MATCH_RECENCY_DAYS = 30
MIN_TEXT_SIMILARITY = 0.2

EARTH_RADIUS_METERS = 6371000


def haversine_distance_meters(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


def text_similarity(text_a, text_b):
    return SequenceMatcher(None, (text_a or "").strip().lower(), (text_b or "").strip().lower()).ratio()


def find_matching_issue(category, latitude, longitude, ai_summary, description):
    """Returns the best-matching open CivicIssue for a new complaint, or
    None if nothing correlates closely enough. Combines multiple signals
    (location proximity, category, recency, text similarity) rather than
    relying on any single one."""

    cutoff = utc_now() - timedelta(days=MATCH_RECENCY_DAYS)

    candidates = CivicIssue.query.filter(
        CivicIssue.category == category,
        CivicIssue.status != "Resolved",
        CivicIssue.created_at >= cutoff,
    ).all()

    reference_text = ai_summary or description or ""

    best_match = None
    best_score = 0.0

    for issue in candidates:
        distance = haversine_distance_meters(
            latitude, longitude, issue.latitude, issue.longitude
        )

        if distance > MATCH_RADIUS_METERS:
            continue

        similarity = text_similarity(reference_text, issue.ai_summary)

        if similarity < MIN_TEXT_SIMILARITY:
            continue

        # Closer + more textually similar = stronger correlation. Distance
        # is normalized against the radius so both signals contribute on
        # a comparable 0-1 scale.
        proximity_score = 1 - (distance / MATCH_RADIUS_METERS)
        score = (proximity_score * 0.5) + (similarity * 0.5)

        if score > best_score:
            best_score = score
            best_match = issue

    return best_match


def get_or_create_issue_for_complaint(category, latitude, longitude, ai_summary, description, location_label):
    """Finds a matching CivicIssue for a new complaint (creating one if no
    good match exists) and returns it, with report_count already updated.
    The caller is responsible for setting complaint.issue_id from the
    returned issue (flushing first if it's newly created, to get an id)."""

    matched_issue = find_matching_issue(
        category, latitude, longitude, ai_summary, description
    )

    if matched_issue:
        matched_issue.report_count += 1
        return matched_issue

    new_issue = CivicIssue(
        category=category,
        location_label=location_label,
        latitude=latitude,
        longitude=longitude,
        ai_summary=ai_summary,
        report_count=1,
    )
    db.session.add(new_issue)
    return new_issue
