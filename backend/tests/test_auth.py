def test_register_success(client):
    response = client.post("/api/auth/register", json={
        "name": "New User",
        "email": "newuser@example.com",
        "password": "password123",
        "role": "Citizen"
    })
    assert response.status_code == 201
    data = response.get_json()
    assert "token" in data
    assert "user" in data
    assert data["user"]["email"] == "newuser@example.com"


def test_register_duplicate_email(client, citizen_user):
    response = client.post("/api/auth/register", json={
        "name": "Duplicate",
        "email": "citizen@example.com",
        "password": "password123"
    })
    assert response.status_code == 400
    data = response.get_json()
    assert "Email already exists" in data["message"]


def test_login_success(client, citizen_user):
    response = client.post("/api/auth/login", json={
        "email": "citizen@example.com",
        "password": "password123"
    })
    assert response.status_code == 200
    data = response.get_json()
    assert "token" in data
    assert data["user"]["email"] == "citizen@example.com"


def test_login_invalid_password(client, citizen_user):
    response = client.post("/api/auth/login", json={
        "email": "citizen@example.com",
        "password": "wrongpassword"
    })
    assert response.status_code == 401


def test_profile_protected(client, citizen_user):
    login_res = client.post("/api/auth/login", json={
        "email": "citizen@example.com",
        "password": "password123"
    })
    token = login_res.get_json()["token"]

    profile_res = client.get(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert profile_res.status_code == 200
    profile_data = profile_res.get_json()
    assert profile_data["email"] == "citizen@example.com"
