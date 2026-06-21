# SHIM (쉼) - 연차 관리 시스템 Project Instructions

## 1. Project Overview & Philosophy
SHIM is a FastAPI-based leave management system designed specifically for closed/internal networks, short-term project teams, and multi-company consortiums.
- **Core Identity**: A "Visibility Tool" focused on answering "Who is available for work today?" rather than a heavy HR ERP.
- **Field-Oriented**: Offline-first, Zero-Configuration. Designed to run portably on Windows PCs or via simple Docker containers without complex DB server setups.
- **Out of Scope (Do Not Implement)**: Payroll/HR integration, complex multi-step approval workflows, and migration to heavy RDBMS (MySQL, PostgreSQL).

## 2. Architecture & Technology Stack
- **Backend**: FastAPI with **Synchronous Routing Policy**.
  - **Standard Router Rule**: For standard CRUD and DB-heavy APIs, define endpoints using synchronous `def` (not `async def`) to let FastAPI handle synchronous SQLAlchemy DB operations in threadpools.
  - **Async Routing Exceptions**: If non-blocking I/O (e.g., websockets, streaming, external HTTP calls) is required, `async def` may be used. However, any synchronous DB queries inside async endpoints must be explicitly wrapped in threadpools (e.g., using `run_in_threadpool`).
- **Database**: SQLite with WAL (Write-Ahead Logging) mode and `PRAGMA foreign_keys=ON;` enforced. Located at `var/data/shim_internal.db`.
- **Frontend & Templates (DRY)**: Server-side rendering using Jinja2 templates (`src/templates`).
  - **Shared Macros**: Common formatting macros (e.g. `fmt_hours`) must be defined centrally in `src/templates/partials/macros.html` and imported explicitly where needed (`{% from "partials/macros.html" import fmt_hours %}`) rather than hardcoded.
  - **Safety Filter**: Ensure formatting macros handle Null or empty string (`""`) values safely using default filters (e.g., `v | default(0) | float`) to prevent 500 Internal Server Errors and blank screens.
- **Styling**: Tailwind CSS v4 using the custom **"Dense UI"** design system (`src/static/css/app.css`). **No external CDNs allowed.**
- **Security & PII (Personally Identifiable Information)**:
  - **Stateless JWT**: Stored in HttpOnly Cookies. SameSite and Secure flags must adapt dynamically to HTTPS detection.
  - **PII Encryption**: Sensitive data (such as user names, leave reasons, and rejection reasons) must be encrypted using `EncryptedString` (Fernet-based symmetric encryption).
  - **Flexible Fallback & Verification**: Under zero-configuration or local development setups, fallback to plaintext when cryptography keys are unconfigured. The application must enforce a fail-fast startup check if key mismatch compromises production data integrity.

## 3. Business Logic & RBAC (Role-Based Access Control)
- **Roles**:
  - `STAFF`: Standard user.
  - `TEAM_LEAD`: Approves requests for their team (based on company/team name matching). Cannot self-approve.
  - `PM`: Has global visibility and approval rights across all teams. PM's own leave requests are **auto-approved**.
  - `ADMIN`: System administrator (Master settings, auditing, user management).
- **Leave Deduction Engine**: Precision time deduction based on 30/60/120-minute boundaries, automatically excluding lunch hours.
- **Bulk Request & Time Omission**:
  - **Bulk Request**: Process list of dates in a single database transaction. Rollback entirely if any validation fails (All-or-Nothing). Skip weekends and public holidays automatically.
  - **Time Omission (Auto Full-day)**: Allow blank start/end times for seamless date-only selections. Map them to default work hours.
- **User-Initiated Cancellation**: STAFF can self-cancel their requests only when in `PENDING` state (transitioning status to `CANCELED`).
- **Session Expiry (token_version)**: User changes (disable status, role changes, password updates) must increment `token_version` in the database to instantly invalidate old JWT tokens.

## 4. AI & Developer Maintenance Standards (CRITICAL)
- **No Stack Changes**: Do not migrate away from FastAPI or SQLite. 
- **No External Dependencies**: Never add external CDN links or APIs to support completely closed/offline networks.
- **Dense UI Integrity**: Strictly adhere to the existing Dense UI tokens (`dense-*`), compact grid layouts, and dynamic HSL-based Company/Team badge styling. Retain responsive responsiveness (using Tailwind `sm:` or `md:`) for small screens.
- **Audit Logging & Snapshots**: Log significant state modifications in `AuditLogs`. Ensure log integrity by taking snapshots of actor details (`actor_name`, `actor_department`) via event listeners to keep audits readable even after user accounts are deleted.
- **Foreign Key Safety**: Always pre-fetch data or update references (e.g., set `actor_id` to NULL in `AuditLogs`) before hard-deleting records to prevent database constraint exceptions.
- **Security & Authorization**: Unify route authorization through FastAPI's dependency injection (`Depends`) from `src/app/dependencies.py`.
- **Performance & N+1 Prevention**:
  - Solve N+1 queries by retrieving parent/child records in bulk (using `in_` queries) and mapping them in memory instead of executing queries in loops.
  - For large Excel exports, use openpyxl's `Workbook(write_only=True)` to stream rows sequentially. Convert numbers and dates to native python objects and assign explicit Excel number formats.
- **Portable Windows & Cross-Platform Safety**:
  - Windows-specific features (MD5 hash-based Mutex, ctypes system tray menu, child process self-forking, and `signal.CTRL_BREAK_EVENT` graceful shutdown) must be encapsulated. 
  - Ensure Win32-specific imports do not raise errors on Linux/Docker environments.
  - Call `database.engine.dispose()` on server shutdown inside the FastAPI lifespan context manager to clean up WAL locks.
- **API Call & Scheduler Performance**:
  - **Notification Polling Guard**: Poll notifications only when the browser tab is active (using Page Visibility API) and enforce throttle/debounce parameters to prevent API call spikes.
  - **Chunked Database Deletion**: Cron scheduler cleanups (e.g., removing expired notifications) must delete records in chunks (e.g. 100 rows per loop) with a small sleep delay (e.g., 0.1s) to avoid WAL database lock contention.

## 5. Strict Documentation Boundaries
Maintaining the documentation structure is mandatory for project integrity:
- **Version Source of Truth**: `package.json` and the root `README.md` must always reflect the exact current version. Use `.\tools\scripts\release.ps1` to sync.
- **Past vs. Future**: 
  - **Future tasks/Backlog** belong ONLY in `docs/3-1_향후_개선계획.md`.
  - **Completed work/Release Ledger** belong ONLY in `docs/2-1_운영_릴리즈_통합_산출물.md`. Do not keep completed tasks in the 3-1 backlog.
- **Architecture State**: `docs/4-1_SHIM_프로젝트_설계서.md` must only describe the **current** state of the system, not its history.
- **Internal Dev Memos**: Unofficial tweaks and developer notes go to `docs/1-4_작업_로그.md`.

## 6. Directory Structure
- `src/app/`: Core FastAPI application (routers, services, models, dependencies).
- `src/templates/` & `src/static/`: Frontend assets.
- `tools/scripts/`: Utility scripts (Dev, Test, Backup, Release, Verification, Seeding).
- `infra/docker/`: Dockerfiles and compose configs.
- `portable/`: Scripts for building the zero-dependency Windows executable bundle.
- `docs/`: Centralized documentation (indexed in `docs/0_문서_인덱스.md`).

## 7. Standard Workflows
- **Local Dev Server**: 
  ```powershell
  npm run dev
  # or
  .\tools\scripts\dev.ps1
  ```
- **Testing & Seeding**:
  - Run `python tools/scripts/seed_test_data.py` to populate the database with realistic test data for development.
  - Run integration/scenario tests before any release.
  ```powershell
  python tools/scripts/run_remaining_tests.py
  ```
  - Verify shutdown and daemon stability:
  ```powershell
  python tools/scripts/test_graceful_shutdown.py
  python tools/scripts/test_duplicate_execution.py
  ```
- **Releasing**: Always run the release script to verify version sync and build artifacts.
  ```powershell
  .\tools\scripts\release.ps1 -Version X.Y.Z -BuildImage -RunChecks
  ```
