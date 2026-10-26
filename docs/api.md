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
- **Role changes** (`PUT .../role`, body `{"role": "Citizen" | "Officer" | "Chief Officer" | "Admin"}`): only an Admin can change a role, including assigning `Chief Officer` (the Admin screen does not offer that choice yet; use this endpoint). The response is `{"message", "user": {id, name, email, role}}`.
  - **Last Admin**: the last active (non-suspended) Admin cannot be demoted, including by themselves: `409 At least one active Admin must remain. Promote another Admin before demoting this one.` The check and the change are one SQL statement, so two Admins cannot demote each other at the same moment.
  - **Concurrent change**: `409 This user's role changed while you were editing it. Reload and try again.`
  - **Audit**: every applied change is recorded in the append-only `role_changes` table (who, whom, old role, new role, time) in the same transaction. If the record cannot be written, the role is not changed (`500 Could not change the role`). Setting a role a user already has changes nothing and records nothing. Refused or failed requests leave no record.
  - Other errors: `400` missing or invalid role, `403 Admin access required`, `404 User not found`.

---

# Resolution workflow, supervision and wards

These 35 endpoints were added with the issue-wide resolution workflow. They are listed from the source in `backend/routes/resolution_review.py`, `backend/routes/supervision.py` and `backend/routes/wards.py`, plus the citizen evidence endpoints in `backend/routes/complaints.py` (section E). The sections above document the earlier endpoints and may be out of date for fields not listed here.

## Conventions

**Authentication and roles.** Every endpoint needs `Authorization: Bearer <JWT>`. The role is read from the database on every request, never from the token. A request with no token gets `401`. A malformed token gets `422`. A valid token with the wrong role gets `403` and a message naming the required role.

| Prefix | Who may call it | `403` message |
|---|---|---|
| `/api/admin/wards...` | Admin only | `Admin access required` |
| `/api/chief-officer/...` | Chief Officer only. **Admins are refused** | `Chief Officer access required` |
| `/api/officers/me/...` | Officer only. Admins and Chief Officers are refused | `Officer access required` |
| `POST /api/issues/<id>/work-updates`, `POST /api/issues/<id>/resolution-reviews` | Officer or Admin | `Officer or Admin access required` |
| `GET /api/issues/<id>/work-updates`, `GET /api/issues/<id>/resolution-reviews` | Officer, Admin or Chief Officer | `Staff access required` |

Citizens are refused in sections A to D. Section E is the only part they can read, and it is an allow-list. Staff-only data (ratings, explanations, follow-ups, correction photos) is never returned by any citizen endpoint.

**Errors.** Errors are JSON: `{"message": "..."}`. Some add detail, for example `allowed_statuses`. Status codes used: `400` invalid input, `403` wrong role, `404` not found (also used when a record belongs to someone else), `409` the record is not in a state that allows the action or another request changed it first, `500` unexpected failure (the message is generic).

**Paging.** Endpoints marked *paged* accept `limit` (default `50`, minimum `1`, maximum `200`) and `offset` (default `0`). The response includes `total` (the filtered total, not the page size), `limit` and `offset`. A non-numeric value returns `400`.

**Dates.** `from` and `to` are `YYYY-MM-DD`. `to` is inclusive. Any other format returns `400`.

**Times** are ISO-8601 UTC strings.

**Photos.** Uploads accept JPG, PNG or WebP only, checked against the file's real content, up to `MAX_UPLOAD_MB` (default 10).
- **Citizen complaint photos** are public: they come back as `image_url` values under `/uploads/` and need no login.
- **Everything staff-related is private.** Field-work photos, completion evidence and correction photos are stored in the private folder and are returned as `image_path` values, relative to `/api`. They must be fetched with the bearer token (an `<img src>` would not send it, so the web app downloads them and shows them from a temporary object URL). `/uploads` answers `404` for any file that a staff record refers to, even if the file is still in the public folder from before.
- **Completion evidence is private until approval.** Staff can read it in any review state. A citizen can read it only once the review is approved (see section E).
- All private photo responses carry `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`. Every failure (missing record, wrong issue, missing file, unsafe stored name) returns the same `404`, so callers learn nothing about records they cannot see.

---

## A. Field work and resolution review (`/api/issues`, `/api/chief-officer`)

An issue is the group of similar citizen complaints. Work and review happen per issue, not per complaint. Issue statuses are `Pending`, `In Progress`, `Pending Review` and `Resolved`; only an approved review sets `Resolved`.

### A1. Record a field-work update
- **URL**: `/api/issues/<issue_id>/work-updates`
- **Method**: `POST` (multipart/form-data)
- **Auth**: Officer or Admin
- **Required header**: `Idempotency-Key` (1-128 characters). Retrying with the same key and the same content returns the original update instead of creating a duplicate.
- **Fields**: `note` (required); `status` (`Pending` or `In Progress`, default `In Progress`); `complaint_id` (optional, must belong to this issue); `latitude` and `longitude` (optional, must be sent together); `image` (optional; stored privately).
- **Effect**: a `status` of `In Progress` moves the issue to `In Progress`. `Resolved` and `Pending Review` are rejected: only a Chief Officer approval resolves an issue.
- **Response (201)**: `{"message": "Work update recorded", "work_update": {id, issue_id, complaint_id, officer_id, status, note, image_path, latitude, longitude, created_at}}`; `image_path` is `/issues/<issue_id>/work-updates/<id>/image`, or `null` when no photo was attached
- **Response (200)**: same shape with `"message": "Work update already recorded"` when the key and content match an earlier request.
- **Errors**: `400` missing or oversized `Idempotency-Key`, empty `note`, invalid `status` (with `allowed_statuses`), invalid or partial coordinates, a `complaint_id` from another issue, or an invalid image; `404 Issue not found`; `409 Idempotency-Key was already used with a different work update`.

### A2. List an issue's field-work log
- **URL**: `/api/issues/<issue_id>/work-updates`
- **Method**: `GET`
- **Auth**: Officer, Admin or Chief Officer
- **Response (200)**: `{"work_updates": [ ...same objects as A1... ]}`
- **Errors**: `404 Issue not found`.

### A2b. Read a field-work photo
- **URL**: `/api/issues/<issue_id>/work-updates/<update_id>/image`  **Method**: `GET`
- **Auth**: Officer, Admin or Chief Officer (`403` for citizens, `401` without a token)
- **Response (200)**: the image bytes. **Errors**: `404 Photo not found` for an unknown issue or update, an update without a photo, or a missing file.

### A3. Submit completed work for review
- **URL**: `/api/issues/<issue_id>/resolution-reviews`
- **Method**: `POST` (multipart/form-data)
- **Auth**: Officer or Admin
- **Fields**:
  - `completion_note` (required)
  - `image` (required): the final evidence photo
  - `dispositions` (required): a JSON list with exactly one object for each eligible linked complaint, `{"complaint_id": 12, "disposition": "Addressed", "note": "Repaired."}`. `disposition` is `Addressed` or `Duplicate Covered`. `Additional Work Required` is refused with `Complete outstanding work before requesting final review`. Complaints confirmed as spam or out of scope are excluded, and submission is refused while any linked complaint is still awaiting spam moderation.
  - `latitude`, `longitude` (optional, together)
  - `supersedes_review_id` (optional): the Officer's own earlier review of this issue that the new submission replaces (for example after a rejection or a withdrawal)
- **Effect**: the review is created `Pending` and the issue moves to `Pending Review`. Only one review per issue can be `Pending`.
- **Response (201)**: `{"message": "Resolution review submitted", "review": {id, issue_id, submitted_by, completion_note, image_path, latitude, longitude, issue_revision, state, submitted_at, reviewed_by, reviewed_at, rejection_reason, stale_reason, stale_at, supersedes_review_id, dispositions: [{complaint_id, disposition, note, created_at}]}}`
- **Review states**: `Pending`, `Approved`, `Rejected`, `Stale` (withdrawn because new information arrived, not a rejection), `Superseded`.
- **Errors**: `400` missing note or photo, invalid dispositions or coordinates, a submission that does not cover every eligible complaint, an issue with no eligible complaints; `404 Issue not found`; `409 A resolution review is already awaiting Chief Officer decision`, or the issue changed while the request was processed.

### A4. List an issue's reviews and review checklist
- **URL**: `/api/issues/<issue_id>/resolution-reviews`
- **Method**: `GET`
- **Auth**: Officer, Admin or Chief Officer
- **Response (200)**: `{"issue": {...}, "complaints": [...], "review_checklist": [{complaint_id, eligible, blocked_reason, excluded_reason}], "reviews": [ ...review objects as in A3... ]}`. Rejection reasons are included so the Officer can correct the work.
- **Errors**: `404 Issue not found`.

### A4b. Read a completion-evidence photo
- **URL**: `/api/issues/<issue_id>/resolution-reviews/<review_id>/image`  **Method**: `GET`
- **Auth**: Officer, Admin or Chief Officer, in any review state (`Pending`, `Approved`, `Rejected`, `Stale`, `Superseded`). Citizens get `403` here; they use section E.
- **Response (200)**: the image bytes. **Errors**: `404 Photo not found` for a review that does not belong to that issue or a missing file.

### A5. Chief Officer decision queue
- **URL**: `/api/chief-officer/resolution-queue`
- **Method**: `GET`
- **Auth**: Chief Officer
- **Response (200)**: `{"queue": [{"issue": {...}, "review": {...}, "complaints": [...], "review_checklist": [...]}], "stale": [ ... ]}`. `queue` holds reviews awaiting a decision. `stale` holds withdrawn reviews that cannot be approved and are waiting for the Officer to resubmit.

### A6. Decide a review
- **URL**: `/api/chief-officer/resolution-reviews/<review_id>/decision`
- **Method**: `PUT`
- **Auth**: Chief Officer
- **Body**: `{"decision": "Approved"}` or `{"decision": "Rejected", "rejection_reason": "At least ten characters explaining what is missing."}`
- **Effect**: approval resolves the whole issue, records the status change and notifies the reporters. A rejection leaves the issue unresolved; the Officer then submits a replacement.
- **Response (200)**: approval returns `{"message": "Resolution review approved", "review": {...}, "issue": {...}}`. Rejection returns `{"message": "Resolution review rejected"}`.
- **Errors**: `400` decision not `Approved` or `Rejected`, or a rejection reason shorter than 10 characters (`A meaningful rejection reason is required`); `403 The submitting officer cannot decide this review`; `404 Resolution review not found`; `409` the review is already decided, was withdrawn (`Stale`), or new information arrived since it was submitted.

---

## B. Wards (`/api/admin/wards`) - Admin only

Wards are a registry with an append-only assignment history. Complaints and issues are **not** linked to wards, so no ward-level work figures exist. Wards cannot be deleted, only deactivated. Assignment history is never edited or deleted; an assignment can only be ended.

A ward object is `{id, name, code, source, is_active, active_assignment_count, created_at, updated_at, deactivated_at}`.

### B1. List wards
- **URL**: `/api/admin/wards`  **Method**: `GET`  **Auth**: Admin
- **Query**: `active=true` or `active=false` (optional)
- **Response (200)**: `{"wards": [ ... ]}`, active wards first, then by name.

### B2. Create a ward
- **URL**: `/api/admin/wards`  **Method**: `POST`  **Auth**: Admin
- **Body**: `{"name": "Panchavati", "code": "W1", "source": "NMC ward list"}`. `name` is required (max 120). `code` is optional (max 32) and unique ignoring case. `source` is optional (max 255).
- **Response (201)**: `{"message": "Ward created", "ward": {...}}`
- **Errors**: `400 Request body is required` or a validation message; `409 A ward with this code already exists`.

### B3. Update a ward
- **URL**: `/api/admin/wards/<ward_id>`  **Method**: `PUT`  **Auth**: Admin
- **Body**: any of `name`, `code`, `source`. Active state cannot be changed here.
- **Response (200)**: `{"message": "Ward updated", "ward": {...}}`
- **Errors**: `400` including `Use the activate/deactivate endpoints to change a ward's state`; `404 Ward not found`; `409` duplicate code.

### B4. Deactivate a ward / B5. Activate a ward
- **URL**: `/api/admin/wards/<ward_id>/deactivate` and `/api/admin/wards/<ward_id>/activate`
- **Method**: `PUT`  **Auth**: Admin  **Body**: none
- **Response (200)**: `{"message": "Ward deactivated", "ward": {...}}` or `{"message": "Ward activated", "ward": {...}}`
- **Errors**: `404 Ward not found`.

### B6. List a ward's assignment history
- **URL**: `/api/admin/wards/<ward_id>/assignments`  **Method**: `GET`  **Auth**: Admin
- **Response (200)**: `{"ward": {...}, "assignments": [{id, ward_id, officer: {id, name, email, role, is_suspended}, assigned_by, assigned_at, reason, ended_at, ended_by, end_reason, is_active}]}`
- **Errors**: `404 Ward not found`.

### B7. Assign an Officer to a ward
- **URL**: `/api/admin/wards/<ward_id>/assignments`  **Method**: `POST`  **Auth**: Admin
- **Body**: `{"officer_id": 5, "reason": "Initial posting"}`. `reason` is optional (max 500). It is visible to Admins only; Chief Officer views omit it.
- **Response (201)**: `{"message": "Officer assigned", "assignment": {...}}`
- **Errors**: `400` `officer_id must be a whole number`, `Only users with the Officer role can be assigned to a ward`, or `A suspended Officer cannot be assigned to a ward`; `404` ward or Officer not found; `409` the Officer is already actively assigned to this ward, or the ward is inactive.

### B8. End an assignment
- **URL**: `/api/admin/wards/<ward_id>/assignments/<assignment_id>/end`  **Method**: `PUT`  **Auth**: Admin
- **Body**: optional `{"reason": "Reassigned"}`
- **Response (200)**: `{"message": "Assignment ended", "assignment": {...}}`
- **Errors**: `404 Assignment not found`; `409 This assignment has already ended`.

---

## C. Chief Officer supervision (`/api/chief-officer`) - Chief Officer only

Admins receive `403` on every endpoint in this section. This is deliberate: access to ratings, follow-ups and the supervisory overview for Admins needs an explicit policy decision.

### C1. Municipality overview
- **URL**: `/api/chief-officer/overview`  **Method**: `GET`
- **Query** (all optional): `from`, `to`, `ward_id`, `officer_id`. `ward_id` narrows the ward and Officer lists only. `officer_id` narrows Officer-attributed figures. Dates filter event counts, not current-state counts. The response's `filters.applies_to` states what each filter affects.
- **Response (200)**: counts and definitions in these sections: `scope`, `filters`, `generated_at`, `issues`, `complaints`, `reviews`, `work`, `ratings`, `follow_ups`, `officers`, `wards`, `resolution_time`, `trends`, `definitions`. Ward-level work is reported as unavailable. There are no overdue or SLA figures: no policy has been approved, and `definitions.overdue` says so.

### C2. Ward detail
- **URL**: `/api/chief-officer/wards/<ward_id>`  **Method**: `GET`
- **Response (200)**: `{"ward": {id, name, code, is_active, deactivated_at}, "assignments": [...], "active_officer_activity": [...], "note": "..."}`. The Admin's assignment reasons are not included.
- **Errors**: `404 Ward not found`.

### C3. Officer detail
- **URL**: `/api/chief-officer/officers/<officer_id>`  **Method**: `GET` (submissions list is paged)
- **Query**: `state` (one of the review states, optional), `limit`, `offset`
- **Response (200)**: `{"officer": {...}, "wards": [...], "work": {...}, "ratings": {...}, "follow_ups": {"assigned_to_this_officer": {...}, "on_this_officers_work": {...}}, "submissions": {items, total, limit, offset}}`. `work` separates field-work updates and review submissions from the number of unique issues involved.
- **Errors**: `400 Unknown review state` (with `allowed_states`); `404 Officer not found`.

### C4. Approved work awaiting or carrying a rating
- **URL**: `/api/chief-officer/approved-work`  **Method**: `GET` (paged)
- **Query**: `rated=true` or `rated=false`, `officer_id`, `from`, `to`
- **Response (200)**: `{"approved_work": [{resolution_review_id, issue, officer, submitted_at, approved_at, evidence: {completion_note, dispositions, image_path}, rating, follow_up}], total, limit, offset}`

### C5. Rate approved work
- **URL**: `/api/chief-officer/resolution-reviews/<review_id>/rating`  **Method**: `POST`
- **Body**: `{"stars": 4, "explanation": "optional text", "revises_rating_id": 7}`
  - `stars`: a whole number from 1 to 5 (strings, floats and booleans are refused).
  - `explanation`: up to 2000 characters. **Required** for 1 or 2 stars.
  - `revises_rating_id`: required when the work already has a rating, and must be the current rating's id. A revision always needs an `explanation`.
- **Rules**: only approved work can be rated; the rated Officer is taken from the review's submitter, never from the request; ratings are append-only, so a revision adds a new row and marks the earlier one superseded. A 1 or 2 star rating opens one corrective follow-up for the work. A later revision never closes, moves or deletes an existing follow-up, and never changes the issue's status.
- **Response (201)**: `{"message": "Rating saved", "rating": {id, resolution_review_id, issue, rated_officer, rated_by, stars, explanation, needs_follow_up, supersedes_rating_id, is_effective, created_at}, "follow_up": {...} or null}`. The Officer is notified without the explanation text.
- **Errors**: `400` invalid stars, missing explanation, `revises_rating_id must be a whole number`; `403 You cannot rate work you submitted yourself` (this also covers work submitted before the rater became a Chief Officer; the database enforces it too); `404` review not found; `409 Only approved work can be rated`, `This work is already rated; submit a revision of rating <id>`, `There is no earlier rating to revise`, or the rating was revised meanwhile.

### C6. Rating history for one piece of work
- **URL**: `/api/chief-officer/resolution-reviews/<review_id>/ratings`  **Method**: `GET`
- **Response (200)**: `{"ratings": [ ...oldest first... ]}`. **Errors**: `404`.

### C7. List ratings
- **URL**: `/api/chief-officer/ratings`  **Method**: `GET` (paged)
- **Query**: `officer_id`, `stars`, `from`, `to`, `history=true` (include superseded revisions; the default is current ratings only)
- **Response (200)**: `{"ratings": [...], total, limit, offset}`

### C8. List corrective follow-ups
- **URL**: `/api/chief-officer/follow-ups`  **Method**: `GET` (paged)
- **Query**: `status` (`Awaiting Assignment`, `Assigned`, `Correction Submitted`, `Closed`), `assigned_officer_id`, `rated_officer_id`, `stars`
- **Response (200)**: `{"follow_ups": [{id, status, resolution_review_id, issue, rating: {stars, explanation}, rated_officer, assigned_officer, created_at, updated_at, closed_at}], total, limit, offset}`
- **Errors**: `400 Unknown status` (with `allowed_statuses`).

### C9. Follow-up detail
- **URL**: `/api/chief-officer/follow-ups/<follow_up_id>`  **Method**: `GET`
- **Response (200)**: `{"follow_up": {...as C8..., "events": [{id, event_type, from_status, to_status, actor, officer, note, image_path, created_at}]}}`. Event types: `Created`, `Assigned`, `Reassigned`, `CorrectionSubmitted`, `CorrectionReturned`, `Closed`. **Errors**: `404`.

### C10. Assign or reassign a correction
- **URL**: `/api/chief-officer/follow-ups/<follow_up_id>/assign`  **Method**: `PUT`
- **Body**: `{"officer_id": 5, "reason": "optional instructions"}`
- **Rules**: the assignee must hold the Officer role and not be suspended. A ward assignment is not required. Reassigning is allowed until a correction has been submitted.
- **Response (200)**: `{"message": "Follow-up updated", "follow_up": {...}}`. The assignee (and a previous assignee) are notified.
- **Errors**: `400 officer_id must be a whole number`, `Only users with the Officer role can be assigned a correction` or `A suspended Officer cannot be assigned a correction`; `404 Officer not found` or follow-up not found; `409 This Officer is already assigned to the follow-up`, `A follow-up that is '<status>' cannot be (re)assigned` (only `Awaiting Assignment` and `Assigned` cases can be), or `The follow-up changed while assigning; reload and try again`.

### C11. Verify, close or return a correction
- **URL**: `/api/chief-officer/follow-ups/<follow_up_id>/verify`  **Method**: `PUT`
- **Body**: `{"decision": "Close", "note": "optional"}` or `{"decision": "Return", "note": "required: what is still needed"}`
- **Effect**: `Close` ends the case. `Return` sends it back to `Assigned`. Neither changes the issue's resolution status.
- **Response (200)**: `{"message": "Follow-up updated", "follow_up": {...}}`
- **Errors**: `400 A note explaining what is still needed is required to return the correction`; `404`; `409 This follow-up has no submitted correction awaiting verification`.

### C12. Read a correction photo
- **URL**: `/api/chief-officer/follow-ups/<follow_up_id>/events/<event_id>/image`  **Method**: `GET`
- **Response (200)**: the image bytes with its content type, `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`.
- **Errors**: `401` without a token; `403` other roles; `404 Evidence not found` for an unknown follow-up or event, an event that is not a correction, or a missing file (the same answer in every case). The file is chosen only from the stored event; nothing in the request names a file.

---

---

## D. Officer's own records (`/api/officers/me`) - Officer only

An Officer sees only records that belong to them. A record that belongs to someone else returns `404`.

### D1. My ratings
- **URL**: `/api/officers/me/ratings`  **Method**: `GET` (paged)
- **Response (200)**: `{"ratings": [{id, resolution_review_id, issue, stars, explanation, needs_follow_up, supersedes_rating_id, is_effective, created_at, follow_up}], total, limit, offset}`

### D2. My assigned corrections
- **URL**: `/api/officers/me/follow-ups`  **Method**: `GET` (paged)
- **Query**: `status` (as in C8). Open cases are listed before closed ones.
- **Response (200)**: `{"follow_ups": [{id, status, issue, rating, assigned_officer, events, created_at, updated_at, closed_at}], total, limit, offset}`. Events show the actor's role, not the Chief Officer's name.

### D3. One assigned correction, with work context
- **URL**: `/api/officers/me/follow-ups/<follow_up_id>`  **Method**: `GET`
- **Response (200)**: `{"follow_up": {...as D2..., "work": {submitted_at, approved_at, completion_note, image_path, by_this_officer}}}`. **Errors**: `404 Follow-up not found`.

### D4. Submit a correction
- **URL**: `/api/officers/me/follow-ups/<follow_up_id>/submit-correction`  **Method**: `POST` (multipart/form-data)
- **Fields**: `note` (required, max 2000), `image` (optional, validated like other uploads). The photo is stored in the private evidence folder, not the public one.
- **Effect**: the case moves from `Assigned` to `Correction Submitted` and the assigning Chief Officer is notified. Closing it is up to the Chief Officer.
- **Response (200)**: `{"message": "Correction submitted", "follow_up": {...}}`
- **Errors**: `400 note is required` or an invalid image; `404 Follow-up not found` (not assigned to you); `409 This follow-up is not awaiting a correction`; `500` generic.

### D5. Read a correction photo
- **URL**: `/api/officers/me/follow-ups/<follow_up_id>/events/<event_id>/image`  **Method**: `GET`
- Same response and errors as C12, but only for a case currently assigned to the caller. An Officer who was reassigned away loses access.

---

## E. Citizen view of completion evidence (`/api/complaints`)

### E1. Resolution progress for a complaint
- **URL**: `/api/complaints/<complaint_id>/resolution-evidence`  **Method**: `GET`
- **Auth**: the reporting citizen, or an Officer or Admin (the same rule as reading the complaint). Other users get `404`.
- **Response (200)**: `{"evidence": {complaint_id, state, issue_status, before: {image_url, reported_at}, work_submitted_at, returned_at, approved_at, after}}`. `before.image_url` is the citizen's own public report photo. `after` is `null` unless the review is approved: then it is `{"image_path": "/complaints/<id>/resolution-evidence/after-image" | null, "report": "<completion note>"}`. `image_path` is `null` if the file is missing. Rejection reasons, dispositions, GPS and staff identities are never included.

### E2. The approved completion photo
- **URL**: `/api/complaints/<complaint_id>/resolution-evidence/after-image`  **Method**: `GET`
- **Auth**: same as E1.
- **Response (200)**: the image bytes, only when E1 would show the photo: the latest review of the issue is approved, the issue is currently `Resolved`, and the complaint took part in the resolution.
- **Errors**: `401` without a token; `404 Photo not found` in every other case: pending, rejected or stale review, a reopened issue, a report excluded as spam or out of scope, another citizen's complaint, or a missing file. Chief Officers use the staff route (A4b).

---

## Follow-up state machine

| From | Action | To |
|---|---|---|
| (rating of 1-2 stars) | `POST .../rating` | `Awaiting Assignment` |
| `Awaiting Assignment` | C10 assign | `Assigned` |
| `Assigned` | C10 reassign | `Assigned` (another Officer) |
| `Assigned` | D4 submit correction | `Correction Submitted` |
| `Correction Submitted` | C11 `Return` | `Assigned` |
| `Correction Submitted` | C11 `Close` | `Closed` |

Each change is also recorded as an immutable event in the case history.
