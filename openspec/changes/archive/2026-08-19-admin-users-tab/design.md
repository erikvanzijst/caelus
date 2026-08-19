# Design: Admin Users Tab

## Context

See proposal.md for motivation. Current state that shapes the approach:

- Admin "tabs" are nested routes plus a sidebar drawer, not MUI Tabs:
  `ui/src/App.tsx:57-62` defines the routes (each panel is `React.lazy`),
  `ui/src/components/AdminSidebar.tsx:21-25` defines the nav items.
- `DeploymentsPanel.tsx` is the only admin table. It uses MUI `DataGrid`
  directly with client-side pagination (`pageSizeOptions={[25, 50, 100]}`)
  and column sorting, and no search. It fetches the full list via
  `useQuery({ queryKey: ['admin-deployments'], queryFn: listAllDeployments })`.
- `listUsers()` (`ui/src/api/endpoints.ts:19-21`) and the `User` type
  (`ui/src/api/types.ts:4-9`: `id`, `email`, `is_admin`, `created_at`)
  already exist; `listUsers` is currently unused.
- `Deployment` (`ui/src/api/types.ts:87-105`) embeds `user: User`, so the
  admin deployments list already carries the owner of every deployment.
- There is no server-side pagination/sorting/searching infrastructure in the
  API, and none is introduced by this change.
- `GET /api/deployments` already excludes `status == 'deleted'`
  (spec: `admin-list-deployments-endpoint`).

## Goals / Non-Goals

**Goals:**

- A fourth admin tab ("Users") showing all users in a DataGrid with
  client-side pagination, sorting, email search, and a per-user deployment
  count column.
- Follow the existing patterns exactly (lazy route, sidebar item, TanStack
  Query, DataGrid) so the change is a small, reviewable diff.

**Non-Goals:**

- Server-side pagination/sorting/searching (deferred; would require new API
  query params on `GET /api/users` and a count query).
- A username column or username search (no such field on the user model).
- User detail dialog, user creation, or user deletion UI (deletion is a 501
  stub server-side).
- Any API, CLI, database, or Terraform change.

## Decisions

1. **Client-side pagination, sorting, and filtering in DataGrid.**
   The Deployments tab already does exactly this, and platform user counts
   are small enough that fetching the full list is fine.
   *Alternative considered:* server-side params — rejected for this change;
   it is the deferred follow-up and would be the first pagination
   infrastructure in the API.

2. **Derive deployment counts client-side from `GET /api/deployments`.**
   The endpoint already excludes deleted deployments and embeds each
   deployment's user, so a `Map<userId, count>` built with `useMemo` gives
   correct counts with zero API changes.
   *Alternative considered:* a new `deployment_count` field on the API —
   rejected because it pulls a backend change (and a `caelus list-users`
   CLI parity question) into a change that should be UI-only. It remains
   the right home for the count once server-side pagination lands.

 3. **Search as a small search box + `useMemo` filter on the email field.**
    The spec requires matching on email only. DataGrid's built-in quick
    filter searches *all* columns (id, admin status, join date, count) and
    cannot be scoped to a single column, so it would over-match. A `TextField`
    plus a `useMemo` that case-insensitively substring-filters the merged rows
    on `email` is a few lines and matches the spec exactly.
    *Alternative considered:* DataGrid quick filter — rejected, it cannot be
    restricted to the email column.

4. **Two parallel queries, merged in the component.**
   `useQuery(['admin-users'], listUsers)` plus
   `useQuery(['admin-deployments'], listAllDeployments)` — the second key
   matches the Deployments tab's, so the cache is shared when an admin
   visits both tabs. Rows are merged with a `useMemo` that maps each user to
   their count (defaulting to 0).
   *Alternative considered:* one combined endpoint — rejected (API change).

5. **One new component file, `UsersPanel.tsx`; no shared DataTable
   wrapper.**
   The repo convention is one file per panel and `DataGrid` is configured
   inline (only two tables exist). Extracting a shared wrapper now would be
   premature.

## Risks / Trade-offs

- [The users list is a new full-list fetch on tab open] → the deployments
  list is served from the shared TanStack Query cache (same key as the
  Deployments tab), so only the users list is new; both lists are small at
  current scale. Revisit in the deferred server-side pagination change.
- [Counts can be briefly stale if a deployment changes while the tab is
  open] → same property as the Deployments tab (TanStack Query staleTime
  5s, no refetch on focus); acceptable for an admin view.
- [A brand-new user's count may read 0 if the deployments list is a few
  seconds behind the users list] → both queries run in parallel and refetch
  on navigation; the staleness window is negligible for this use case.

## Migration Plan

Frontend-only change; ships with the normal UI deploy. Rollback is reverting
the commit — no data, API, or migration state is touched.

## Open Questions

None. The "search by username/email" request resolves to email-only search
because the user model has no username field (confirmed with the user).
