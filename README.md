# CivicPulse AI (NMC-SmartFix)

**AI-powered municipal complaint intelligence platform** — citizens report civic issues with a photo and a pinned location, and an AI engine automatically classifies, prioritizes, and routes each report to the right municipal department.

<p>
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Frontend" src="https://img.shields.io/badge/frontend-React%2019%20%2B%20Vite-61dafb">
  <img alt="Backend" src="https://img.shields.io/badge/backend-Flask-black">
  <img alt="AI" src="https://img.shields.io/badge/AI-Google%20Gemini-4285F4">
</p>

---

## About

CivicPulse AI (branded in the UI as NMC-SmartFix) is a civic-tech platform for municipal complaint management. Citizens submit issues such as potholes, garbage overflow, water supply problems, faulty streetlights, or drainage blockages — with a description, a camera-captured photo, and a location picked on a map. A Gemini-powered AI service reads the text and image together and returns a structured analysis (category, priority, responsible department, a short visual observation, and a summary), which is attached to the complaint automatically. Municipal officers work a triaged queue, review flagged/duplicate reports, and update status; admins get a dashboard with resolution rates and category/department/priority breakdowns.

The pilot location baked into the map component is **Nashik, India**, though the app is designed to generalize to other municipalities.

## Project status

This branch (`level1-integration`) has the full application merged and working end-to-end: Flask API, JWT auth, the Gemini AI analysis engine, the map picker, and the Citizen / Officer / Admin dashboards. `main` still reflects an earlier frontend-only scaffold — check out `level1-integration` (or whichever branch has since replaced it as the integration target) to run the real app.

Backend test suite: 62 tests, all passing (`pytest` in `backend/`).

## Key features

**Citizen**
- Register / log in (JWT-based auth, bcrypt-hashed passwords)
- Submit a complaint with title, description, category, a camera-captured photo, and a location picked on an interactive map
- Track status (`Pending` → `In Progress` → `Resolved`) and see officer rejections/re-openings with reasons
- Read own notifications (e.g. when a report is confirmed as spam)

**AI engine**
- Sends each complaint's text and image to Google Gemini
- Returns structured JSON: `category`, `priority`, `department`, `visual_observation`, `summary`
- Categories: Road Infrastructure, Garbage and Waste, Water Supply, Street Lighting, Drainage, Public Safety, Other
- Priorities: Low, Medium, High, Critical

**Officer**
- Queue of all complaints, filterable by status, category, priority, and department
- Heatmap of complaint density and clustering of duplicate/related issues into a single "civic issue"
- Spam review queue: confirm or dismiss AI-flagged spam; accounts are auto-suspended after repeated confirmed spam
- Reject complaints as out-of-scope (with a required reason) and reopen them later
- Update complaint status; quick stats (total / pending / in progress / resolved)

**Admin**
- Platform-wide analytics: totals, resolution rate, and breakdowns by category, department, and priority
- User list and role management (promote/demote Citizen / Officer / Admin)

## Tech stack

**Frontend** — `frontend/`
- React 19 + Vite (Rolldown)
- React Router v7
- Tailwind CSS v4
- Axios for API calls
- React-Leaflet + Leaflet (+ `leaflet.heat`) for the map/location picker and heatmap
- Camera capture via the browser `MediaDevices` API (no file-upload fallback by design — see Known limitations)

**Backend** — `backend/`
- Flask 3 + Flask-CORS
- Flask-SQLAlchemy (SQLite by default) for User, Complaint, and Notification models
- Flask-JWT-Extended for authentication, bcrypt for password hashing
- `google-genai` (Gemini) for AI complaint analysis
- pytest-based test suite (`backend/tests/`, 62 tests)

## Repository structure

```
civicpulse-ai/
├── docs/                      # api.md, database.md, requirements.md
├── frontend/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/        # Navbar, Footer, Button, Card, Input, ProtectedRoute, MapPicker, CameraCapture
│   │   ├── config/             # api.js, routes.js
│   │   ├── context/            # authcontext.jsx
│   │   ├── pages/               # home, login, register, citizen/officer/admin dashboards, notfound
│   │   ├── services/            # api.js, authservice.js, complaintservice.js
│   │   └── utils/
│   └── package.json
└── backend/
    ├── app.py
    ├── config.py
    ├── database/db.py
    ├── models/                 # user.py, complaint.py, notification.py, civic_issue.py
    ├── routes/                 # auth.py, complaints.py, officers.py, admin.py, notifications.py
    ├── services/                # ai_service.py, auth_service.py, complaint_service.py
    ├── utils/                   # jwt_helper.py, validators.py
    └── tests/                    # pytest suite (62 tests)
```

## Getting started

### Prerequisites
- Node.js 18+ and npm
- Python 3.10+
- A Google Gemini API key (for AI-powered complaint analysis)

### Quick start (Windows)

```bat
setup.bat    :: once per machine: venv, pip/npm installs, backend\.env, demo users
start.bat    :: every time: starts backend + frontend and opens the browser
```

`setup.bat` seeds these demo accounts:

| Role | Email | Password |
|---|---|---|
| Citizen | citizen@example.com | password123 |
| Officer | officer@example.com | officer123 |
| Admin | admin@example.com | admin123 |

Keep the project outside OneDrive/Dropbox-synced folders — sync conflicts silently replace files with stale copies (`name-COMPUTERNAME.ext`). Use git to move work between machines.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server serves over HTTPS when a local mkcert certificate is present under `frontend/.cert/` (see `vite.config.js`) — this is needed for browser camera/geolocation APIs to work when testing over a LAN IP, and falls back to plain HTTP if no cert exists. It proxies `/api` and `/uploads` to the backend at `http://127.0.0.1:5001`.

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Copy `backend/.env.example` to `backend/.env` and fill in the values (at minimum `GEMINI_API_KEY`):

```bash
cp .env.example .env
```

Run the API:

```bash
python app.py
```

This starts Flask on `http://127.0.0.1:5001` (override with `PORT`), creates the SQLite database (`backend/instance/civicpulse.db`) on first run, and exposes the API under `/api/...`.

### Tests

```bash
cd backend
pytest
```

## API overview

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| POST | `/api/auth/register` | Create an account | – |
| POST | `/api/auth/login` | Log in, receive a JWT | – |
| GET | `/api/auth/profile` | Get the current user | JWT |
| POST | `/api/complaints/` | Submit a complaint (+ optional image), triggers AI analysis | JWT |
| GET | `/api/complaints/` | List the current user's complaints | JWT |
| GET | `/api/complaints/<id>` | Get one complaint (own, or any as Officer/Admin) | JWT |
| PUT | `/api/complaints/<id>` | Edit a complaint's own fields | JWT |
| PUT | `/api/complaints/<id>/status` | Update status: Pending / In Progress / Resolved | JWT (Officer/Admin) |
| PUT | `/api/complaints/<id>/reject` | Reject a complaint as out-of-scope, with a reason | JWT (Officer/Admin) |
| PUT | `/api/complaints/<id>/reopen-rejection` | Reopen a previously rejected complaint | JWT (Officer/Admin) |
| GET | `/api/officers/complaints` | Filterable complaint queue | JWT (Officer/Admin) |
| GET | `/api/officers/heatmap` | Complaint density points for the heatmap | JWT (Officer/Admin) |
| GET | `/api/officers/stats` | Quick status counts | JWT (Officer/Admin) |
| GET | `/api/officers/spam` | AI-flagged spam review queue | JWT (Officer/Admin) |
| PUT | `/api/officers/spam/<id>/review` | Confirm or dismiss a flagged complaint as spam | JWT (Officer/Admin) |
| PUT | `/api/officers/spam/<id>/reopen` | Reopen a confirmed-spam complaint | JWT (Officer/Admin) |
| GET | `/api/officers/issues` | Clustered duplicate/related civic issues | JWT (Officer/Admin) |
| GET | `/api/officers/issues/<id>/complaints` | Complaints within a clustered issue | JWT (Officer/Admin) |
| PUT | `/api/officers/issues/<id>/status` | Update status for a whole clustered issue | JWT (Officer/Admin) |
| GET | `/api/admin/analytics` | Platform-wide analytics and breakdowns | JWT (Admin) |
| GET | `/api/admin/users` | List all users | JWT (Admin) |
| PUT | `/api/admin/users/<id>/role` | Change a user's role | JWT (Admin) |
| GET | `/api/notifications/` | List the current user's notifications | JWT |
| PUT | `/api/notifications/<id>/read` | Mark a notification as read | JWT |

A fuller reference lives in `docs/api.md`.

## Known limitations

- **Photo submission is camera-only.** `CameraCapture.jsx` calls the camera API directly with no file-upload fallback, so the report flow is unusable on a device/browser that denies or lacks camera access. Confirm this is the desired behavior before a live demo.
- **No retry on transient Gemini errors.** A `503` ("model overloaded") from Gemini currently surfaces as a hard failure with no retry.
- **Open CORS.** `CORS(app)` in `app.py` currently allows all origins; tighten this before any public deployment.
- **`SECRET_KEY` / `JWT_SECRET_KEY` fall back to hardcoded dev defaults** in `config.py` if unset in the environment — always set real values outside local dev.

## Contributing

1. Branch from `level1-integration` (or the current integration branch) using the existing convention (`feature/<name>`, `backend-<area>`, etc.)
2. Keep AI prompt logic in `backend/services/ai_service.py` and secrets out of version control (`.env` is already gitignored)
3. Run `pytest` (backend) and `npm run build` (frontend) before opening a PR

## License

MIT © 2026 Ishaan Pande — see [LICENSE](./LICENSE).
