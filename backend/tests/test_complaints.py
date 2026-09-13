from unittest.mock import patch


def get_token(client, email, password):
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    return res.get_json()["token"]


@patch("routes.complaints.analyze_complaint")
def test_create_and_get_complaint(mock_ai, client, citizen_user):
    mock_ai.return_value = {
        "category": "Road Infrastructure",
        "priority": "High",
        "department": "Roads Dept",
        "visual_observation": "Pothole spotted",
        "summary": "Fix pothole"
    }

    token = get_token(client, "citizen@example.com", "password123")

    # Create complaint
    create_res = client.post(
        "/api/complaints/",
        data={
            "title": "Pothole on Main St",
            "description": "Deep hole near intersection",
            "location": "20.011, 73.790"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert create_res.status_code == 201
    complaint_data = create_res.get_json()["complaint"]
    assert complaint_data["title"] == "Pothole on Main St"
    assert complaint_data["category"] == "Road Infrastructure"

    # Get my complaints
    get_res = client.get(
        "/api/complaints/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_res.status_code == 200
    my_complaints = get_res.get_json()["complaints"]
    assert len(my_complaints) == 1


def test_officer_status_update_permission(client, citizen_user, officer_user):
    citizen_token = get_token(client, "citizen@example.com", "password123")
    officer_token = get_token(client, "officer@example.com", "officer123")

    with patch("routes.complaints.analyze_complaint") as mock_ai:
        mock_ai.return_value = {"category": "Other", "priority": "Low", "department": "General", "visual_observation": "None", "summary": "Test"}
        create_res = client.post(
            "/api/complaints/",
            data={"title": "Broken bench", "description": "Park bench", "location": "Park"},
            headers={"Authorization": f"Bearer {citizen_token}"}
        )
        complaint_id = create_res.get_json()["complaint"]["id"]

    # Citizen trying to update status should be forbidden (403)
    citizen_status_res = client.put(
        f"/api/complaints/{complaint_id}/status",
        json={"status": "In Progress"},
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert citizen_status_res.status_code == 403

    # Officer updating status should succeed (200)
    officer_status_res = client.put(
        f"/api/complaints/{complaint_id}/status",
        json={"status": "In Progress"},
        headers={"Authorization": f"Bearer {officer_token}"}
    )
    assert officer_status_res.status_code == 200
    assert officer_status_res.get_json()["complaint"]["status"] == "In Progress"
