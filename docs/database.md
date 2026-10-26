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

---

# Resolution workflow, ratings, follow-ups and wards

The tables below were added with the issue-wide resolution workflow (plus the `role_changes` audit table). They are listed from the models in `backend/models/` and from the schema the application creates, including the indexes and triggers added by the startup migrations. Earlier sections of this file describe only `users` and `complaints`; other tables (`civic_issues`, `notifications`, the community tables) are not described here.

**Conventions.** All timestamps are UTC. "Append-only" means database triggers reject `UPDATE` and `DELETE`. Allowed-value lists are enforced twice: by the API and by database triggers (SQLite cannot add a `CHECK` constraint to an existing table, so triggers give new and upgraded databases the same protection).

## 3. Tables

### Table `wards`
The ward registry. Wards are never deleted.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | Ward ID |
| `name` | String(120) | Not Null | Ward name |
| `code` | String(32) | Unique, nullable | Short code. Unique ignoring case (partial index `uq_wards_code_nocase`, only where `code` is not null) |
| `source` | String(255) | nullable | Where the ward definition came from |
| `is_active` | Boolean | Not Null | Deactivated wards cannot receive new assignments |
| `created_by` | Integer | FK `users.id` | Admin who created it |
| `created_at`, `updated_at` | DateTime | Not Null | |
| `deactivated_at` | DateTime | nullable | Set when deactivated |

Trigger `wards_no_delete` rejects deletes: `Wards cannot be deleted; deactivate them instead`.

### Table `ward_officer_assignments`
Append-only history of which Officer was assigned to which ward. Only the end fields can change, once.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | |
| `ward_id` | Integer | FK `wards.id`, Not Null, indexed | |
| `officer_id` | Integer | FK `users.id`, Not Null, indexed | Must have the Officer role |
| `assigned_by` | Integer | FK `users.id`, Not Null | Admin who made the assignment |
| `assigned_at` | DateTime | Not Null | |
| `reason` | Text | nullable | Admin-only note; hidden from Chief Officer views |
| `ended_at`, `ended_by`, `end_reason` | DateTime, FK `users.id`, Text | nullable | Set when the assignment ends |

Constraints: partial unique index `uq_ward_assignment_active_pair` on `(ward_id, officer_id) WHERE ended_at IS NULL` allows one active assignment per Officer and ward. Triggers: `ward_assignments_officer_only` (`Only Officers can be assigned to a ward`), `ward_assignments_no_delete` and `ward_assignments_immutable_update` (`Ward assignment history is immutable`).

### Table `issue_work_updates`
Field-work log entries for a civic issue.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | |
| `issue_id` | Integer | FK `civic_issues.id`, Not Null, indexed | |
| `complaint_id` | Integer | FK `complaints.id`, nullable, indexed | Optional: the complaint, within this issue, the update concerns |
| `officer_id` | Integer | FK `users.id`, Not Null, indexed | Taken from the token, never the request |
| `status` | String(50) | Not Null | `Pending` or `In Progress` (trigger `issue_work_updates_valid_status_*`: `Invalid work update status`) |
| `note` | Text | Not Null | |
| `image_filename` | String(255) | nullable, indexed | File name of the field-work photo. New files are stored in the private upload folder; rows from before photos became private may still point at a file in the public folder |
| `latitude`, `longitude` | Float | nullable | Always stored as a pair |
| `idempotency_key` | String(128) | nullable | Client retry key |
| `request_fingerprint` | String(64) | nullable | Hash of the request content, used to tell a safe retry from a conflicting reuse of a key |
| `created_at` | DateTime | Not Null, indexed | Server time |

Constraint `uq_issue_work_update_retry` is unique on `(officer_id, idempotency_key)`.

### Table `resolution_reviews`
A request for the Chief Officer to decide that a whole civic issue is resolved. This replaces an earlier complaint-level table of the same name (see Migration behaviour).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | |
| `issue_id` | Integer | FK `civic_issues.id`, Not Null, indexed | |
| `submitted_by` | Integer | FK `users.id`, Not Null, indexed | The Officer who submitted the work |
| `completion_note` | Text | Not Null | |
| `image_filename` | String(255) | Not Null, indexed | Final evidence photo. Private (see the note on field-work photos) |
| `latitude`, `longitude` | Float | nullable | |
| `issue_revision` | Integer | Not Null | The issue's `review_revision` when submitted; used to detect that new information arrived |
| `state` | String(20) | Not Null, indexed | `Pending`, `Approved`, `Rejected`, `Stale`, `Superseded` (trigger `resolution_reviews_valid_state_*`) |
| `submitted_at` | DateTime | Not Null, indexed | |
| `reviewed_by`, `reviewed_at` | FK `users.id`, DateTime | nullable | Set by the decision |
| `rejection_reason` | Text | nullable | Required (10+ characters) when rejected |
| `stale_reason`, `stale_at` | Text, DateTime | nullable | Why a review was withdrawn |
| `supersedes_review_id` | Integer | FK `resolution_reviews.id`, nullable, indexed | The earlier review this one replaces |

Partial unique index `uq_resolution_reviews_pending_issue` on `(issue_id) WHERE state = 'Pending'` allows one pending review per issue. `Stale` means withdrawn because new information arrived; it is not a rejection.

### Table `resolution_review_complaint_dispositions`
What the Officer says happened to each linked complaint. Append-only.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | |
| `resolution_review_id` | Integer | FK `resolution_reviews.id`, Not Null, indexed | |
| `complaint_id` | Integer | FK `complaints.id`, Not Null, indexed | |
| `disposition` | String(40) | Not Null | `Addressed`, `Duplicate Covered` or `Additional Work Required` (the API accepts only the first two when submitting) |
| `note` | Text | Not Null | |
| `created_at` | DateTime | Not Null | |

Constraint `uq_review_complaint_disposition` is unique on `(resolution_review_id, complaint_id)`. Triggers `resolution_dispositions_immutable_*` reject updates and deletes: `Resolution review dispositions are immutable`.

### Table `resolution_ratings`
Chief Officer ratings of approved work. Append-only: a revision is a new row that points at the one it replaces.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | |
| `resolution_review_id` | Integer | FK `resolution_reviews.id`, Not Null, indexed | The approved work being rated |
| `rated_officer_id` | Integer | FK `users.id`, Not Null, indexed | Copied from the review's submitter |
| `rated_by` | Integer | FK `users.id`, Not Null | The Chief Officer |
| `stars` | Integer | Not Null | 1 to 5 |
| `explanation` | Text | nullable | Required for 1 or 2 stars, and for every revision |
| `needs_follow_up` | Boolean | Not Null | True exactly when `stars` is 1 or 2 |
| `supersedes_rating_id` | Integer | FK `resolution_ratings.id`, nullable | The earlier rating this one revises |
| `created_at` | DateTime | Not Null, indexed | |

Constraints: partial unique indexes `uq_rating_one_original` (one original per review: `WHERE supersedes_rating_id IS NULL`) and `uq_rating_one_revision` (at most one revision of any rating: `WHERE supersedes_rating_id IS NOT NULL`). The current rating of a review is the one no other rating supersedes. Triggers: `resolution_ratings_stars_range` (`Rating must be between 1 and 5 stars`), `resolution_ratings_low_needs_explanation`, `resolution_ratings_follow_up_flag`, `resolution_ratings_chief_only` (`Only a Chief Officer can rate work`), `resolution_ratings_approved_only` (`Only approved work can be rated`), `resolution_ratings_submitter_only`, `resolution_ratings_no_self_rating` (`A Chief Officer cannot rate work they submitted themselves`, which also covers work submitted before the rater was promoted), and `resolution_ratings_immutable_update` / `_delete` (`Rating history is immutable; submit a revision`).

### Table `resolution_follow_ups`
One corrective case per rated job.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | |
| `resolution_review_id` | Integer | FK `resolution_reviews.id`, Unique, Not Null | At most one case per approved job |
| `rating_id` | Integer | FK `resolution_ratings.id`, Not Null | The rating that opened the case |
| `issue_id` | Integer | FK `civic_issues.id`, Not Null, indexed | |
| `status` | String(30) | Not Null, indexed | `Awaiting Assignment`, `Assigned`, `Correction Submitted`, `Closed` (trigger `resolution_follow_ups_valid_status_*`) |
| `assigned_officer_id` | Integer | FK `users.id`, nullable, indexed | |
| `created_by` | Integer | FK `users.id`, Not Null | The Chief Officer who rated |
| `created_at`, `updated_at` | DateTime | Not Null | |
| `closed_at` | DateTime | nullable | |

Triggers: `resolution_follow_ups_no_delete` (`Follow-up cases cannot be deleted`) and `resolution_follow_ups_frozen_links` (`A follow-up case cannot be re-linked`: the review, rating and issue never change). Closing a case does not change the issue's status, and a rating revision never closes, moves or deletes a case.

### Table `resolution_follow_up_events`
Immutable history of each follow-up case.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | |
| `follow_up_id` | Integer | FK `resolution_follow_ups.id`, Not Null, indexed | |
| `event_type` | String(30) | Not Null | `Created`, `Assigned`, `Reassigned`, `CorrectionSubmitted`, `CorrectionReturned`, `Closed` |
| `from_status` | String(30) | nullable | |
| `to_status` | String(30) | Not Null | One of the follow-up statuses |
| `actor_id` | Integer | FK `users.id`, Not Null | Who did it |
| `officer_id` | Integer | FK `users.id`, nullable | The Officer concerned (assignee or submitter) |
| `note` | Text | nullable | Instructions, correction note or verification note |
| `image_filename` | String(255) | nullable, indexed | Correction photo. Stored in the **private** upload folder, never the public one |
| `created_at` | DateTime | Not Null | |

Triggers: `resolution_follow_up_events_immutable_update` / `_delete` (`Follow-up history is immutable`) and value guards on `event_type` and `to_status`.

### Table `role_changes`
Append-only audit trail of Admin role changes. A row is written in the same transaction as the change; if it cannot be written, the role does not change. Refused, failed and no-op requests leave no row.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | Integer | Primary Key | |
| `target_user_id` | Integer | FK `users.id`, Not Null, indexed | The user whose role changed |
| `changed_by` | Integer | FK `users.id`, Not Null, indexed | The Admin who made the change |
| `old_role` | String(20) | Not Null | |
| `new_role` | String(20) | Not Null | `Citizen`, `Officer`, `Chief Officer` or `Admin` |
| `created_at` | DateTime | Not Null, indexed | Server time, UTC |

Triggers `role_changes_immutable_update` and `role_changes_immutable_delete` reject changes: `Role change history is immutable`. The last active Admin cannot be demoted: the rule is enforced by the role-change endpoint in a single SQL statement (see `docs/api.md`), not by a trigger.

## 4. Changes to existing tables

- `civic_issues.review_revision` (Integer, Not Null, default `1`): incremented atomically whenever information relevant to a pending review changes (for example a new complaint joins the issue). A review whose `issue_revision` no longer matches becomes `Stale`.
- `civic_issues` status is limited by trigger (`civic_issues_valid_status_*`) to `Pending`, `In Progress`, `Pending Review`, `Resolved`.
- No columns were added to `users` or `complaints` by this change.
- Indexes `ix_issue_work_updates_image_filename`, `ix_resolution_reviews_image_filename` and `ix_resolution_follow_up_events_image_filename` support the check that keeps `/uploads` from serving files that staff records refer to.

## 5. Relationships

```
civic_issues (1) --< (N) issue_work_updates
civic_issues (1) --< (N) resolution_reviews --< (N) resolution_review_complaint_dispositions >-- (1) complaints
resolution_reviews (1) --< (N) resolution_ratings            (a revision points at the rating it replaces)
resolution_reviews (1) --- (0..1) resolution_follow_ups --< (N) resolution_follow_up_events
resolution_ratings (1) --- (0..1) resolution_follow_ups      (the rating that opened the case)
wards (1) --< (N) ward_officer_assignments >-- (1) users     (Officer)
```

Complaints and issues are **not** linked to wards. Ward-level work figures therefore do not exist. Foreign keys are enforced on every SQLite connection (`PRAGMA foreign_keys=ON`).

## 6. Migration behaviour

There is no migration command. When the API starts it runs `db.create_all()` and then small additive, idempotent functions in `backend/app.py` (`migrate_legacy_resolution_reviews_table`, `migrate_resolution_workflow_schema`, `migrate_ward_registry_schema`, `migrate_performance_schema`, `migrate_role_change_schema`, `migrate_upload_reference_indexes`):

- New tables are created. Existing tables only gain columns, indexes and triggers; no existing row is rewritten or deleted, and running startup again changes nothing.
- An older complaint-level `resolution_reviews` table (columns `complaint_id`, `decision`, `rejection_note`) is **renamed** to `resolution_reviews_legacy_complaint_level` with its rows and data intact, before the new table is created. Startup stops with an error rather than overwrite if that name is already taken or the table has an unrecognised layout. The application does not read the legacy table. The older `complaint_work_updates` table is left as it is and is also not read.
- Triggers and partial indexes are SQLite-specific. The migration functions return without doing anything for any other `DATABASE_URL`, so on another database engine the tables are created but these database-level guards are not.
- Copy `backend/instance/civicpulse.db` before upgrading a database you care about.

## 7. Photo storage and the legacy-photo migration tool

| Photo | Column | Folder for new uploads | Who can read it |
|---|---|---|---|
| Citizen complaint photo | `complaints.image_filename` | public (`UPLOAD_FOLDER`) | anyone with the link, via `/uploads` |
| Field-work photo | `issue_work_updates.image_filename` | private (`PRIVATE_UPLOAD_FOLDER`) | staff, via an authenticated endpoint |
| Completion evidence | `resolution_reviews.image_filename` | private | staff in any state; citizens only after approval, via the complaint evidence endpoint |
| Correction photo | `resolution_follow_up_events.image_filename` | private | the Chief Officer and the assigned Officer |

Files uploaded before photos became private sit in the public folder. They keep working (the endpoints fall back to the public folder), and `/uploads` refuses to serve them. The database stores only the file name, so no row changes when a file is moved. `backend/scripts/private_photo_migration.py` moves them reversibly:

1. `report`: read-only classification of every reference (`private-only`, `public-only`, `both-identical`, `both-different`, `missing`, `unsafe-name`, `shared-with-complaint-photo`). Exits with status 2 if anything cannot be mapped safely.
2. `copy --apply`: copies `public-only` files to the private folder and verifies a SHA-256 hash. It never overwrites an existing file and leaves the originals in place.
3. `verify`: every present file must be in the private folder. Files that exist nowhere are listed as already missing; `--strict` makes them fail.
4. `quarantine --apply`: moves the now-redundant public copies to a quarantine folder (nothing is deleted); refuses unless everything is safely mapped.
5. `restore --apply`: moves quarantined files back (the rollback).

The tool opens the database read-only and never writes to it. Every step is a dry run unless `--apply` is given.
