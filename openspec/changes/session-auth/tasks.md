## 1. Backend Auth Dependency

- [ ] 1.1 Add `get_current_user` FastAPI dependency that reads `X-Auth-Request-Email` header, performs case-insensitive lookup, auto-creates user if not found, and returns `UserORM`.
- [ ] 1.2 Add `GET /api/me` endpoint using `get_current_user`; return `UserRead` on success, `404` when header is absent.
- [ ] 1.3 Inject `Depends(get_current_user)` into all existing endpoint functions across all route modules (no behavioral change — plumbing only).
- [ ] 1.4 Add API tests for `/api/me`: success with known user, auto-creation for unknown email, case-insensitive email matching, and `404` when header is missing.
- [ ] 1.5 Add API tests verifying all existing endpoints return `404` when `X-Auth-Request-Email` header is absent.

## 2. CLI Authentication

- [ ] 2.1 Add `CAELUS_USER_EMAIL` env var reading at CLI startup with same lookup/auto-create logic as the API dependency.
- [ ] 2.2 Add optional `--as-user` flag that overrides `CAELUS_USER_EMAIL` when provided.
- [ ] 2.3 Ensure CLI commands that require a user context fail with a clear error when neither `CAELUS_USER_EMAIL` nor `--as-user` is set.
- [ ] 2.4 Add CLI tests for env var authentication, `--as-user` override, and missing-email error behavior.

## 3. Frontend Session Initialization

- [ ] 3.1 Refactor `useAuthEmail` (or replace) to manage a localStorage headers object (`caelus.auth.headers`) that is unconditionally spread into all API request headers.
- [ ] 3.2 Update `client.ts` request functions to read and apply headers from the localStorage headers object instead of a single `authEmail` parameter.
- [ ] 3.3 Add `/api/me` call as the first action on app startup; on `200` store user in memory, on `404` trigger the email dialog.
- [ ] 3.4 Update `EmailDialog.tsx`: on submit, populate localStorage headers with `{"X-Auth-Request-Email": email}` and retry `/api/me`.
- [ ] 3.5 Remove client-side user auto-creation logic from `Dashboard.tsx` (the `listUsers` → find → `createUser` flow).
- [ ] 3.6 Remove the "Switch user" button from `AppShell.tsx`.

## 4. Frontend Cleanup And Polish

- [ ] 4.1 Update `AppShell.tsx` top-right user display to use the user object returned from `/api/me` instead of reading email from localStorage.
- [ ] 4.2 Remove the `authEmail` parameter threading from `endpoints.ts` call sites now that headers are applied globally.
- [ ] 4.3 Verify Dashboard, Admin, and any other pages work correctly with the new auth flow.

## 5. Testing And Verification

- [ ] 5.1 Run full backend test suite and verify all existing tests pass with auth dependency injected (tests will need to supply the header).
- [ ] 5.2 Run CLI test suite and verify env var / `--as-user` flows.
- [ ] 5.3 Manually verify local-dev flow: fresh start → `/api/me` 404 → email dialog → header set → `/api/me` 200 → Dashboard loads.
- [ ] 5.4 Update API README and CLI README with new authentication documentation.
