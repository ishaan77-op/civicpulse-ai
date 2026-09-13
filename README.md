# CivicPulse AI

**AI-powered municipal complaint intelligence platform** — citizens report civic issues with a photo and a pinned location, and an AI engine automatically classifies, prioritizes, and routes each report to the right municipal department.

<p>
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Frontend" src="https://img.shields.io/badge/frontend-React%2019%20%2B%20Vite-61dafb">
  <img alt="Backend" src="https://img.shields.io/badge/backend-Flask-black">
  <img alt="AI" src="https://img.shields.io/badge/AI-Google%20Gemini-4285F4">
</p>

---

## About

CivicPulse AI is a civic-tech platform for municipal complaint management. Citizens submit issues such as potholes, garbage overflow, water supply problems, faulty streetlights, or drainage blockages — with a description, an optional photo, and a location picked on a map. A Gemini-powered AI service reads the text and image together and returns a structured analysis (category, priority, responsible department, a short visual observation, and a summary), which is attached to the complaint automatically. Municipal officers then work a triaged queue and update status, while admins get a dashboard with resolution rates and category/department/priority breakdowns.

The current pilot location baked into the map component is **Nashik, India**, though the app is designed to generalize to other municipalities.

## ⚠️ Project status

This repository is under active, branch-based development by a small team, and **the `main` branch currently reflects an early scaffold**, not the full application described below.

- `main` contains the initial Vite + React frontend skeleton (folder structure, routing dependency installed, mostly empty placeholder files) and stub `docs/` files. There is no `backend/` directory on `main` yet.
- The functionality described in this README — the Flask API, the AI complaint-analysis engine, JWT auth, the map picker, and the role-based dashboards — lives on unmerged feature branches:

| Branch | Focus |
|---|---|
| `ai-engine` | Gemini-based complaint analysis service (`backend/services/ai_service.py`) |
| `backend-auth` | Flask API skeleton, JWT auth, user model |
| `backend-complaints` | Complaint model, complaint CRUD routes |
| `feature/user-model` | User schema and role handling |
| `feature/frontend-routing` | Frontend routing wired to backend APIs, backend test suite |
| `feature/member4-integration-maps` | Leaflet-based location picker, marketing pages (About, Features, How it Works) |

This README documents the project as a whole so it's useful both as a map of what's implemented where and as the target `README.md` once the branches above are merged into `main`. Sections below note where something is not yet on `main`.

## Key features

**Citizen**
- Register / log in (JWT-based auth, bcrypt-hashed passwords)
- Submit a complaint with title, description, category, an optional photo, and a location picked on an interactive map
- Track the status of submitted complaints (`Pending` → `In Progress` → `Resolved`)

**AI engine**
- Sends each complaint's text (and image, if provided) to Google Gemini
- Returns structured JSON: `category`, `priority`, `department`, `visual_observation`, `summary`
- Categories: Road Infrastructure, Garbage and Waste, Water Supply, Street Lighting, Drainage, Public Safety, Other
- Priorities: Low, Medium, High, Critical

**Officer**
- Queue of all complaints, filterable by status, category, priority, and department
- Update a complaint's status
- Quick stats (total / pending / in progress / resolved)

**Admin**
- Platform-wide analytics: totals, resolution rate, and breakdowns by category, department, and priority
- User list and role management (promote/demote Citizen / Officer / Admin)

*(All items above are implemented on feature branches; none are merged into `main` yet.)*

## Tech stack

**Frontend** — `frontend/`
- React 19 + Vite
- React Router v7
- Tailwind CSS v4
- Axios for API calls
- React-Leaflet + Leaflet for the map/location picker

**Backend** — `backend/` (feature branches only)
- Flask 3 + Flask-CORS
- Flask-SQLAlchemy (SQLite by default) for the User and Complaint models
- Flask-JWT-Extended for authentication, bcrypt for password hashing
- `google-genai` (Gemini) for AI complaint analysis
- pytest-based test suite (`backend/tests/`, on `feature/frontend-routing`)

## Repository structure

```
civicpulse-ai/
├── docs/                     # api.md, database.md, requirements.md, meeting-log.md (currently empty)
├── frontend/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/       # Navbar, Footer, Button, Card, Input, Loader, ProtectedRoute, MapPicker*
│   │   ├── config/           # api.js, routes.js
│   │   ├── context/          # authcontext.jsx
│   │   ├── pages/            # home, login, register, citizen/officer/admin dashboards, notfound
│   │   ├── routes/           # AppRoutes.jsx
│   │   ├── services/         # api.js, authservice.js, complaintservice.js
│   │   └── utils/
│   └── package.json
└── backend/*                 # Flask API — see "Project status" (not yet on main)
    ├── app.py
    ├── config.py
    ├── database/db.py
    ├── models/                # user.py, complaint.py
    ├── routes/                # auth.py, complaints.py, officers.py, admin.py
    ├── services/              # ai_service.py, auth_service.py, complaint_service.py
    └── utils/                 # jwt_helper.py, validators.py
```
`*` = only present on feature branches, not on `main`.

## Getting started

### Prerequisites
- Node.js 18+ and npm
- Python 3.10+ (for the backend, once you check out a branch that includes it)
- A Google Gemini API key (for AI-powered complaint analysis)

### Frontend (available on `main`)

```bash
git clone https://github.com/ishaan77-op/civicpulse-ai.git
cd civicpulse-ai/frontend
npm install
npm run dev
```

This runs the Vite dev server. Note that on `main` today, `App.jsx` still shows the default Vite/React starter page — the actual CivicPulse pages, routes, and API wiring live on `feature/frontend-routing` and `feature/member4-integration-maps`.

### Backend (currently only on feature branches, e.g. `ai-engine`)

```bash
git checkout ai-engine
cd backend
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Create a `backend/.env` file with:

```
GEMINI_API_KEY=your_gemini_api_key
```

Run the API:

```bash
python app.py
```

This starts Flask on `http://127.0.0.1:5000`, creates the SQLite database (`civicpulse.db`) on first run, and exposes the API under `/api/...`.

> `config.py` currently hardcodes `SECRET_KEY` and `JWT_SECRET_KEY` for local development — swap these for environment variables before deploying anywhere public.

## API overview

*(from the `backend-*` and `feature/frontend-routing` branches)*

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
| GET | `/api/officers/complaints` | Filterable complaint queue | JWT (Officer/Admin) |
| GET | `/api/officers/stats` | Quick status counts | JWT (Officer/Admin) |
| GET | `/api/admin/analytics` | Platform-wide analytics and breakdowns | JWT (Admin) |
| GET | `/api/admin/users` | List all users | JWT (Admin) |
| PUT | `/api/admin/users/<id>/role` | Change a user's role | JWT (Admin) |

A full `docs/api.md` reference is planned but currently empty.

## Roadmap

- [ ] Merge `feature/user-model`, `backend-auth`, `backend-complaints`, and `ai-engine` into `main` so the backend actually ships
- [ ] Merge `feature/frontend-routing` and `feature/member4-integration-maps` for a working, routed frontend
- [ ] Replace the placeholder Vite starter page in `App.jsx` on `main`
- [ ] Fill in `docs/requirements.md`, `docs/api.md`, `docs/database.md`
- [ ] Move hardcoded secrets in `backend/config.py` to environment variables
- [ ] Expand automated test coverage (a start exists in `backend/tests/`)

## Contributing

This is a small team project (branch names like `feature/member4-integration-maps` reflect per-member feature branches). If you're contributing:

1. Branch from `main` using the existing convention (`feature/<name>`, `backend-<area>`, etc.)
2. Keep AI prompt logic in `backend/services/ai_service.py` and secrets out of version control (`.env` is already gitignored)
3. Open a PR into `main` once your feature branch is stable

## License

MIT © 2026 Ishaan Pande — see [LICENSE](./LICENSE).
