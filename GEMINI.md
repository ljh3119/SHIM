# SHIM (쉼) - 연차 관리 시스템 Project Instructions

## 1. Project Overview & Philosophy
SHIM is a FastAPI-based leave management system designed specifically for closed/internal networks, short-term project teams, and multi-company consortiums.
- **Core Identity**: A "Visibility Tool" focused on answering "Who is available for work today?" rather than a heavy HR ERP.
- **Field-Oriented**: Offline-first, Zero-Configuration. Designed to run portably on Windows PCs or via simple Docker containers without complex DB server setups.
- **Out of Scope (Do Not Implement)**: Payroll/HR integration, complex multi-step approval workflows, and migration to heavy RDBMS (MySQL, PostgreSQL).

## 2. Architecture & Technology Stack
- **Backend**: FastAPI (Async routing with synchronous SQLAlchemy DB calls).
- **Database**: SQLite with WAL (Write-Ahead Logging) mode enabled. Located at `var/data/shim_internal.db`.
- **Frontend**: Server-side rendering using Jinja2 templates (`src/templates`).
- **Styling**: Tailwind CSS v4 using the custom **"Dense UI"** design system (`src/static/css/app.css`). **No external CDNs allowed.**
- **Security**: Stateless JWT authentication stored in HttpOnly Cookies. `SHIM_SECRET_KEY` is required.

## 3. Business Logic & RBAC (Role-Based Access Control)
- **Roles**:
  - `STAFF`: Standard user.
  - `TEAM_LEAD`: Approves requests for their team (based on company/team name matching). Cannot self-approve.
  - `PM`: Has global visibility and approval rights across all teams. PM's own leave requests are **auto-approved**.
  - `ADMIN`: System administrator (Master settings, auditing, user management).
- **Leave Deduction Engine**: Precision time deduction based on 30/60/120-minute boundaries, automatically excluding lunch hours.
- **Single-Line Approval**: The system intentionally avoids multi-step approvals.

## 4. AI & Developer Maintenance Standards (CRITICAL)
- **No Stack Changes**: Do not migrate away from FastAPI or SQLite.
- **No External Dependencies**: Because this targets closed networks, never add CDN links or external APIs.
- **Dense UI Integrity**: When adding new UI components, strictly adhere to the existing Dense UI tokens (`dense-*`) and layout structures.
- **Audit Logging**: Any significant state changes (user updates, leave deletions, system setting changes) MUST be logged in the `AuditLogs` table.
- **Race Conditions**: Be cautious with SQLite concurrency; pre-fetch necessary data before deleting records to avoid foreign key/reference errors.

## 5. Strict Documentation Boundaries
Maintaining the documentation structure is mandatory for project integrity:
- **Version Source of Truth**: `package.json` and the root `README.md` must always reflect the exact current version. Use `.\tools\scripts\release.ps1` to sync.
- **Past vs. Future**: 
  - **Future tasks/Backlog** belong ONLY in `docs/3-1_향후_개선계획.md`.
  - **Completed work/Release Ledger** belongs ONLY in `docs/2-1_운영_릴리즈_통합_산출물.md`. Do not keep completed tasks in the 3-1 backlog.
- **Architecture State**: `docs/4-1_SHIM_프로젝트_설계서.md` must only describe the **current** state of the system, not its history.
- **Internal Dev Memos**: Unofficial tweaks and developer notes go to `docs/1-4_작업_로그.md`.

## 6. Directory Structure
- `src/app/`: Core FastAPI application (routers, services, models).
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
- **Releasing**: Always run the release script to verify version sync and build artifacts.
  ```powershell
  .\tools\scripts\release.ps1 -Version X.Y.Z -BuildImage -RunChecks
  ```
