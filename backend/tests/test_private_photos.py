"""Staff-only photos: field-work updates and completion evidence are private, citizen complaint photos are not.

Rules under test
* New field-work and completion photos are stored in the private folder, never the public one.
* ``/uploads`` refuses any file that a staff record refers to, but still serves complaint photos.
* Staff (Officer, Admin, Chief Officer) read field-work and completion photos in any review state.
* A citizen sees the completion photo only through the complaint's evidence endpoint, and only for an
  approved review of an issue that is Resolved and a report that took part in the resolution.
* Photos uploaded before this change (still in the public folder) keep working through the endpoints.
"""

import os
import shutil
import sqlite3

import pytest

from database.db import db
from models.performance import ResolutionFollowUp  # noqa: F401  (ensures tables are registered)
from models.notification import Notification
from models.resolution_review import ResolutionReview
from models.work_update import IssueWorkUpdate
from tests.helpers import JPEG_BYTES
from tests.test_resolution_workflow import auth, create_complaint, image, submit_review, token


@pytest.fixture
def who(client, citizen_user, officer_user, admin_user, chief_officer_user):
    other = client.post("/api/auth/register", json={"name": "Other", "email": "other@example.com", "password": "password123"})
    return {
        "citizen": token(client, "citizen@example.com", "password123"),
        "other": other.get_json()["token"],
        "officer": token(client, "officer@example.com", "officer123"),
        "admin": token(client, "admin@example.com", "admin123"),
        "chief": token(client, "chief@example.com", "chief123"),
    }


def private_dir(client):
    return client.application.config["PRIVATE_UPLOAD_FOLDER"]


def public_dir(client):
    return client.application.config["UPLOAD_FOLDER"]


def decide(client, who, review_id, decision, reason=None):
    body = {"decision": decision}
    if reason:
        body["rejection_reason"] = reason
    return client.put(f"/api/chief-officer/resolution-reviews/{review_id}/decision", json=body, headers=auth(who["chief"]))


def work_update_with_photo(client, who, issue_id, key="k1"):
    response = client.post(
        f"/api/issues/{issue_id}/work-updates",
        data={"note": "Crew inspected the site", "status": "Pending", "image": image("progress.jpg")},
        content_type="multipart/form-data", headers=auth(who["officer"], key),
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["work_update"]


def stored(model, row_id):
    db.session.expire_all()
    return db.session.get(model, row_id).image_filename


def snapshot(client):
    db.session.expire_all()
    return (ResolutionReview.query.count(), IssueWorkUpdate.query.count(), Notification.query.count(),
            sorted(r.state for r in ResolutionReview.query.all()))


def job_with_field_work(client, who):
    """Field work is recorded before the review is submitted: new field work withdraws a pending review."""
    complaint = create_complaint(client, who["citizen"])
    update = work_update_with_photo(client, who, complaint["civic_issue"]["id"])
    review = submit_review(client, who["officer"], complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]
    return complaint, review, update


def job(client, who):
    complaint = create_complaint(client, who["citizen"])
    review = submit_review(client, who["officer"], complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"]
    return complaint, review


# ---------------------------------------------------------------- storage and /uploads

def test_new_staff_photos_are_stored_privately_and_not_served_by_uploads(client, who):
    complaint, review = job(client, who)
    update = work_update_with_photo(client, who, complaint["civic_issue"]["id"])
    update_file, review_file = stored(IssueWorkUpdate, update["id"]), stored(ResolutionReview, review["id"])
    for name in (update_file, review_file):
        assert os.path.isfile(os.path.join(private_dir(client), name))
        assert not os.path.exists(os.path.join(public_dir(client), name))
        assert client.get(f"/uploads/{name}").status_code == 404
    # No public URL for either photo appears in any API payload.
    for response in (
        client.get(f"/api/issues/{complaint['civic_issue']['id']}/work-updates", headers=auth(who["officer"])),
        client.get(f"/api/issues/{complaint['civic_issue']['id']}/resolution-reviews", headers=auth(who["officer"])),
        client.get("/api/chief-officer/resolution-queue", headers=auth(who["chief"])),
    ):
        raw = response.get_data(as_text=True)
        assert update_file not in raw and review_file not in raw and "/uploads/" not in raw.replace(complaint["image_url"], "")


def test_citizen_complaint_photos_stay_public(client, who):
    complaint, _ = job(client, who)
    response = client.get(complaint["image_url"])
    assert response.status_code == 200 and response.data == JPEG_BYTES
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_uploads_refuses_a_legacy_file_that_a_staff_record_refers_to_without_touching_it(client, who):
    complaint, review = job(client, who)
    name = stored(ResolutionReview, review["id"])
    legacy = os.path.join(public_dir(client), name)
    shutil.move(os.path.join(private_dir(client), name), legacy)  # simulate a photo uploaded before this change
    assert client.get(f"/uploads/{name}").status_code == 404
    assert os.path.isfile(legacy)  # refused, not removed or moved


# ---------------------------------------------------------------- staff endpoints

def test_staff_can_read_field_work_photos_and_everyone_else_cannot(client, who):
    complaint, _ = job(client, who)
    issue_id = complaint["civic_issue"]["id"]
    update = work_update_with_photo(client, who, issue_id)
    url = f"/api/issues/{issue_id}/work-updates/{update['id']}/image"
    for role in ("officer", "admin", "chief"):
        response = client.get(url, headers=auth(who[role]))
        assert response.status_code == 200 and response.data == JPEG_BYTES, role
        assert response.headers["X-Content-Type-Options"] == "nosniff" and "no-store" in response.headers["Cache-Control"]
    assert client.get(url).status_code == 401
    for role in ("citizen", "other"):
        denied = client.get(url, headers=auth(who[role]))
        assert denied.status_code == 403 and JPEG_BYTES not in denied.data, role
    assert client.get(f"/api/issues/{issue_id + 99}/work-updates/{update['id']}/image", headers=auth(who["officer"])).status_code == 404
    assert client.get(f"/api/issues/{issue_id}/work-updates/{update['id'] + 99}/image", headers=auth(who["officer"])).status_code == 404


def test_a_work_update_without_a_photo_has_no_image_and_a_404(client, who):
    complaint, _ = job(client, who)
    issue_id = complaint["civic_issue"]["id"]
    response = client.post(f"/api/issues/{issue_id}/work-updates", data={"note": "No photo"},
                           content_type="multipart/form-data", headers=auth(who["officer"], "nokey"))
    update = response.get_json()["work_update"]
    assert update["image_path"] is None
    assert client.get(f"/api/issues/{issue_id}/work-updates/{update['id']}/image", headers=auth(who["officer"])).status_code == 404


def completion_url(issue_id, review_id):
    return f"/api/issues/{issue_id}/resolution-reviews/{review_id}/image"


def test_completion_photo_staff_route_works_in_every_review_state_and_never_for_citizens(client, who):
    complaint, pending = job(client, who)
    issue_id = complaint["civic_issue"]["id"]
    seen = {}

    def check(label, review_id):
        seen[label] = review_id
        for role in ("officer", "admin", "chief"):
            response = client.get(completion_url(issue_id, review_id), headers=auth(who[role]))
            assert response.status_code == 200 and response.data == JPEG_BYTES, (label, role)
        for role in ("citizen", "other"):
            assert client.get(completion_url(issue_id, review_id), headers=auth(who[role])).status_code == 403, (label, role)
        assert client.get(completion_url(issue_id, review_id)).status_code == 401, label

    check("pending", pending["id"])
    assert decide(client, who, pending["id"], "Rejected", "The photo does not show the repaired area.").status_code == 200
    check("rejected", pending["id"])
    second = submit_review(client, who["officer"], issue_id, [complaint["id"]], supersedes_review_id=str(pending["id"])).get_json()["review"]
    assert second["supersedes_review_id"] == pending["id"]
    check("pending replacement", second["id"])
    # A new report joining the issue withdraws the pending review (Stale); staff can still see its photo.
    create_complaint(client, who["other"], latitude="20.0111", longitude="73.7901", title="Another report")
    db.session.expire_all()
    assert db.session.get(ResolutionReview, second["id"]).state == "Stale"
    check("stale", second["id"])
    # A stale review that is replaced stays Stale; its photo stays available to staff.
    refreshed = [c["id"] for c in client.get(f"/api/issues/{issue_id}/resolution-reviews", headers=auth(who["officer"])).get_json()["complaints"]]
    third = submit_review(client, who["officer"], issue_id, refreshed, supersedes_review_id=str(second["id"])).get_json()["review"]
    check("stale, replaced", second["id"])
    # An Officer replacing their own pending review marks the old one Superseded.
    fourth = submit_review(client, who["officer"], issue_id, refreshed, supersedes_review_id=str(third["id"])).get_json()["review"]
    db.session.expire_all()
    assert db.session.get(ResolutionReview, third["id"]).state == "Superseded"
    check("superseded", third["id"])
    check("latest pending", fourth["id"])


def test_completion_photo_route_rejects_a_review_from_another_issue_and_missing_files(client, who):
    complaint, review = job(client, who)
    issue_id = complaint["civic_issue"]["id"]
    assert client.get(completion_url(issue_id + 50, review["id"]), headers=auth(who["officer"])).status_code == 404
    assert client.get(completion_url(issue_id, review["id"] + 50), headers=auth(who["officer"])).status_code == 404
    os.remove(os.path.join(private_dir(client), stored(ResolutionReview, review["id"])))
    assert client.get(completion_url(issue_id, review["id"]), headers=auth(who["officer"])).status_code == 404


# ---------------------------------------------------------------- citizen evidence

def after_url(complaint_id):
    return f"/api/complaints/{complaint_id}/resolution-evidence/after-image"


def test_a_citizen_sees_the_completion_photo_only_after_approval(client, who):
    complaint, review = job(client, who)
    reporter = who["citizen"]
    # Pending: nothing.
    assert client.get(after_url(complaint["id"]), headers=auth(reporter)).status_code == 404
    # Rejected: nothing.
    assert decide(client, who, review["id"], "Rejected", "The photo does not show the repaired area.").status_code == 200
    assert client.get(after_url(complaint["id"]), headers=auth(reporter)).status_code == 404
    # Resubmitted and still pending: nothing.
    again = submit_review(client, who["officer"], complaint["civic_issue"]["id"], [complaint["id"]],
                          supersedes_review_id=str(review["id"])).get_json()["review"]
    assert client.get(after_url(complaint["id"]), headers=auth(reporter)).status_code == 404
    # Approved: the reporter gets it.
    assert decide(client, who, again["id"], "Approved").status_code == 200
    photo = client.get(after_url(complaint["id"]), headers=auth(reporter))
    assert photo.status_code == 200 and photo.data == JPEG_BYTES
    assert photo.headers["X-Content-Type-Options"] == "nosniff" and "no-store" in photo.headers["Cache-Control"]
    # The photo served is the approved review's, not the rejected one's.
    with open(os.path.join(private_dir(client), stored(ResolutionReview, again["id"])), "rb") as handle:
        assert photo.data == handle.read()


def test_approved_completion_photo_is_not_available_to_other_citizens_or_anonymous_users(client, who):
    complaint, review = job(client, who)
    assert decide(client, who, review["id"], "Approved").status_code == 200
    assert client.get(after_url(complaint["id"])).status_code == 401
    unrelated = client.get(after_url(complaint["id"]), headers=auth(who["other"]))
    assert unrelated.status_code == 404 and JPEG_BYTES not in unrelated.data
    # Chief Officers use the staff route; the citizen route follows the complaint access rule.
    assert client.get(after_url(complaint["id"]), headers=auth(who["chief"])).status_code == 404
    assert client.get(completion_url(complaint["civic_issue"]["id"], review["id"]), headers=auth(who["chief"])).status_code == 200
    for role in ("officer", "admin"):
        assert client.get(after_url(complaint["id"]), headers=auth(who[role])).status_code == 200, role


def test_a_reopened_issue_and_an_excluded_report_do_not_get_the_photo(client, who):
    complaint, review = job(client, who)
    other_report = create_complaint(client, who["other"], latitude="20.0111", longitude="73.7901", title="Society light")
    assert other_report["civic_issue"]["id"] == complaint["civic_issue"]["id"]
    assert client.put(f"/api/complaints/{other_report['id']}/reject", json={"reason": "Private Property"},
                      headers=auth(who["officer"])).status_code == 200
    review = submit_review(client, who["officer"], complaint["civic_issue"]["id"], [complaint["id"]]).get_json()["review"] \
        if ResolutionReview.query.get(review["id"]).state != "Pending" else review
    assert decide(client, who, review["id"], "Approved").status_code == 200
    assert client.get(after_url(complaint["id"]), headers=auth(who["citizen"])).status_code == 200
    # The report that was excluded as out of scope took no part in the resolution.
    assert client.get(after_url(other_report["id"]), headers=auth(who["other"])).status_code == 404
    # Reopening the issue withdraws the old photo as proof.
    from models.civic_issue import CivicIssue
    issue = db.session.get(CivicIssue, complaint["civic_issue"]["id"])
    issue.status = "In Progress"
    db.session.commit()
    assert client.get(after_url(complaint["id"]), headers=auth(who["citizen"])).status_code == 404


def test_the_evidence_payload_gives_an_authenticated_path_not_a_public_url(client, who):
    complaint, review = job(client, who)
    assert decide(client, who, review["id"], "Approved").status_code == 200
    raw = client.get(f"/api/complaints/{complaint['id']}/resolution-evidence", headers=auth(who["citizen"])).get_data(as_text=True)
    name = stored(ResolutionReview, review["id"])
    assert name not in raw and f"/uploads/{name}" not in raw
    assert f'"image_path": "/complaints/{complaint["id"]}/resolution-evidence/after-image"' in raw.replace('":"', '": "')


# ---------------------------------------------------------------- legacy files, tampering, side effects

def test_photos_uploaded_before_the_change_keep_working_through_the_endpoints(client, who):
    complaint, review, update = job_with_field_work(client, who)
    issue_id = complaint["civic_issue"]["id"]
    assert decide(client, who, review["id"], "Approved").status_code == 200
    for model, row in ((ResolutionReview, review["id"]), (IssueWorkUpdate, update["id"])):
        name = stored(model, row)
        shutil.move(os.path.join(private_dir(client), name), os.path.join(public_dir(client), name))
    assert client.get(completion_url(issue_id, review["id"]), headers=auth(who["officer"])).status_code == 200
    assert client.get(f"/api/issues/{issue_id}/work-updates/{update['id']}/image", headers=auth(who["officer"])).status_code == 200
    assert client.get(after_url(complaint["id"]), headers=auth(who["citizen"])).status_code == 200
    # ...and they are still not reachable through the public route.
    assert client.get(f"/uploads/{stored(ResolutionReview, review['id'])}").status_code == 404


@pytest.mark.parametrize("hostile", ["../secret.jpg", "/etc/passwd.jpg", "..\\secret.jpg", ".hidden.jpg", "x.html", "x.svg", "dir/../photo.jpg", ""])
def test_a_corrupted_stored_file_name_is_never_served(client, who, tmp_path, hostile):
    complaint, review = job(client, who)
    issue_id = complaint["civic_issue"]["id"]
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(JPEG_BYTES + b"-OUTSIDE")
    db_path = client.application.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE resolution_reviews SET image_filename = ? WHERE id = ?", (hostile, review["id"]))
        conn.commit()
    finally:
        conn.close()
    db.session.expire_all()
    response = client.get(completion_url(issue_id, review["id"]), headers=auth(who["officer"]))
    assert response.status_code == 404 and b"-OUTSIDE" not in response.data


def test_reading_private_photos_changes_nothing(client, who):
    complaint, review, update = job_with_field_work(client, who)
    issue_id = complaint["civic_issue"]["id"]
    assert decide(client, who, review["id"], "Approved").status_code == 200
    before = snapshot(client)
    for _ in range(2):
        client.get(completion_url(issue_id, review["id"]), headers=auth(who["chief"]))
        client.get(f"/api/issues/{issue_id}/work-updates/{update['id']}/image", headers=auth(who["officer"]))
        client.get(after_url(complaint["id"]), headers=auth(who["citizen"]))
        client.get(after_url(complaint["id"]), headers=auth(who["other"]))
    assert snapshot(client) == before
