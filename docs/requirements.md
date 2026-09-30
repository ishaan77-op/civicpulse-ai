# CivicPulse AI — System Requirements & Specifications

## 1. Functional Requirements

### Citizen Portal
- **FR-1.1 Account Management**: Users can register an account, sign in securely, and view profile details.
- **FR-1.2 Auto Sign-in**: Registration automatically issues JWT tokens and signs in the user.
- **FR-1.3 Issue Filing**: Citizens can file civic complaints with title, description, interactive Leaflet map coordinates, and optional photo attachment.
- **FR-1.4 Complaint Tracking**: Citizens can view a chronological list of their filed issues and track real-time status updates (`Pending` -> `In Progress` -> `Resolved`).
- **FR-1.5 AI Insights**: Citizens can view Gemini AI triage details (assigned priority, suggested department, and visual observation).

### Officer Hub
- **FR-2.1 Municipal View**: Officers can view all complaints filed across the municipality.
- **FR-2.2 Multi-Filter Triage**: Officers can filter issues by status (`Pending`, `In Progress`, `Resolved`), category, priority, and department.
- **FR-2.3 Status Operations**: Officers can update complaint status directly with instant UI reflect.
- **FR-2.4 Workload Overview**: Officers can view aggregate KPI statistics for assigned issues.

### Admin Intelligence
- **FR-3.1 Platform Analytics**: Admins can view executive metrics (total complaints, resolution rate %, pending workloads).
- **FR-3.2 Category & Dept Breakdown**: Visual bar distributions of complaints by category, department, and priority.
- **FR-3.3 User Role Directory**: Admins can promote users to `Officer` or `Admin` roles.

---

## 2. Non-Functional Requirements

- **NFR-1 Security**: Passwords hashed with `bcrypt`. API authenticated using JWT tokens with 1-day expiration. Environment variable based secret management.
- **NFR-2 Performance**: Fast SPA rendering with Vite + React 19. Gemini AI calls optimized with Gemini 3.6 Flash.
- **NFR-3 Responsive Design**: Seamless layout scaling from mobile viewports (320px) up to ultra-wide desktop displays (1440px+).
- **NFR-4 Data Persistence**: Uploaded complaint photos permanently stored in `uploads/` and served via static route.
