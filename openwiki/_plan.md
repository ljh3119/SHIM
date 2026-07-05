# OpenWiki plan

## Intended pages
- `quickstart.md` — add links to the new admin workflow and router source map pages.
- `routers/admin-source-map.md` — source map for the main admin router modules and how they are mounted from `src/app/main.py` and `src/app/routers/admin/__init__.py`.
- `workflows/admin.md` — explain the admin workflow, key pages, shared state, audit behavior, and operational constraints.

## Source evidence
- `src/app/main.py` — app startup, router mounting, admin sidebar metrics, exception handling.
- `src/app/routers/admin/__init__.py` — admin page/API router aggregation.
- `src/app/routers/admin/dashboard.py` — dashboard metrics, system health, setup banner.
- `src/app/routers/admin/users.py` — user management, password reset, activation/deactivation, role constraints.
- `src/app/routers/admin/leaves.py` — admin leave timeline/calendar flows and exports.
- `src/app/routers/admin/settings.py` — approval, branding, calendar scope, and time policy settings.
- `src/app/routers/admin/holidays.py` — holiday CRUD.
- `src/app/routers/admin/audit.py` — audit log browsing/export and label normalization.
- `src/app/services/admin_service.py` — query/service layer behind the admin pages.

## Remaining questions
- Whether any additional admin router files are exposed elsewhere outside `src/app/routers/admin/`.
- Whether the admin workflow should mention specific template names or stay at the page/action level only.
