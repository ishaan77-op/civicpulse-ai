# NMC-SmartFix (CivicPulse AI)

**AI-powered municipal complaint intelligence platform** — citizens report civic issues with a live photo and a pinned map location, and Google Gemini automatically classifies, prioritizes, and routes each report to the right municipal department.

<p>
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Frontend" src="https://img.shields.io/badge/frontend-React%2019%20%2B%20Vite-61dafb">
  <img alt="Backend" src="https://img.shields.io/badge/backend-Flask-black">
  <img alt="AI" src="https://img.shields.io/badge/AI-Google%20Gemini-4285F4">
</p>

---

## About

NMC-SmartFix is a civic-tech platform built for Nashik Municipal Corporation (NMC): citizens submit issues such as potholes, garbage overflow, water supply problems, faulty streetlights, or drainage blockages — with a title, description, a camera photo, and a location picked on an interactive map. A Gemini-powered AI service reads the text and photo together and returns a structured analysis (category, priority, responsible department, a short visual observation, and a summary, plus a spam/mismatch signal), which is attached to the complaint automatically. Complaints are also auto-clustered into shared "civic issues" so duplicate reports of the same pothole don't create separate work items. Municipal officers work a triaged queue (filter, update status, review spam, reject out-of-scope reports), and admins get a platform-wide dashboard with resolution rates and category/department/priority breakdowns.

The pilot location baked into the map component is **Nashik, India**.

## Project status

The full application — Flask API, Gemini AI analysis, JWT auth, role-based dashboards, the Leaflet map picker — lives on the **`level1-integration`** branch (this branch, `level1-integration-work`, is the active integration/verification branch built on top of it). **`main` is still the original Vite + React scaffold and does not contain a `backend/` directory yet.** Use `level1-integration` (or a branch based on it) to run the real application described below.

This is Level 1 of the project: a reliably working end-to-end civic-complaint flow for citizens, officers, and admins. Heatmaps, RAG, Redis, custom-trained AI, async processing, and containerization are intentionally out of scope for now.

## Key features

**Citizen**
- Register / log in (JWT-based auth, bcrypt-hashed passwords)
- Submit a complaint with title, description, a **live camera photo** (no file-upload fallback — see note below), and a location picked/searched on an interactive Nashik map
- View AI-generated category, priority, department, visual observation, and summary for each submitted complaint
- Track status (`Pending` → `In Progress` → `Resolved`, or `Rejected` if out of scope)

**AI engine** (`backend/services/ai_service.py`)
- Sends each complaint's text and photo to Google Gemini in one call
- Returns structured JSON: `category`, `priority`, `department`, `visual_observation`, `summary`, plus a `spam_flag`/`spam_reason`/`spam_confidence` signal when the photo doesn't match the description
- Categories: Road Infrastructure, Street Lighting, Garbage and Waste, Water Supply, Drainage, Public Safety, Other

**Officer**
- Queue of all complaints, filterable by status, category, keyword/location search
- Update a complaint's status, reject it as out-of-scope (with reason), or reopen a rejected/spam decision
- Spam/misreport review queue and issue-cluster view (multiple complaints grouped into one civic issue)
- Quick stats (total / pending / in progress / resolved) and a damage heatmap tab

**Admin**
- Platform-wide analytics: totals, resolution rate, and breakdowns by category, department, and priority
- User list and role management (promote/demote Citizen / Officer / Admin), including suspending spam-flagged users
- Same spam review, issue-cluster, and heatmap views as Officer

> **Note on the camera-only photo requirement:** `CameraCapture.jsx` calls `getUserMedia` directly with no `<input type="file">` fallback — a report cannot be submitted without live camera access. This looks intentional (it stops citizens from uploading old/reused/stock photos), but it also means the app cannot be used on a device/browser that denies or lacks camera access. Worth confirming this is the desired behavior before a demo.

## Tech stack

**Frontend** — `frontend/`
- React 19 + Vite 8 (Rolldown-powered)
- React Router v7
- Tailwind CSS v4
- Axios for API calls
- React-Leaflet + Leaflet (+ `leaflet.heat` for the heatmap tab, `leaflet-control-geocoder` for address search) for the map/location picker

**Backend** — `backend/`
- Flask 3 + Flask-CORS
- Flask-SQLAlchemy (SQLite by default) for User, Complaint, CivicIssue, and Notification models
- Flask-JWT-Extended for authentication, bcrypt for password hashing
- `google-genai` (Gemini) for AI complaint analysis
- pytest test suite (`backend/tests/`) — 62 tests as of this writing, all passing

## Repository structure

```
civicpulse-ai/
├── frontend/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/       # appshell, navbar, footer, brand, protectedroute,
│   │   │                      # MapPicker, CameraCapture, HeatmapView,
│   │   │                      # SpamReviewList, IssueClusterList, RejectedComplaintsList,
│   │   │                      # NotificationBanner
│   │   ├── config/            # api.js, routes.js
│   │   ├── context/           # authcontext.jsx, authcontextvalue.jsx
│   │   ├── pages/              # home, about, features, how-it-works, login, register,
│   │   │                        # citizendashboard, report, complaints, complaintdetails,
│   │   │                        # profile, officerdashboard, admindashboard, notfound
│   │   ├── services/           # api.js, authservice.js, complaintservice.js, notificationservice.js
│   │   └── utils/               # constants.js, formatDateTime.js, helper.js, roleHome.js
│   └── package.json
└── backend/
    ├── app.py
    ├── config.py
    ├── seed.py                  # seeds demo Citizen/Officer/Admin accounts
    ├── database/db.py
    ├── models/                  # user.py, complaint.py, civic_issue.py, notification.py
    ├── routes/                  # auth.py, complaints.py, officers.py, admin.py, notifications.py
    ├── services/                # ai_service.py, auth_service.py, complaint_service.py, issue_clustering.py
    ├── utils/                   # jwt_helper.py, time_helper.py, validators.py
    └── tests/                   # pytest suite
```

## Getting started

### Prerequisites
- Node.js 18+ and npm
- Python 3.10+
- A Google Gemini API key (for AI-powered complaint analysis)

### Backend

```bash
git checkout level1-integration
cd backend
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # then fill in SECRET_KEY, JWT_SECRET_KEY, GEMINI_API_KEY
python app.py
```

This starts Flask on `http://127.0.0.1:5001` (override with `PORT`), creates the SQLite database (`instance/civicpulse.db`) on first run, and exposes the API under `/api/...`. `config.py` requires `SECRET_KEY` and `JWT_SECRET_KEY` to be set via environment — it raises at startup if they're missing, it does not fall back to a hardcoded default.

Optionally seed demo accounts (Citizen `citizen@example.com` / `password123`, Officer `officer@example.com` / `officer123`, Admin `admin@example.com` / `admin123`):

```bash
python seed.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` and `/uploads` to `http://127.0.0.1:5001` (see `vite.config.js`), so run the backend first.

### Tests

```bash
cd backend
source venv/bin/activate
pytest
```

## API overview

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| POST | `/api/auth/register` | Create a Citizen account | – |
| POST | `/api/auth/login` | Log in, receive a JWT | – |
| GET | `/api/auth/profile` | Get the current user | JWT |
| POST | `/api/complaints/` | Submit a complaint (title, description, location, photo), triggers AI analysis | JWT (Citizen) |
| GET | `/api/complaints/` | List the current user's complaints | JWT |
| GET | `/api/complaints/<id>` | Get one complaint (own, or any as Officer/Admin) | JWT |
| PUT | `/api/complaints/<id>` | Edit a complaint's own fields | JWT |
| PUT | `/api/complaints/<id>/status` | Update status: Pending / In Progress / Resolved | JWT (Officer/Admin) |
| PUT | `/api/complaints/<id>/reject` | Reject a complaint as out-of-scope, with reason | JWT (Officer/Admin) |
| PUT | `/api/complaints/<id>/reopen-rejection` | Reopen a previously rejected complaint | JWT (Officer/Admin) |
| GET | `/api/officers/complaints` | Filterable complaint queue | JWT (Officer/Admin) |
| GET | `/api/officers/heatmap` | Location + weight data for the damage heatmap | JWT (Officer/Admin) |
| GET | `/api/officers/stats` | Quick status counts | JWT (Officer/Admin) |
| GET | `/api/officers/spam` | Spam/misreport review queue | JWT (Officer/Admin) |
| PUT | `/api/officers/spam/<id>/review` | Confirm or dismiss an AI spam flag | JWT (Officer/Admin) |
| PUT | `/api/officers/spam/<id>/reopen` | Reopen a spam decision | JWT (Officer/Admin) |
| GET | `/api/officers/issues` | List clustered civic issues | JWT (Officer/Admin) |
| GET | `/api/officers/issues/<id>/complaints` | List complaints within a cluster | JWT (Officer/Admin) |
| PUT | `/api/officers/issues/<id>/status` | Update a cluster's overall status | JWT (Officer/Admin) |
| GET | `/api/admin/analytics` | Platform-wide analytics and breakdowns | JWT (Admin) |
| GET | `/api/admin/users` | List all users | JWT (Admin) |
| PUT | `/api/admin/users/<id>/role` | Change a user's role / suspend | JWT (Admin) |
| GET | `/api/notifications/` | List the current user's notifications | JWT |
| PUT | `/api/notifications/<id>/read` | Mark a notification read | JWT |
| GET | `/api/health` | Health check | – |
| GET | `/uploads/<filename>` | Serve an uploaded complaint photo | – |

## Roadmap

- [ ] Merge `level1-integration` into `main`
- [ ] Confirm the camera-only photo requirement is intentional, or add a fallback
- [ ] Add Gemini failure handling (a transient `503` from the model currently surfaces as a hard submission failure)
- [ ] Reseed/clean leftover test data (Playwright/manual test complaints and users) before any live demo
- [ ] Lightweight CI (run `pytest` + `npm run build` on push)
- [ ] Tighter CORS configuration for a real deployment

Explicitly deferred beyond Level 1: heatmap polish, RAG, Redis, custom-trained AI, async AI processing, community/social features, Docker, full production CI/CD, production secrets infrastructure, database migration infrastructure.

## Contributing

1. Branch from `level1-integration` (not `main`, until it's merged there)
2. Keep AI prompt logic in `backend/services/ai_service.py` and secrets out of version control (`.env` is gitignored; copy `backend/.env.example`)
3. Run `pytest` (backend) and `npm run build` (frontend) before opening a PR

## License

MIT © 2026 Ishaan Pande — see [LICENSE](./LICENSE).
