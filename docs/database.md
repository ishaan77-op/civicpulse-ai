# CivicPulse AI — Database Schema Documentation

Engine: **SQLite 3** via **Flask-SQLAlchemy**
Database location: `instance/civicpulse.db`

---

## 1. Tables

### Table `users`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | Integer | Primary Key, Auto-increment | Unique User ID |
| `name` | String(100) | Not Null | User's full name |
| `email` | String(120) | Unique, Not Null | Account email address |
| `password_hash` | String(255) | Not Null | Bcrypt password hash |
| `role` | String(20) | Default: `"Citizen"` | Account role (`Citizen`, `Officer`, `Admin`) |
| `created_at` | DateTime | Default: `utcnow` | Account registration timestamp |

---

### Table `complaints`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | Integer | Primary Key, Auto-increment | Complaint ID |
| `title` | String(200) | Not Null | Complaint title |
| `description` | Text | Not Null | Detailed issue description |
| `category` | String(100) | Not Null, Default: `"Other"` | AI or citizen category |
| `location` | String(255) | Not Null | Geolocation coordinates / address |
| `status` | String(50) | Not Null, Default: `"Pending"` | Lifecycle status (`Pending`, `In Progress`, `Resolved`) |
| `user_id` | Integer | Foreign Key (`users.id`), Not Null | ID of submitting citizen |
| `image_filename` | String(255) | Nullable | Uploaded photo filename stored in `uploads/` |
| `ai_priority` | String(20) | Nullable | Gemini AI assigned priority (`Low`, `Medium`, `High`, `Critical`) |
| `ai_department` | String(100) | Nullable | Responsible municipal department |
| `ai_visual_observation` | Text | Nullable | Visual observation extracted from issue photo |
| `ai_summary` | Text | Nullable | Short AI triage summary |
| `created_at` | DateTime | Default: `utcnow` | Filing timestamp |

---

## 2. Relationships

```
users (1) <-------------> (N) complaints
```

- Each user can file multiple complaints (`complaints.user_id` -> `users.id`).
- Officer and Admin users access system-wide complaints across all user records.
