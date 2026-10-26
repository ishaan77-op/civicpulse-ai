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

The full application runs end-to-end on this branch: Flask API, JWT auth, the Gemini AI analysis engine, the map picker, community features, and Citizen / Officer / Chief Officer / Admin dashboards, including the **resolution workflow** (Officers submit completed work, the Chief Officer approves it, citizens see before/after evidence) and **Chief Officer supervision** (ward directory, ratings, corrective follow-ups).

Branches differ across the team: `main` and the other branches may not contain all of this. Check which branch the team has chosen as the integration target (and any open pull requests) before cloning for a demo.

Run the backend tests with `pytest` in `backend/` and the frontend checks with `npm test`, `npm run lint` and `npm run build` in `frontend/` (see [Tests, lint and build](#tests-lint-and-build)).

## Roles and workflow

| Role | What they can do |
|---|---|
| **Citizen** | Report issues, track their own reports, see the before/after evidence once an issue is resolved. Never sees ratings or internal follow-ups. |
| **Officer** | Triage the queue, post field-work updates, submit completed work for review, see **only their own** ratings, and complete corrections assigned to them. |
| **Chief Officer** | Municipality-wide supervision: approves or rejects submitted work, rates approved work 1-5 stars, assigns and verifies corrective follow-ups, reads the supervisory overview and analytics. |
| **Admin** | Users, roles, wards and Officer-to-ward assignments, platform analytics. Admins are deliberately **not** given access to ratings, follow-ups or the supervisory overview. |

Complaint-to-resolution flow:

1. A citizen reports an issue; the AI classifies it and similar reports are grouped into one civic issue.
2. An Officer works the issue (optional field-work updates) and submits completed work with a completion note and a photo, covering the linked reports.
3. The issue moves to **Pending Review**. Only the Chief Officer can approve it (the issue becomes **Resolved** and citizens are notified) or reject it with a reason. If new information arrives (for example another report joins the issue), a pending review is withdrawn and the Officer must resubmit.
4. The Chief Officer may rate the approved work 1-5 stars. A 1 or 2 star rating needs a written explanation and opens a **corrective follow-up**. Ratings are append-only: a revision never deletes the original, and never closes, moves or deletes an existing follow-up.
5. The Chief Officer assigns the follow-up to an Officer, who submits a correction (note, optional photo). The Chief Officer verifies and closes it, or returns it for more work. Closing a follow-up does not change the issue's resolution status.

Correction photos are staff-only evidence. They are stored outside the public upload folder and served only to the assigned Officer and Chief Officers through authenticated API endpoints.

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

**Chief Officer**
- Overview of what needs attention, a ward and Officer directory (read-only), approval queue for completed work, ratings, corrective follow-ups, and read-only analytics with documented metric definitions (no SLA/overdue labels: none has been approved)

**Admin**
- Platform-wide analytics: totals, resolution rate, and breakdowns by category, department, and priority
- User list and role management (see Known limitations about the Chief Officer role)
- Ward registry and append-only Officer-to-ward assignment history

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
- pytest-based test suite (`backend/tests/`)

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
    └── tests/                    # pytest suite
```

## Getting started

### Prerequisites
- Node.js 18+ and npm
- Python 3.10+
- A Google Gemini API key (for AI-powered complaint analysis)

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
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
```

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | Must be `development` for local work (see below) | unset = production |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Signing secrets (placeholders only; never commit real values) | dev defaults, development only |
| `GEMINI_API_KEY` | Google Gemini key for AI analysis (`your-gemini-api-key`) | none |
| `GEMINI_MODEL` | Gemini model name | `gemini-3.6-flash` |
| `DATABASE_URL` | SQLAlchemy URL | SQLite at `backend/instance/civicpulse.db` |
| `UPLOAD_FOLDER` | Public complaint/completion photos | `backend/uploads` |
| `PRIVATE_UPLOAD_FOLDER` | Staff-only correction photos; must be **outside** `UPLOAD_FOLDER` | `backend/private_uploads` |
| `MAX_UPLOAD_MB` | Largest accepted photo | `10` |
| `HOST`, `PORT`, `FLASK_DEBUG` | Dev server binding and debug (see below) | `127.0.0.1`, `5001`, off |

`.env.example` ships with `APP_ENV=development`, which is what allows `SECRET_KEY` and `JWT_SECRET_KEY` to stay blank locally (insecure built-in development defaults are used, and a warning is logged). **Without `APP_ENV=development` the app treats the environment as production and refuses to start** unless both secrets are set to real, non-default values. Never commit `backend/.env`. Generate real secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Run the API:

```bash
python app.py
```

This starts Flask on `http://127.0.0.1:5001` (this machine only; override the port with `PORT`), creates the SQLite database (`backend/instance/civicpulse.db`) on first run, and exposes the API under `/api/...`. Debug mode is **off** by default. For auto-reload while developing, set `FLASK_DEBUG=1`; it is honoured only when `APP_ENV=development` and `HOST` is a loopback address, and is ignored (with a warning) otherwise.

Complaint photos are validated before they are saved: JPG, PNG or WebP only, content must match the extension, and the size limit is 10 MB (`MAX_UPLOAD_MB`). They are stored in `backend/uploads/` (override with `UPLOAD_FOLDER`) and served at `/uploads/<name>` **without authentication** (unguessable names, but anyone with a link can open them). Staff-only correction photos go to `backend/private_uploads/` instead (override with `PRIVATE_UPLOAD_FOLDER`) and are never served by `/uploads`; both folders are gitignored.

#### Database setup and migrations

There is no separate migration command. When the API starts it creates any missing tables and runs small **additive, idempotent** migrations (see the `migrate_*` functions in `backend/app.py`): new columns, tables, indexes and integrity triggers are added, and existing rows are never deleted or rewritten. A pre-existing prototype `resolution_reviews` table from an earlier schema is renamed to `resolution_reviews_legacy_complaint_level`, not dropped; startup stops with an error if that name is already taken. The database is a local SQLite file, so before upgrading a database that holds data you care about, **copy `backend/instance/civicpulse.db` somewhere safe first**. Never delete it to "fix" a startup error; read the error message instead.

#### Phone / LAN testing

The Vite dev server proxies `/api` and `/uploads` to the backend on `127.0.0.1`, so for testing from a phone on the same Wi-Fi you normally only need to expose the **frontend**:

```bash
cd frontend
npm run dev -- --host
```

Open the `Network:` URL that Vite prints (for the camera and geolocation APIs the page must be served over HTTPS; see the mkcert note above). The backend can stay on `127.0.0.1`.

Only if a device must reach the Flask API directly, bind it to all interfaces explicitly:

```bash
# macOS / Linux
HOST=0.0.0.0 python app.py
```

```powershell
# Windows PowerShell
$env:HOST = "0.0.0.0"; python app.py
```

This makes the API reachable by anyone on your network and the app prints a warning. Debug mode is never enabled on a non-loopback `HOST`. Unset it again afterwards (`Remove-Item Env:HOST`).

### Tests, lint and build

```bash
# Backend (uses a temporary database and temporary upload folders; it never touches backend/instance/civicpulse.db)
cd backend
pytest

# Frontend
cd frontend
npm test          # unit tests for the pure logic (Node's built-in runner)
npm run lint
npm run build
```

The frontend tests cover logic helpers only; there are no component tests, so UI changes should also be checked by hand in a browser.

### Safe demo

- Use a **copy** of the database, or a fresh one: set `DATABASE_URL=sqlite:////absolute/path/to/demo.db` (and separate `UPLOAD_FOLDER` / `PRIVATE_UPLOAD_FOLDER` directories) so the demo never writes into data you want to keep. Do not run `backend/seed.py` against a database you care about; read it first, since it creates sample accounts.
- Create people through the app: register Citizens at `/register`. Officer and Admin roles are granted by an Admin; the first Admin has to be set up by whoever controls the database. The Admin screen offers Citizen / Officer / Admin; the **Chief Officer** role is currently assigned through the Admin API (`PUT /api/admin/users/<id>/role` with `{"role": "Chief Officer"}`) and the choice of who may assign it is still an open policy decision (see Known limitations).
- Walk the flow: citizen reports an issue, Officer submits completed work, Chief Officer approves it and rates it, a low rating opens a follow-up, the Chief Officer assigns it, the Officer submits a correction, the Chief Officer verifies it. Citizens see the before/after evidence on the complaint page.
- Choose passwords yourself and do not reuse real ones. Never put real credentials, tokens or API keys in screenshots, slides or commits.

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

Resolution, ward and supervision endpoints (added with the resolution workflow; `docs/api.md` has not been extended for them yet, so the route files are the reference):

| Area | Endpoints | Who |
|---|---|---|
| Resolution workflow | `/api/issues/<id>/work-updates`, `/api/issues/<id>/resolution-reviews`, `/api/chief-officer/resolution-reviews...`, `/api/complaints/<id>/resolution-evidence` | Officer submits; Chief Officer decides; citizen reads a safe evidence view |
| Wards | `/api/admin/wards...` | Admin only |
| Supervision | `/api/chief-officer/overview`, `.../approved-work`, `.../ratings`, `.../wards/<id>`, `.../officers/<id>`, `.../follow-ups...` | Chief Officer only |
| Officer's own records | `/api/officers/me/ratings`, `/api/officers/me/follow-ups...` | Officer only (own records) |
| Correction photos | `/api/chief-officer/follow-ups/<id>/events/<event_id>/image`, `/api/officers/me/follow-ups/<id>/events/<event_id>/image` | Chief Officer; the assigned Officer |

A fuller reference for the original endpoints lives in `docs/api.md`.

## Known limitations

- **Photo submission is camera-only.** `CameraCapture.jsx` calls the camera API directly with no file-upload fallback, so the report flow is unusable on a device/browser that denies or lacks camera access. Confirm this is the desired behavior before a live demo.
- **No retry on transient Gemini errors.** A `503` ("model overloaded") from Gemini currently surfaces as a hard failure with no retry.
- **Public photo URLs.** `/uploads/<name>` serves complaint and completion photos without authentication (they are shown to citizens and in the community feed by design). Staff-only correction photos are *not* served there. Staff field-work update photos (`IssueWorkUpdate`) still are, so whether those should also move to authenticated access is an open policy decision.
- **Ward-level work is not available.** Complaints and issues are not linked to wards, so the app cannot attribute work to a ward and says so instead of showing zeros.
- **Open policy decisions:** who may assign the Chief Officer role (today any Admin, via the API), the Officer-to-ward cardinality, municipality-wide Officer access, any SLA/overdue thresholds, and whether Admins may ever see ratings.
- **Notifications do not deep-link** to the related work; they say where to look.
- **Open CORS.** `CORS(app)` in `app.py` currently allows all origins; tighten this before any public deployment.
- **Insecure secret defaults exist for local development only.** `config.py` uses built-in `SECRET_KEY` / `JWT_SECRET_KEY` defaults only when `APP_ENV=development` is set explicitly; in any other environment missing, blank or default secrets stop the app from starting.
- **JWT access tokens expire after 15 minutes** (Flask-JWT-Extended default; there is no refresh mechanism), and the frontend signs the user out on any `401`.

## Contributing

1. Branch from the integration branch the team has agreed on, using the existing convention (`feature/<name>`, `backend-<area>`, etc.), and open a pull request rather than pushing to a shared branch
2. Keep AI prompt logic in `backend/services/ai_service.py` and secrets out of version control (`.env` is already gitignored)
3. Run `pytest` (backend) and `npm test`, `npm run lint` and `npm run build` (frontend) before opening a PR

## License

MIT © 2026 Ishaan Pande — see [LICENSE](./LICENSE).
