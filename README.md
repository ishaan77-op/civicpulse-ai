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

NMC-SmartFix is a civic-tech platform built for Nashik Municipal Corporation (NMC): citizens submit issues such as potholes, garbage overflow, water supply problems, faulty streetlights, or drainage blockages — with a title, description, a camera photo, and a location picked on an interactive map. A Gemini-powered AI service reads the text and photo together and returns a structured analysis (category, priority, responsible department, a short visual observation, and a summary, plus a spam/mismatch signal), which is attached to the complaint automatically. Complaints are also auto-clustered into shared "civic issues" so duplicate reports of the same pothole don't create separate work items. Citizens can additionally support, verify, and comment on public civic issues, and track a personal Community Impact Score. Municipal officers track and update field-work evidence, while Chief Officers inspect resolution evidence in a dedicated review queue before complaints can officially be marked "Resolved". Admins get a platform-wide dashboard with resolution rates, category/department/priority breakdowns, and community engagement analytics.

The pilot location baked into the map component is **Nashik, India**.

## Project status

The full application — Flask API, Gemini AI analysis, JWT auth, role-based dashboards, the Leaflet map picker, and the community engagement layer — lives on the **`level1-integration`** branch (this branch, `level1-integration-work`, is the active integration/verification branch built on top of it, merged with the community/maps/notifications/moderation features from `ai-engine`). **`main` is still the original Vite + React scaffold and does not contain a `backend/` directory yet.** Use `level1-integration` (or a branch based on it) to run the real application described below.

This is Level 1 of the project (core complaint flow) plus field-work evidence tracking, Chief Officer resolution verification, and an initial Level 2 slice (community engagement: support, verification, comments, impact scoring, moderation). Heatmap polish, RAG, Redis, custom-trained AI, async processing, and containerization are intentionally out of scope for now.

## Key features

**Citizen**
- Register / log in (JWT-based auth, bcrypt-hashed passwords)
- Submit a complaint with title, description, a **live camera photo** (no file-upload fallback — see note below), and a location picked/searched on an interactive Nashik map
- View AI-generated category, priority, department, visual observation, and summary for each submitted complaint
- Track official status (`Pending` → `In Progress` → `Pending Review` → `Resolved`, or `Rejected` if out of scope)
- Browse the community feed of public civic issues (recent / trending / nearby / priority), support or verify an issue, and comment on it
- Track a personal Community Impact Score and recent activity

**AI engine** (`backend/services/ai_service.py`)
- Sends each complaint's text and photo to Google Gemini in one call
- Returns structured JSON: `category`, `priority`, `department`, `visual_observation`, `summary`, plus a `spam_flag`/`spam_reason`/`spam_confidence` signal when the photo doesn't match the description
- Categories: Road Infrastructure, Street Lighting, Garbage and Waste, Water Supply, Drainage, Public Safety, Other

**Officer**
- Queue of all complaints, filterable by status, category, keyword/location search
- Dedicated complaint detail page (`/officer/complaints/:id`) with chronological field-work log
- **Field-work updates**: record progress notes, photos, and optional GPS coordinates; updates status to `Pending` or `In Progress` (ordinary work updates cannot bypass review to set `Resolved`)
- **Resolution review submission**: submit final completion note and mandatory evidence photo, transitioning status to `Pending Review`
- View Chief Officer rejection feedback and resubmit corrected resolution evidence
- Reject out-of-scope complaints (with reason), or reopen a rejected/spam decision
- Spam/misreport review queue and issue-cluster view (multiple complaints grouped into one civic issue)
- Quick stats (total / pending / in progress / pending review / resolved) and a damage heatmap tab
- Per-issue community intelligence (support/verification/comment signal) and a comment moderation queue (flagged/removed/visible, remove or restore)

**Chief Officer**
- Dedicated Resolution Review Queue (`/chief-officer`)
- Inspect submitted resolution evidence: completion note, final evidence photo, GPS coordinates, submitting officer, and server timestamp
- Approve resolution (officially transitions complaint status to `Resolved`) or reject (requires rejection reason, reverts status to `In Progress` for officer correction)
- Server-enforced audit guarantees: submitting officer cannot approve their own request, no double-approvals, and authoritative server timestamps

**Admin**
- Platform-wide analytics: totals, resolution rate, and breakdowns by category, department, and priority
- User list and role management (promote/demote Citizen / Officer / Chief Officer / Admin), including suspending spam-flagged users
- Same spam review, issue-cluster, and heatmap views as Officer
- Community analytics: supports, verifications, comments, impact-score averages, community-confirmed-unresolved and disputed-resolution counts, engagement by category

> **Note on the camera-only photo requirement:** `CameraCapture.jsx` calls `getUserMedia` directly with no `<input type="file">` fallback — a report cannot be submitted without live camera access. This looks intentional (it stops citizens from uploading old/reused/stock photos), but it also means the app cannot be used on a device/browser that denies or lacks camera access. Worth confirming this is the desired behavior before a demo.

## Tech stack

**Frontend** — `frontend/`
- React 19 + Vite 8 (Rolldown-powered)
- React Router v7
- Tailwind CSS v4
- Axios for API calls
- React-Leaflet + Leaflet (+ `leaflet.heat` for the heatmap tab, `leaflet-control-geocoder` for address search) for the map/location picker
- Camera capture via the browser `MediaDevices` API (no file-upload fallback by design — see note above)

**Backend** — `backend/`
- Flask 3 + Flask-CORS
- Flask-SQLAlchemy (SQLite by default) for User, Complaint, CivicIssue, Notification, and community models (support, verification, comment, impact-score event)
- Flask-JWT-Extended for authentication, bcrypt for password hashing
- `google-genai` (Gemini) for AI complaint analysis
- pytest test suite (`backend/tests/`), including dedicated community-feature tests

## Repository structure

```
civicpulse-ai/
├── frontend/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/        # appshell, navbar, footer, brand, protectedroute,
│   │   │                        # MapPicker, CameraCapture, HeatmapView,
│   │   │                        # SpamReviewList, IssueClusterList, RejectedComplaintsList,
│   │   │                        # WorkUpdatePanel, ResolutionReviewPanel,
│   │   │                        # NotificationBanner, Community* (analytics, comments, issue card, moderation list), ImpactPanel
│   │   ├── config/             # api.js, routes.js
│   │   ├── context/            # authcontext.jsx, authcontextvalue.jsx
│   │   ├── pages/              # home, about, features, how-it-works, login, register,
│   │   │                        # citizendashboard, report, complaints, complaintdetails,
│   │   │                        # profile, officerdashboard, officercomplaintdetail,
│   │   │                        # chiefOfficerDashboard, admindashboard, notfound,
│   │   │                        # community, communityissue
│   │   ├── services/           # api.js, authservice.js, complaintservice.js, notificationservice.js, communityservice.js
│   │   └── utils/               # constants.js, formatDateTime.js, helper.js, roleHome.js, community.js
│   └── package.json
└── backend/
    ├── app.py
    ├── config.py
    ├── seed.py                  # seeds demo Citizen/Officer/Admin accounts
    ├── database/db.py
    ├── models/                  # user.py, complaint.py, civic_issue.py, notification.py, community.py,
    │                             # work_update.py, resolution_review.py
    ├── routes/                  # auth.py, complaints.py, officers.py, admin.py, notifications.py, community.py,
    │                             # resolution_review.py
    ├── services/                # ai_service.py, auth_service.py, complaint_service.py, issue_clustering.py,
    │                             # community_service.py, community_identity.py, impact_score_service.py
    ├── utils/                   # jwt_helper.py, time_helper.py, validators.py
    └── tests/                   # pytest suite (133 tests: test_work_updates.py, test_resolution_review.py, test_community.py, etc.)
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

### Backend (macOS/Linux/manual setup)

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

Vite proxies `/api` and `/uploads` to `http://127.0.0.1:5001` (see `vite.config.js`), so run the backend first. The dev server serves over HTTPS when a local mkcert certificate is present under `frontend/.cert/` — this is needed for browser camera/geolocation APIs to work when testing over a LAN IP — and falls back to plain HTTP if no cert exists.

### Tests

```bash
cd backend
source venv/bin/activate
pytest -q   # 133 automated tests covering auth, complaints, clustering, community, field updates, and resolution reviews
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
| PUT | `/api/complaints/<id>/status` | Update status: Pending / In Progress | JWT (Officer/Admin) |
| PUT | `/api/complaints/<id>/reject` | Reject a complaint as out-of-scope, with reason | JWT (Officer/Admin) |
| PUT | `/api/complaints/<id>/reopen-rejection` | Reopen a previously rejected complaint | JWT (Officer/Admin) |
| GET | `/api/officers/complaints` | Filterable complaint queue | JWT (Officer/Admin) |
| POST | `/api/officers/complaints/<id>/work-updates` | Record field-work progress note, photo, GPS (status: Pending / In Progress) | JWT (Officer/Admin) |
| GET | `/api/officers/complaints/<id>/work-updates` | List field-work updates for a complaint | JWT (Officer/Admin) |
| POST | `/api/officers/complaints/<id>/resolution-review` | Submit final-resolution evidence for review (status → Pending Review) | JWT (Officer/Admin) |
| GET | `/api/officers/complaints/<id>/resolution-review` | Get latest resolution review for a complaint | JWT (Officer/Chief Officer/Admin) |
| GET | `/api/chief-officer/resolution-queue` | List complaints awaiting final resolution approval | JWT (Chief Officer) |
| PUT | `/api/chief-officer/resolution-reviews/<id>/decide` | Approve (status → Resolved) or reject (status → In Progress) with reason | JWT (Chief Officer) |
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
| PUT | `/api/admin/users/<id>/role` | Change a user's role (Citizen / Officer / Chief Officer / Admin) / suspend | JWT (Admin) |
| GET | `/api/notifications/` | List the current user's notifications | JWT |
| PUT | `/api/notifications/<id>/read` | Mark a notification read | JWT |
| GET | `/api/community/feed` | Public civic-issue feed (recent / trending / nearby / priority) | JWT |
| GET | `/api/community/issues/<id>` | Issue detail with community snapshot, evidence, timeline | JWT |
| POST | `/api/community/issues/<id>/support` | Support an issue (citizen only) | JWT (Citizen) |
| DELETE | `/api/community/issues/<id>/support` | Remove support | JWT (Citizen) |
| POST | `/api/community/issues/<id>/verify` | Verify an issue's current state (citizen only) | JWT (Citizen) |
| DELETE | `/api/community/issues/<id>/verify` | Withdraw a verification | JWT (Citizen) |
| GET | `/api/community/issues/<id>/comments` | List public comments on an issue | JWT |
| POST | `/api/community/issues/<id>/comments` | Post a comment | JWT |
| PUT | `/api/community/comments/<id>` | Edit own comment | JWT |
| DELETE | `/api/community/comments/<id>` | Soft-delete own comment | JWT |
| POST | `/api/community/comments/<id>/report` | Report another citizen's comment | JWT |
| GET | `/api/community/me/impact` | Current user's impact score, stats, and breakdown | JWT (Citizen) |
| GET | `/api/community/me/activity` | Current user's recent impact-score events | JWT (Citizen) |
| GET | `/api/community/moderation/comments` | Comment moderation queue | JWT (Officer/Admin) |
| PUT | `/api/community/moderation/comments/<id>` | Remove or restore a flagged comment | JWT (Officer/Admin) |
| GET | `/api/community/issues/<id>/intelligence` | Per-issue community signal for staff | JWT (Officer/Admin) |
| GET | `/api/community/analytics` | Platform-wide community engagement analytics | JWT (Admin) |
| GET | `/api/health` | Health check | – |
| GET | `/uploads/<filename>` | Serve an uploaded complaint photo | – |

## Known limitations

- **Photo submission is camera-only.** `CameraCapture.jsx` calls the camera API directly with no file-upload fallback, so the report flow is unusable on a device/browser that denies or lacks camera access.
- **No retry on transient Gemini errors.** A `503` ("model overloaded") from Gemini currently surfaces as a hard failure with no retry.
- **Open CORS.** `CORS(app)` in `app.py` currently allows all origins; tighten this before any public deployment.

## Roadmap

- [ ] Merge `level1-integration` into `main`
- [ ] Confirm the camera-only photo requirement is intentional, or add a fallback
- [ ] Add Gemini failure handling (a transient `503` from the model currently surfaces as a hard submission failure)
- [ ] Reseed/clean leftover test data (Playwright/manual test complaints and users) before any live demo
- [ ] Lightweight CI (run `pytest` + `npm run build` on push)
- [ ] Tighter CORS configuration for a real deployment
- [ ] Build out the rest of Level 2 (community features) beyond the current support/verify/comment/impact-score/moderation slice

Explicitly deferred beyond Level 1/initial Level 2: heatmap polish, RAG, Redis, custom-trained AI, async AI processing, Docker, full production CI/CD, production secrets infrastructure, database migration infrastructure.

## Contributing

1. Branch from `level1-integration` (not `main`, until it's merged there)
2. Keep AI prompt logic in `backend/services/ai_service.py` and secrets out of version control (`.env` is gitignored; copy `backend/.env.example`)
3. Run `pytest` (backend) and `npm run build` (frontend) before opening a PR

## License

MIT © 2026 Ishaan Pande — see [LICENSE](./LICENSE).
