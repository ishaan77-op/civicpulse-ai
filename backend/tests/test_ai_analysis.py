import json
import os
from unittest.mock import MagicMock, patch
import pytest

from google.genai.errors import ServerError
from models.complaint import Complaint
from services.ai_service import analyze_complaint, get_client
from tests.helpers import fake_image, JPEG_BYTES


def get_token(client, email="citizen@example.com", password="password123"):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


def test_analyze_complaint_success():
    """Verify successful AI analysis response is properly parsed into structured JSON."""
    mock_payload = {
        "category": "Road Infrastructure",
        "priority": "High",
        "department": "Road Department",
        "visual_observation": "Deep pothole on asphalt",
        "summary": "Pothole on Main St",
        "spam_flag": False,
        "spam_reason": "",
        "spam_confidence": "",
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_payload)
    mock_client.models.generate_content.return_value = mock_response

    with patch("services.ai_service.get_client", return_value=mock_client):
        result = analyze_complaint(
            title="Pothole on Main St",
            description="Deep pothole causing vehicle damage",
            location="Main St, Nashik",
        )

    assert result == mock_payload
    mock_client.models.generate_content.assert_called_once()
    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-3.6-flash"
    assert kwargs["config"].automatic_function_calling.disable is True


def test_analyze_complaint_markdown_fences_stripped():
    """Verify that Markdown code fences in AI text are stripped before JSON decoding."""
    mock_payload = {
        "category": "Street Lighting",
        "priority": "Medium",
        "department": "Electrical Dept",
        "visual_observation": "Broken bulb",
        "summary": "Dark street",
        "spam_flag": False,
        "spam_reason": "",
        "spam_confidence": "",
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = f"```json\n{json.dumps(mock_payload)}\n```"
    mock_client.models.generate_content.return_value = mock_response

    with patch("services.ai_service.get_client", return_value=mock_client):
        result = analyze_complaint("Lamp post", "Dark", "Location")

    assert result == mock_payload


def test_analyze_complaint_504_timeout_propagates():
    """Verify that a 504 DEADLINE_EXCEEDED from Gemini propagates as an exception."""
    mock_client = MagicMock()
    error_response = {
        "error": {
            "code": 504,
            "message": "Deadline expired before operation could complete.",
            "status": "DEADLINE_EXCEEDED",
        }
    }
    mock_client.models.generate_content.side_effect = ServerError(504, error_response)

    with patch("services.ai_service.get_client", return_value=mock_client):
        with pytest.raises(ServerError) as exc_info:
            analyze_complaint("Pothole", "Deep hole", "Nashik")

    assert exc_info.value.code == 504
    assert "Deadline expired" in str(exc_info.value)


def test_analyze_complaint_malformed_json_raises_value_error():
    """Verify that unparseable non-JSON text from the AI raises a descriptive ValueError."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Sorry, I am unable to analyze this image as requested."
    mock_client.models.generate_content.return_value = mock_response

    with patch("services.ai_service.get_client", return_value=mock_client):
        with pytest.raises(ValueError, match="AI returned invalid JSON"):
            analyze_complaint("Pothole", "Deep hole", "Nashik")


def test_complaint_creation_route_handles_504_timeout_with_cleanup(app, client, citizen_user):
    """
    Regression: When Gemini encounters a 504 DEADLINE_EXCEEDED timeout:
    1. The route returns HTTP 500 with a generic message ('AI analysis failed').
    2. No partial complaint record is saved to the database.
    3. The uploaded photo file is cleaned up from the uploads folder.
    """
    error_response = {
        "error": {
            "code": 504,
            "message": "Deadline expired before operation could complete.",
            "status": "DEADLINE_EXCEEDED",
        }
    }
    timeout_err = ServerError(504, error_response)

    token = get_token(client)
    upload_folder = app.config["UPLOAD_FOLDER"]
    files_before = set(os.listdir(upload_folder))
    complaints_before = Complaint.query.count()

    with patch("routes.complaints.analyze_complaint", side_effect=timeout_err):
        res = client.post(
            "/api/complaints/",
            data={
                "title": "Flooded Underpass",
                "description": "Underpass submerged after heavy rain",
                "latitude": "20.005",
                "longitude": "73.785",
                "image": fake_image("underpass.jpg", JPEG_BYTES),
            },
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 500
    assert res.get_json() == {"message": "AI analysis failed"}

    # Database integrity: no complaint record created
    assert Complaint.query.count() == complaints_before

    # Disk cleanup: no uploaded file leaked
    files_after = set(os.listdir(upload_folder))
    assert files_after == files_before


def test_complaint_creation_route_handles_malformed_ai_json_with_cleanup(app, client, citizen_user):
    """
    Regression: When Gemini returns non-JSON text:
    1. The route returns HTTP 500.
    2. No partial complaint record is saved to the database.
    3. The uploaded photo file is cleaned up from the uploads folder.
    """
    token = get_token(client)
    upload_folder = app.config["UPLOAD_FOLDER"]
    files_before = set(os.listdir(upload_folder))
    complaints_before = Complaint.query.count()

    with patch("routes.complaints.analyze_complaint", side_effect=ValueError("AI returned invalid JSON")):
        res = client.post(
            "/api/complaints/",
            data={
                "title": "Garbage Spill",
                "description": "Trash everywhere",
                "latitude": "20.005",
                "longitude": "73.785",
                "image": fake_image("garbage.jpg", JPEG_BYTES),
            },
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 500
    assert res.get_json() == {"message": "AI analysis failed"}
    assert Complaint.query.count() == complaints_before
    assert set(os.listdir(upload_folder)) == files_before


def test_get_client_timeout_and_retry_configuration(monkeypatch):
    """Verify genai.Client is initialized with bounded retries and 30s timeout."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    with patch("google.genai.Client") as mock_genai_client:
        get_client()

    mock_genai_client.assert_called_once()
    _, kwargs = mock_genai_client.call_args
    assert kwargs["api_key"] == "test-api-key"
    http_opts = kwargs["http_options"]
    assert http_opts.timeout == 30_000
    assert http_opts.retry_options.attempts == 2


def test_model_selection_defaults_and_env_override(monkeypatch):
    """Verify that GEMINI_MODEL defaults to gemini-3.6-flash and respects valid override."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({"category": "Other", "priority": "Low", "department": "General", "visual_observation": "", "summary": ""})
    mock_client.models.generate_content.return_value = mock_response

    with patch("services.ai_service.get_client", return_value=mock_client):
        # 1. Unset / empty -> gemini-3.6-flash
        monkeypatch.setenv("GEMINI_MODEL", "")
        analyze_complaint("Title", "Desc", "Loc")
        assert mock_client.models.generate_content.call_args[1]["model"] == "gemini-3.6-flash"

        # 2. Set to another model
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
        analyze_complaint("Title", "Desc", "Loc")
        assert mock_client.models.generate_content.call_args[1]["model"] == "gemini-3.5-flash"
