import os
from unittest.mock import patch

import pytest

from tests.helpers import JPEG_BYTES, fake_image, png_bytes

AI_OK = {
    "category": "Road Infrastructure",
    "priority": "High",
    "department": "Roads Dept",
    "visual_observation": "Pothole spotted",
    "summary": "Fix pothole",
}


def token_for(client):
    res = client.post(
        "/api/auth/login",
        json={"email": "citizen@example.com", "password": "password123"},
    )
    return res.get_json()["token"]


def post_complaint(client, token, image):
    return client.post(
        "/api/complaints/",
        data={
            "title": "Pothole",
            "description": "Deep hole",
            "latitude": "20.011",
            "longitude": "73.790",
            "image": image,
        },
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {token}"},
    )


def upload_listing(app):
    folder = app.config["UPLOAD_FOLDER"]
    return set(os.listdir(folder)) if os.path.isdir(folder) else set()


@patch("routes.complaints.analyze_complaint", return_value=AI_OK)
@pytest.mark.parametrize(
    "image",
    [
        fake_image("report-1700000000000.jpg"),  # what the camera component sends
        fake_image("photo.jpeg"),
        fake_image("PHOTO.JPG"),
        fake_image("shot.png", png_bytes()),
        fake_image("shot.webp", b"RIFF\x1a\x00\x00\x00WEBPVP8 "),
    ],
    ids=["camera-jpg", "jpeg", "upper-case-ext", "png", "webp"],
)
def test_valid_images_are_accepted(mock_ai, app, client, citizen_user, image):
    res = post_complaint(client, token_for(client), image)

    assert res.status_code == 201
    filename = res.get_json()["complaint"]["image_url"][len("/uploads/"):]
    assert os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    assert not filename.endswith(".part")


@patch("routes.complaints.analyze_complaint", return_value=AI_OK)
@pytest.mark.parametrize(
    "image",
    [
        fake_image("notes.jpg", b"this is not an image"),
        fake_image("script.exe", JPEG_BYTES),
        fake_image("noextension", JPEG_BYTES),
        fake_image("page.html", b"<html></html>"),
        fake_image("photo.png", JPEG_BYTES),  # content does not match extension
        fake_image("photo.jpg", b""),
    ],
    ids=["text-as-jpg", "exe", "no-extension", "html", "ext-mismatch", "empty"],
)
def test_invalid_uploads_are_rejected_and_leave_no_files(mock_ai, app, client, citizen_user, image):
    token = token_for(client)
    before = upload_listing(app)

    res = post_complaint(client, token, image)

    assert res.status_code == 400
    assert "message" in res.get_json()
    mock_ai.assert_not_called()  # rejected before any AI call or save
    assert upload_listing(app) == before


@patch("routes.complaints.analyze_complaint", return_value=AI_OK)
def test_oversized_upload_is_rejected_with_413(mock_ai, app, client, citizen_user):
    token = token_for(client)
    before = upload_listing(app)
    limit = 1024  # 1 KB for the test

    with patch.dict(app.config, {"MAX_UPLOAD_BYTES": limit, "MAX_CONTENT_LENGTH": limit * 1024}):
        res = post_complaint(client, token, fake_image("big.jpg", JPEG_BYTES + b"0" * (limit + 1)))

    assert res.status_code == 413
    assert "too large" in res.get_json()["message"].lower()
    mock_ai.assert_not_called()
    assert upload_listing(app) == before


@patch("routes.complaints.analyze_complaint", return_value=AI_OK)
def test_request_larger_than_hard_cap_is_rejected_with_413(mock_ai, app, client, citizen_user):
    token = token_for(client)
    before = upload_listing(app)

    with patch.dict(app.config, {"MAX_CONTENT_LENGTH": 2048}):
        res = post_complaint(client, token, fake_image("huge.jpg", JPEG_BYTES + b"0" * 10_000))

    assert res.status_code == 413
    mock_ai.assert_not_called()
    assert upload_listing(app) == before


@patch("routes.complaints.analyze_complaint", return_value=AI_OK)
def test_save_failure_leaves_no_partial_file(mock_ai, app, client, citizen_user):
    token = token_for(client)
    before = upload_listing(app)

    with patch("werkzeug.datastructures.FileStorage.save", side_effect=OSError("disk full")):
        res = post_complaint(client, token, fake_image())

    assert res.status_code == 500
    assert upload_listing(app) == before


@patch("routes.complaints.analyze_complaint", return_value=AI_OK)
def test_database_failure_removes_saved_photo(mock_ai, app, client, citizen_user):
    token = token_for(client)
    before = upload_listing(app)

    with patch("routes.complaints.get_or_create_issue_for_complaint", side_effect=RuntimeError("db down")):
        res = post_complaint(client, token, fake_image())

    assert res.status_code == 500
    assert upload_listing(app) == before


@patch("routes.complaints.analyze_complaint", side_effect=RuntimeError("provider down"))
def test_ai_failure_removes_saved_photo(mock_ai, app, client, citizen_user):
    token = token_for(client)
    before = upload_listing(app)

    res = post_complaint(client, token, fake_image())

    assert res.status_code == 500
    assert upload_listing(app) == before


def test_ai_failure_response_does_not_leak_exception_text(app, client, citizen_user, caplog):
    secret_detail = "https://provider.example/v1?key=SUPER-SECRET-123 connection refused"
    token = token_for(client)
    before = upload_listing(app)

    with patch("routes.complaints.analyze_complaint", side_effect=RuntimeError(secret_detail)):
        with caplog.at_level("ERROR"):
            res = post_complaint(client, token, fake_image())

    assert res.status_code == 500
    body = res.get_json()
    assert body == {"message": "AI analysis failed"}
    assert "SUPER-SECRET" not in res.get_data(as_text=True)
    # diagnostics are still available server-side
    assert "SUPER-SECRET-123" in caplog.text
    assert upload_listing(app) == before
