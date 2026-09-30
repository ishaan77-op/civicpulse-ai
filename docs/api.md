# CivicPulse AI — API Documentation

Base URL: `http://localhost:5000/api` (or proxied via `/api` in Vite)

All endpoints expecting authentication require standard Bearer HTTP header:
`Authorization: Bearer <JWT_TOKEN>`

---

## Authentication (`/api/auth`)

### 1. Register User
- **URL**: `/api/auth/register`
- **Method**: `POST`
- **Auth**: None
- **Body**:
  ```json
  {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "password": "securepassword123",
    "role": "Citizen"
  }
  ```
- **Response (201 Created)**:
  ```json
  {
    "message": "User registered successfully",
    "token": "eyJhbGciOi...",
    "user": {
      "id": 1,
      "name": "Jane Doe",
      "email": "jane@example.com",
      "role": "Citizen"
    }
  }
  ```

### 2. User Login
- **URL**: `/api/auth/login`
- **Method**: `POST`
- **Auth**: None
- **Body**:
  ```json
  {
    "email": "jane@example.com",
    "password": "securepassword123"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "message": "Login Successful",
    "token": "eyJhbGciOi...",
    "user": {
      "id": 1,
      "name": "Jane Doe",
      "email": "jane@example.com",
      "role": "Citizen"
    }
  }
  ```

### 3. Get User Profile
- **URL**: `/api/auth/profile`
- **Method**: `GET`
- **Auth**: Required
- **Response (200 OK)**:
  ```json
  {
    "id": 1,
    "name": "Jane Doe",
    "email": "jane@example.com",
    "role": "Citizen"
  }
  ```

---

## Complaints (`/api/complaints`)

### 1. Create Complaint
- **URL**: `/api/complaints/`
- **Method**: `POST`
- **Auth**: Required
- **Content-Type**: `multipart/form-data`
- **Form Fields**:
  - `title` (string, required)
  - `description` (string, required)
  - `location` (string, required)
  - `image` (file, optional)
- **Response (201 Created)**:
  ```json
  {
    "message": "Complaint created successfully",
    "complaint": {
      "id": 10,
      "title": "Large Pothole on Main St",
      "description": "Deep pothole causing vehicle damage",
      "category": "Road Infrastructure",
      "location": "20.011000, 73.790300",
      "status": "Pending",
      "user_id": 1,
      "image_filename": "a1b2c3_pothole.jpg",
      "image_url": "/uploads/a1b2c3_pothole.jpg",
      "created_at": "2026-08-13T10:30:00",
      "ai_analysis": {
        "priority": "High",
        "department": "Roads & Highways",
        "visual_observation": "Severe asphalt erosion detected.",
        "summary": "High risk pothole requiring resurfacing."
      }
    }
  }
  ```

### 2. Get My Complaints
- **URL**: `/api/complaints/`
- **Method**: `GET`
- **Auth**: Required
- **Response (200 OK)**: Array of complaints filed by logged-in citizen.

### 3. Get Single Complaint
- **URL**: `/api/complaints/<id>`
- **Method**: `GET`
- **Auth**: Required
- **Response (200 OK)**: Complaint object.

### 4. Update Complaint Status (Officer / Admin)
- **URL**: `/api/complaints/<id>/status`
- **Method**: `PUT`
- **Auth**: Required (Officer or Admin role)
- **Body**:
  ```json
  {
    "status": "In Progress"
  }
  ```
- **Response (200 OK)**: Updated complaint object.

---

## Officer Hub (`/api/officers`)

### 1. Get All Municipal Complaints
- **URL**: `/api/officers/complaints?status=Pending&category=Roads`
- **Method**: `GET`
- **Auth**: Required (Officer or Admin)
- **Response (200 OK)**: Array of all complaints with filter criteria.

### 2. Get Workload Statistics
- **URL**: `/api/officers/stats`
- **Method**: `GET`
- **Auth**: Required (Officer or Admin)
- **Response (200 OK)**: Count of total, pending, in_progress, and resolved complaints.

---

## Admin Intelligence (`/api/admin`)

### 1. Get Platform Analytics
- **URL**: `/api/admin/analytics`
- **Method**: `GET`
- **Auth**: Required (Admin role)
- **Response (200 OK)**: System summary, category breakdown, department workload, and priority distributions.

### 2. List Users & Update User Roles
- **URL**: `/api/admin/users` (GET)
- **URL**: `/api/admin/users/<id>/role` (PUT with `{ "role": "Officer" }`)
- **Method**: `GET` / `PUT`
- **Auth**: Required (Admin role)
