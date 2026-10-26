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

The full application runs end-to-end: Flask API, Gemini AI analysis, JWT auth, the Leaflet map picker, the community engagement layer (support, verification, comments, impact scoring, moderation), and Citizen / Officer / Chief Officer / Admin dashboards.

Resolution is **issue-wide**: reports about the same problem are grouped into one civic issue, Officers submit completed work for the whole issue, and only the Chief Officer can approve it. This replaced an earlier complaint-level review prototype (one review per complaint, which could resolve one report of an issue while others were still open). On top of it, the Chief Officer can rate approved work and manage corrective follow-ups, and Admins manage wards. See [Roles and workflow](#roles-and-workflow).

Heatmap polish, RAG, Redis, custom-trained AI, async processing, and containerization are intentionally out of scope for now.

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
- Dedicated complaint page (`/officer/complaints/:id`) with the AI analysis and the field-work panel for the complaint's civic issue
- **Field-work updates** per civic issue: progress notes, photos and optional GPS; they can set `Pending` or `In Progress`, never `Resolved`
- **Resolution submission** per civic issue: a completion note, a mandatory evidence photo and a disposition for every linked report; the issue moves to `Pending Review`. If new information arrives (for example another report joins the issue) the pending review is withdrawn and must be resubmitted
- See Chief Officer rejection reasons and resubmit corrected evidence
- **My ratings & corrections**: the Officer's own ratings (with explanations) and corrective follow-ups assigned to them, with a correction form (note + optional photo). Officers never see other Officers' ratings
- Reject out-of-scope complaints (with reason), or reopen a rejected/spam decision
- Spam/misreport review queue and issue-cluster view, damage heatmap, quick stats
- Per-issue community intelligence and a comment moderation queue

**Chief Officer** (`/chief-officer`, municipality-wide; distinct from Admin)
- Overview of what needs attention, a read-only ward and Officer directory (with assignment history), and read-only analytics with documented metric definitions (no SLA/overdue labels: none has been approved)
- Resolution review queue: approve (the whole issue becomes `Resolved`) or reject with a reason; withdrawn reviews are listed separately
- Rate approved work 1-5 stars (a 1-2 star rating needs an explanation and opens a corrective follow-up); ratings are append-only
- Assign, verify, return or close corrective follow-ups; closing one never changes the issue's status
- Server-enforced audit guarantees: only a Chief Officer can approve, authoritative server timestamps, no double approval

**Admin**
- Platform-wide analytics: totals, resolution rate, and breakdowns by category, department, and priority
- User list and role management (the Admin API accepts Citizen / Officer / Chief Officer / Admin; the screen currently offers Citizen / Officer / Admin), including suspending spam-flagged users
- Ward registry and append-only Officer-to-ward assignment history
- Same spam review, issue-cluster, and heatmap views as Officer
- Community analytics: supports, verifications, comments, impact-score averages, community-confirmed-unresolved and disputed-resolution counts, engagement by category

> **Note on the camera-only photo requirement:** `CameraCapture.jsx` calls `getUserMedia` directly with no `<input type="file">` fallback — a report cannot be submitted without live camera access. This looks intentional (it stops citizens from uploading old/reused/stock photos), but it also means the app cannot be used on a device/browser that denies or lacks camera access. Worth confirming this is the desired behavior before a demo.

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
│   │   │                        # IssueWorkPanel, WorkUpdateForm, ResolutionSubmitForm, ResolutionQueue,
│   │   │                        # RateWork, RatingsHistory, FollowUpQueue, ChiefHome, ChiefAnalytics,
│   │   │                        # WardManagement, WardsOfficers, OfficerPerformancePanel, ProtectedImage,
│   │   │                        # NotificationBanner, Community* (analytics, comments, issue card, moderation list), ImpactPanel
│   │   ├── config/             # api.js, routes.js
│   │   ├── context/            # authcontext.jsx, authcontextvalue.jsx
│   │   ├── pages/              # home, about, features, how-it-works, login, register,
│   │   │                        # citizendashboard, report, complaints, complaintdetails,
│   │   │                        # profile, officerdashboard, officercomplaintdetail,
│   │   │                        # chiefofficerdashboard, admindashboard, notfound,
│   │   │                        # community, communityissue
│   │   ├── services/           # api.js, authservice.js, complaintservice.js, notificationservice.js, communityservice.js,
│   │   │                        # resolutionservice.js, performanceservice.js, wardservice.js
│   │   └── utils/               # constants.js, formatDateTime.js, helper.js, roleHome.js, community.js
│   └── package.json
└── backend/
    ├── app.py
    ├── config.py
    ├── seed.py                  # seeds demo Citizen/Officer/Admin accounts
    ├── database/db.py
    ├── models/                  # user.py, complaint.py, civic_issue.py, notification.py, community.py,
    │                             # work_update.py, resolution_review.py, ward.py, performance.py
    ├── routes/                  # auth.py, complaints.py, officers.py, admin.py, notifications.py, community.py,
    │                             # resolution_review.py, wards.py, supervision.py
    ├── services/                # ai_service.py, auth_service.py, complaint_service.py, issue_clustering.py,
    │                             # community_service.py, community_identity.py, impact_score_service.py
    ├── utils/                   # jwt_helper.py, time_helper.py, validators.py
    └── tests/                   # pytest suite (auth, complaints, clustering, community, resolution workflow, wards, supervision, uploads, config)
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
cd backend
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # then fill in SECRET_KEY, JWT_SECRET_KEY, GEMINI_API_KEY
python app.py
```

This starts Flask on `http://127.0.0.1:5001` (override with `PORT`), creates the SQLite database (`instance/civicpulse.db`) on first run, and exposes the API under `/api/...`. Outside `APP_ENV=development`, `config.py` refuses to start unless `SECRET_KEY` and `JWT_SECRET_KEY` are set to real, non-default values (see [Environment and database](#environment-and-database)); it never falls back to a hardcoded secret in production.

### Environment and database

Settings come from `backend/.env` (copy `backend/.env.example`; placeholders only, never commit real values):

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
| `HOST`, `PORT`, `FLASK_DEBUG` | Dev server binding and debug (see comments in `.env.example`) | `127.0.0.1`, `5001`, off |

`.env.example` sets `APP_ENV=development`, which is what allows `SECRET_KEY` and `JWT_SECRET_KEY` to stay blank locally (insecure built-in development defaults, with a logged warning). Without it the app treats the environment as production and refuses to start unless both secrets are real, non-default values.

Complaint photos are validated before they are saved: JPG, PNG or WebP only, content must match the extension, and the size limit is 10 MB (`MAX_UPLOAD_MB`). They are stored in `backend/uploads/` (override with `UPLOAD_FOLDER`) and served at `/uploads/<name>` **without authentication** (unguessable names, but anyone with a link can open them). Staff-only correction photos go to `backend/private_uploads/` instead (override with `PRIVATE_UPLOAD_FOLDER`) and are never served by `/uploads`; both folders are gitignored.

#### Database setup and migrations

There is no separate migration command. When the API starts it creates any missing tables and runs small **additive, idempotent** migrations (see the `migrate_*` functions in `backend/app.py`): new columns, tables, indexes and integrity triggers are added, and existing rows are never deleted or rewritten. A pre-existing prototype `resolution_reviews` table from an earlier schema is renamed to `resolution_reviews_legacy_complaint_level`, not dropped; startup stops with an error if that name is already taken. The database is a local SQLite file, so before upgrading a database that holds data you care about, **copy `backend/instance/civicpulse.db` somewhere safe first**. Never delete it to "fix" a startup error; read the error message instead.


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
| POST | `/api/issues/<id>/work-updates` | Record field work on a civic issue (note, photo, GPS; status Pending / In Progress; idempotency key supported) | JWT (Officer) |
| GET | `/api/issues/<id>/work-updates` | List an issue's field-work log | JWT (Officer/Admin) |
| POST | `/api/issues/<id>/resolution-reviews` | Submit completed work for the whole issue (status becomes Pending Review) | JWT (Officer) |
| GET | `/api/chief-officer/resolution-queue` | Reviews awaiting a decision, plus withdrawn (stale) ones | JWT (Chief Officer) |
| PUT | `/api/chief-officer/resolution-reviews/<id>/decision` | Approve (issue becomes Resolved) or reject with a reason | JWT (Chief Officer) |
| GET | `/api/complaints/<id>/resolution-evidence` | Citizen-safe before/after view of a complaint's issue | JWT |
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

Ward, supervision and follow-up endpoints (`/api/admin/wards...`, `/api/chief-officer/overview|ratings|approved-work|wards|officers|follow-ups...`, `/api/officers/me/ratings|follow-ups...`) are listed with their roles in the table below; the route files are the reference.

| Area | Endpoints | Who |
|---|---|---|
| Resolution workflow | `/api/issues/<id>/work-updates`, `/api/issues/<id>/resolution-reviews`, `/api/chief-officer/resolution-reviews...`, `/api/complaints/<id>/resolution-evidence` | Officer submits; Chief Officer decides; citizen reads a safe evidence view |
| Wards | `/api/admin/wards...` | Admin only |
| Supervision | `/api/chief-officer/overview`, `.../approved-work`, `.../ratings`, `.../wards/<id>`, `.../officers/<id>`, `.../follow-ups...` | Chief Officer only |
| Officer's own records | `/api/officers/me/ratings`, `/api/officers/me/follow-ups...` | Officer only (own records) |
| Correction photos | `/api/chief-officer/follow-ups/<id>/events/<event_id>/image`, `/api/officers/me/follow-ups/<id>/events/<event_id>/image` | Chief Officer; the assigned Officer |

| GET | `/uploads/<filename>` | Serve an uploaded complaint or completion photo (public; staff-only correction photos are never served here) | – |

## Known limitations

- **Photo submission is camera-only.** `CameraCapture.jsx` calls the camera API directly with no file-upload fallback, so the report flow is unusable on a device/browser that denies or lacks camera access.
- **No retry on transient Gemini errors.** A `503` ("model overloaded") from Gemini currently surfaces as a hard failure with no retry.
- **Public photo URLs.** `/uploads/<name>` serves complaint and completion photos without authentication (they are shown to citizens and in the community feed by design). Staff-only correction photos are *not* served there. Staff field-work update photos (`IssueWorkUpdate`) still are, so whether those should also move to authenticated access is an open policy decision.
- **Ward-level work is not available.** Complaints and issues are not linked to wards, so the app cannot attribute work to a ward and says so instead of showing zeros.
- **Open policy decisions:** who may assign the Chief Officer role (today any Admin, via the API), the Officer-to-ward cardinality, municipality-wide Officer access, any SLA/overdue thresholds, and whether Admins may ever see ratings.
- **Notifications do not deep-link** to the related work; they say where to look.
- **Open CORS.** `CORS(app)` in `app.py` currently allows all origins; tighten this before any public deployment.

## Roadmap

- [ ] Merge the integrated branch into `main` after review
- [ ] Confirm the camera-only photo requirement is intentional, or add a fallback
- [ ] Add Gemini failure handling (a transient `503` from the model currently surfaces as a hard submission failure)
- [ ] Reseed/clean leftover test data (Playwright/manual test complaints and users) before any live demo
- [ ] Lightweight CI (run `pytest` + `npm run build` on push)
- [ ] Tighter CORS configuration for a real deployment
- [ ] Build out the rest of Level 2 (community features) beyond the current support/verify/comment/impact-score/moderation slice

Explicitly deferred beyond Level 1/initial Level 2: heatmap polish, RAG, Redis, custom-trained AI, async AI processing, Docker, full production CI/CD, production secrets infrastructure, database migration infrastructure.

## Contributing

1. Branch from the integration branch the team has agreed on, and open a pull request rather than pushing to a shared branch
2. Keep AI prompt logic in `backend/services/ai_service.py` and secrets out of version control (`.env` is gitignored; copy `backend/.env.example`)
3. Run `pytest` (backend) and `npm test`, `npm run lint` and `npm run build` (frontend) before opening a PR

## License

MIT © 2026 Ishaan Pande — see [LICENSE](./LICENSE).
