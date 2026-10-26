"""scripts/private_photo_migration.py on disposable fixtures: classify, copy, verify, quarantine, restore."""

import hashlib
import os
import shutil
import sqlite3

import pytest

from database.db import db
from models.resolution_review import ResolutionReview
from models.work_update import IssueWorkUpdate
from scripts import private_photo_migration as mig
from tests.test_resolution_workflow import auth, create_complaint, image, submit_review, token


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.fixture
def legacy(client, citizen_user, officer_user, chief_officer_user, tmp_path):
    """A database whose staff photos all sit in the public folder, as before photos became private."""
    citizen = token(client, "citizen@example.com", "password123")
    officer = token(client, "officer@example.com", "officer123")
    public, app_private = client.application.config["UPLOAD_FOLDER"], client.application.config["PRIVATE_UPLOAD_FOLDER"]
    private = str(tmp_path / "private")  # a fresh private folder: the app's own is shared by the whole test session
    complaint = create_complaint(client, citizen)
    issue_id = complaint["civic_issue"]["id"]
    client.post(f"/api/issues/{issue_id}/work-updates", data={"note": "Inspecting", "status": "Pending", "image": image("a.jpg")},
                content_type="multipart/form-data", headers=auth(officer, "k1"))
    review = submit_review(client, officer, issue_id, [complaint["id"]]).get_json()["review"]
    db.session.expire_all()
    names = {
        "update": IssueWorkUpdate.query.first().image_filename,
        "review": db.session.get(ResolutionReview, review["id"]).image_filename,
    }
    for name in names.values():  # move to the public folder: the legacy layout
        shutil.move(os.path.join(app_private, name), os.path.join(public, name))
    return {
        "db": client.application.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", ""),
        "public": public, "private": private, "quarantine": str(tmp_path / "quarantine"), "names": names,
        "complaint_photo": complaint["image_filename"],
    }


def run(legacy_env, command, *extra):
    args = [command, "--db", legacy_env["db"], "--public", legacy_env["public"], "--private", legacy_env["private"],
            "--quarantine", legacy_env["quarantine"], *extra]
    return mig.main(args)


def statuses(legacy_env):
    return {i["file"]: i["status"] for i in mig.classify(legacy_env["db"], legacy_env["public"], legacy_env["private"])}


def test_report_classifies_and_changes_nothing(legacy, capsys):
    before_db = digest(legacy["db"])
    before_files = sorted(os.listdir(legacy["public"]))
    assert run(legacy, "report", "--manifest", legacy["db"] + ".manifest.json") == 0
    out = capsys.readouterr().out
    assert "public-only" in out and legacy["names"]["review"] in out
    assert all(s == "public-only" for s in statuses(legacy).values())
    assert sorted(os.listdir(legacy["public"])) == before_files
    assert not os.path.exists(legacy["private"]) or os.listdir(legacy["private"]) == []
    assert digest(legacy["db"]) == before_db
    assert os.path.getsize(legacy["db"] + ".manifest.json") > 0
    os.remove(legacy["db"] + ".manifest.json")


def test_copy_is_a_dry_run_unless_applied_and_never_removes_the_originals(legacy):
    assert run(legacy, "copy") == 0  # dry run
    assert not os.path.exists(legacy["private"]) or os.listdir(legacy["private"]) == []
    assert run(legacy, "copy", "--apply") == 0
    for name in legacy["names"].values():
        assert digest(os.path.join(legacy["public"], name)) == digest(os.path.join(legacy["private"], name))
    assert set(statuses(legacy).values()) == {"both-identical"}
    assert run(legacy, "copy", "--apply") == 0  # idempotent: nothing left to do
    assert not [n for n in os.listdir(legacy["private"]) if n.endswith(".part")]


def test_verify_fails_until_files_are_copied_and_missing_files_are_only_fatal_in_strict_mode(legacy, capsys):
    assert run(legacy, "verify") == 1
    run(legacy, "copy", "--apply")
    assert run(legacy, "verify") == 0
    os.remove(os.path.join(legacy["public"], legacy["names"]["update"]))
    os.remove(os.path.join(legacy["private"], legacy["names"]["update"]))
    assert statuses(legacy)[legacy["names"]["update"]] == "missing"
    assert run(legacy, "verify") == 0 and "already missing" in capsys.readouterr().out
    assert run(legacy, "verify", "--strict") == 1


def test_a_differing_private_file_is_never_overwritten_and_blocks_quarantine(legacy):
    name = legacy["names"]["review"]
    os.makedirs(legacy["private"], exist_ok=True)
    with open(os.path.join(legacy["private"], name), "wb") as handle:
        handle.write(b"a different file")
    assert statuses(legacy)[name] == "both-different"
    assert run(legacy, "report") == 2
    run(legacy, "copy", "--apply")
    with open(os.path.join(legacy["private"], name), "rb") as handle:
        assert handle.read() == b"a different file"  # untouched
    assert run(legacy, "quarantine", "--apply") == 1
    assert os.path.isfile(os.path.join(legacy["public"], name))


def test_a_name_shared_with_a_public_complaint_photo_is_never_moved(legacy):
    conn = sqlite3.connect(legacy["db"])
    try:
        conn.execute("UPDATE issue_work_updates SET image_filename = ?", (legacy["complaint_photo"],))
        conn.commit()
    finally:
        conn.close()
    assert statuses(legacy)[legacy["complaint_photo"]] == "shared-with-complaint-photo"
    assert run(legacy, "report") == 2
    assert run(legacy, "copy", "--apply") == 0
    assert os.path.isfile(os.path.join(legacy["public"], legacy["complaint_photo"]))
    assert not os.path.exists(os.path.join(legacy["private"], legacy["complaint_photo"]))
    assert run(legacy, "quarantine", "--apply") == 1


def test_hostile_stored_names_are_reported_not_followed(legacy):
    conn = sqlite3.connect(legacy["db"])
    try:
        conn.execute("UPDATE resolution_reviews SET image_filename = '../../etc/passwd.jpg'")
        conn.commit()
    finally:
        conn.close()
    assert "unsafe-name" in statuses(legacy).values()
    assert run(legacy, "report") == 2
    assert run(legacy, "copy", "--apply") == 0


def test_quarantine_and_restore_are_a_reversible_round_trip_and_the_database_is_never_touched(legacy):
    db_hash = digest(legacy["db"])
    names = list(legacy["names"].values())
    assert run(legacy, "quarantine", "--apply") == 1  # nothing copied yet: refuses
    run(legacy, "copy", "--apply")
    assert run(legacy, "quarantine") == 0  # dry run
    assert all(os.path.isfile(os.path.join(legacy["public"], n)) for n in names)
    assert run(legacy, "quarantine", "--apply") == 0
    for name in names:
        assert not os.path.exists(os.path.join(legacy["public"], name))
        assert os.path.isfile(os.path.join(legacy["quarantine"], name))
        assert os.path.isfile(os.path.join(legacy["private"], name))
    assert set(statuses(legacy).values()) == {"private-only"}
    assert run(legacy, "verify") == 0
    assert os.path.isfile(os.path.join(legacy["public"], legacy["complaint_photo"]))  # citizen photo untouched
    assert run(legacy, "restore", "--apply") == 0  # rollback
    assert all(os.path.isfile(os.path.join(legacy["public"], n)) for n in names)
    assert os.listdir(legacy["quarantine"]) == []
    assert digest(legacy["db"]) == db_hash
