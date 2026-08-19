# Tasks: Admin Users Tab

## 1. Navigation and route

- [x] 1.1 Add a "Users" nav item (with a people-style icon) to `navItems` in `ui/src/components/AdminSidebar.tsx`, pointing at `/admin/users`
- [x] 1.2 Add the lazy import for `UsersPanel` and the `/admin/users` route in `ui/src/App.tsx`, following the existing panel pattern

## 2. Users panel

- [x] 2.1 Create `ui/src/components/UsersPanel.tsx` fetching both lists with TanStack Query: `useQuery({ queryKey: ['admin-users'], queryFn: listUsers })` and `useQuery({ queryKey: ['admin-deployments'], queryFn: listAllDeployments })`, both `enabled: Boolean(user)`
- [x] 2.2 Derive per-user deployment counts with `useMemo` from the deployments list (keyed by deployment's user id, defaulting to 0) and merge into the user rows
- [x] 2.3 Render an MUI `DataGrid` with columns: id, email, admin status, join date (`created_at`), deployment count; client-side pagination with `pageSizeOptions={[25, 50, 100]}`; default sort `created_at` descending; all columns sortable
- [x] 2.4 Add a search box wired to DataGrid filtering on the email column (case-insensitive substring)
- [x] 2.5 Show a loading indicator while either query is in flight, instead of the table

## 3. Tests

- [x] 3.1 Add `ui/src/components/UsersPanel.test.tsx` (vitest + Testing Library, mocking the endpoint functions): one row per user with id/email/admin/join date; deployment count correct per user including a user with zero; search narrows rows by email substring and clearing restores all rows; default sort is newest first and clicking a header re-sorts; pagination shows one page at a time

## 4. Verification

- [x] 4.1 Run `npm test` and `npm run build` in `ui/` until green
- [x] 4.2 Verify against the running dev servers (UI on localhost:5173, API on localhost:8000): the tab appears for an admin, rows and deployment counts match the API responses, search/sort/pagination behave per spec
