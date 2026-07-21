## 1. Legal document versioning (UI content) — retained, unchanged

- [x] 1.1 `LegalDoc.version` parsed once from each document's
  `**Effective date:** YYYY-MM-DD` line in `ui/src/content/legal/index.ts`
- [x] 1.2 Parser throws on a missing/malformed effective date (fail at build)
- [x] 1.3 Test asserting every document's `version` matches `^\d{4}-\d{2}-\d{2}$`

## 2. Shared legal-document renderer — retained, unchanged

- [x] 2.1 `LegalDocBody` extracted from `ui/src/pages/LegalDoc.tsx`
- [x] 2.2 Full-page `LegalDoc` renders `LegalDocBody` inside its print/nav chrome
- [x] 2.3 `LegalDocModal` nested reader that restores the deploy dialog on close

## 3. API: current ToS version + CI guard (`api-current-tos-version`)

- [x] 3.1 `current_tos_version` in `CaelusSettings` (in-code default `2026-07-01`,
  not set in `.env`/Terraform)
- [x] 3.2 CI test parsing `ui/src/content/legal/terms-of-service.md`'s
  `**Effective date:**` and asserting it equals `settings.current_tos_version`

## 4. API: acceptance resource on the user (`user-tos-record`)

- [x] 4.1 Nullable `tos_accepted_version` / `tos_accepted_at` on `UserORM`;
  `deployment.tos_version` removed
- [x] 4.2 `TosAcceptanceCreate` / `TosAcceptanceRead` models; acceptance kept off
  `UserRead`
- [x] 4.3 `GET /api/me/tos-acceptance` (always 200) and `POST /api/me/tos-acceptance`
  (validates `== current`, 409 on mismatch), backed by `users.record_tos_acceptance`
- [x] 4.4 CLI parity: `accept-tos --user-id --version` command

## 5. API: deployment precondition (`deployment-create-contract`)

- [x] 5.1 `DeploymentCreate` no longer carries a ToS field
- [x] 5.2 `create_deployment` rejects (400) when the owning user has not accepted
- [x] 5.3 CLI `create-deployment` loses `--tos-version`; the guard applies via the
  shared service

## 6. Migration (dev DB reset — no production data)

- [x] 6.1 Migration adds the two nullable `user` columns and drops
  `deployment.tos_version` (no backfill)
- [x] 6.2 Dev database reconciled to match

## 7. API tests

- [x] 7.1 Acceptance resource: initially null; record current; 409 on mismatch;
  422 on malformed; idempotent; GET reflects state
- [x] 7.2 Deployment precondition: rejected without acceptance; succeeds after
- [x] 7.3 CLI: `accept-tos` records; `create-deployment` blocked until accepted
- [x] 7.4 Full suite updated for the removed field / new precondition (green)

## 8. UI: conditional consent + accept-then-deploy (`deploy-tos-consent-ui`)

- [x] 8.1 Add `getTosAcceptance` / `recordTosAcceptance` endpoints + types
  (`GET`/`POST /api/me/tos-acceptance`)
- [x] 8.2 Read acceptance state and show `TosAgreement` in `DeployDialogContent`
  only for new launches by unaccepted users; gate `launchDisabled` only when shown
- [x] 8.3 On launch by an unaccepted user, `POST` acceptance (with the displayed
  version) then create the deployment; accepted users deploy directly
- [x] 8.4 UI tests: checkbox shown/hidden per acceptance state; Launch gating;
  modal preserves form state; first launch records then deploys
- [x] 8.5 Manual verification on the running UI (`:5173`/`:8000`): first deploy
  prompts and records; a second deploy shows no checkbox
