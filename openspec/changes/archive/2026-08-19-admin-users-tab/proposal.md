# Proposal: Admin Users Tab

## Why

Admins currently have no way to see who is on the platform. The admin UI has
tabs for Products, Deployments, and Plans, but no view of the users themselves.
Operators need to answer "who has an account, when did they join, how many
deployments do they run?" without hitting the database directly.

## What Changes

- Add a fourth admin tab, "Users", at route `/admin/users`, alongside the
  existing Products, Deployments, and Plans tabs.
- The tab renders a table of all users (from the existing admin-only
  `GET /api/users`) with the user's id, email, admin status, and join date.
- The table is paginated, sortable, and searchable, all client-side, using the
  same MUI DataGrid pattern as the existing Deployments tab. Search matches on
  email (the `User` model has no username field).
- Each row shows the number of deployments the user has. Counts are derived
  client-side from the existing admin `GET /api/deployments` endpoint, which
  already excludes deleted deployments and embeds the owning user.
- No API, CLI, or database changes. Both endpoints and the UI `User` type
  already exist; `listUsers()` in `ui/src/api/endpoints.ts` is currently unused
  and will now be consumed.
- Server-side pagination/sorting/searching is explicitly deferred to a later
  change.

## Capabilities

### New Capabilities

- `admin-users-panel`: the admin Users tab — navigation entry and route, the
  users table with client-side pagination, sorting, and email search, and the
  per-user deployment count column.

### Modified Capabilities

(None. The backing endpoints `GET /api/users` and `GET /api/deployments` are
unchanged; their existing specs in `user-endpoint-authorization` and
`admin-list-deployments-endpoint` remain as-is.)

## Impact

- `ui/src/App.tsx`: lazy import + route for the new panel.
- `ui/src/components/AdminSidebar.tsx`: new nav item.
- `ui/src/components/UsersPanel.tsx`: new component (table + data fetching).
- `ui/src/api/endpoints.ts`: no change (`listUsers` and `listAllDeployments`
  already exist).
- `ui/src/api/types.ts`: no change (`User` and `Deployment` types already
  exist).
- Tests: new component tests for the panel; endpoint tests unchanged.
- No API, CLI, migration, or Terraform impact.
