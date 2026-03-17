## 1. Fix list_deployments service to exclude deleted deployments

- [ ] 1.1 Add `WHERE status != 'deleted'` filter to `list_deployments()` in `api/app/services/deployments.py`
- [ ] 1.2 Remove client-side `status !== 'deleted'` filter from `Dashboard.tsx`
- [ ] 1.3 Add/update tests to verify deleted deployments are excluded from list results

## 2. Add admin deployments API endpoint

- [ ] 2.1 Add `GET /api/deployments` route in `api/app/api/users.py` with `require_admin` dependency
- [ ] 2.2 Route calls `list_deployments(session)` without `user_id` to return all non-deleted deployments
- [ ] 2.3 Add test: admin can list all deployments across users
- [ ] 2.4 Add test: non-admin gets 403
- [ ] 2.5 Add test: deleted deployments are not included in admin listing

## 3. Add CLI --all flag to list-deployments

- [ ] 3.1 Add `--all` flag to `list-deployments` command in `api/app/cli.py`
- [ ] 3.2 When `--all` is set, call `list_deployments(session)` without `user_id` filter
- [ ] 3.3 When `--all` is set, verify calling user is admin; fail with error if not
- [ ] 3.4 Add CLI test for `list-deployments --all`
