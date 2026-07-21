## 1. Legal document versioning (UI content)

- [x] 1.1 Add a `version` field to the `LegalDoc` interface and populate it in
  `ui/src/content/legal/index.ts` by parsing each document's
  `**Effective date:** YYYY-MM-DD` line once at module load
- [x] 1.2 Make the parser throw on a missing/malformed effective date (fail at
  build, not at consent)
- [x] 1.3 Add a test asserting every registered document's `version` matches
  `^\d{4}-\d{2}-\d{2}$`

## 2. Shared legal-document renderer

- [x] 2.1 Extract the markdown body of `ui/src/pages/LegalDoc.tsx` (the
  `<Markdown>` element, `articleSx`, external-link handling) into a
  `LegalDocBody` component under `ui/src/components/`
- [x] 2.2 Re-point the full-page `LegalDoc` to render `LegalDocBody` inside its
  existing print/nav chrome (no visual change to the `/legal/:slug` route)

## 3. ToS reader modal + agreement checkbox (UI)

- [x] 3.1 Add a nested-modal ToS reader (`LegalDocModal`, a MUI `<Dialog>`
  rendering `LegalDocBody`) that opens over the deploy dialog and restores it
  unchanged on close
- [x] 3.2 Add the required agreement checkbox (`TosAgreement`) to
  `DeployDialogContent` with a label linking the ToS/AUP/Privacy (each opens the
  modal); new-launch only, not edit mode
- [x] 3.3 Wire the checkbox into `DeployDialog`: include its state in
  `launchDisabled`, and send the bundled ToS `version` as `tos_version` in the
  create payload (`createDeployment` / endpoint + types)
- [x] 3.4 UI tests: Launch disabled until checked; opening/closing the ToS modal
  preserves entered form values; create payload carries the version

## 4. Persistence + create contract (API)

- [x] 4.1 Add `tos_version` (NOT NULL) to `DeploymentORM` (`tos_git_commit`
  provenance intentionally deferred — see design D1/D6)
- [x] 4.2 Add required `tos_version` to `DeploymentCreate` with ISO-8601
  (`YYYY-MM-DD`) validation; add `tos_version` to `DeploymentRead`
- [x] 4.3 Persist the supplied `tos_version` in `create_deployment` (recorded
  verbatim via `model_dump` passthrough, no compare-against-current)
- [x] 4.4 Alembic migration: add the column, backfill existing deployments to
  `2026-07-01` (current ToS effective date), then enforce NOT NULL (batch mode
  for SQLite/Postgres portability)
- [x] 4.5 CLI parity: add `--tos-version` to the create-deployment command
  (required), passed through to the service

## 5. Tests & verification

- [x] 5.1 API tests: create requires `tos_version`; malformed date rejected;
  value persisted and returned on read; migration backfills existing rows to
  `2026-07-01` and the column is NOT NULL (verified end-to-end on a seeded DB)
- [x] 5.2 CLI tests: create requires `--tos-version`; value persisted and
  returned
- [x] 5.3 Manual verification via the running UI (`:5173`/`:8000`): launch is
  gated until the box is checked, the ToS modal opens over the dialog and
  preserves form state, and a new deployment POST recorded `tos_version`
  `2026-07-01` (confirmed in request + 201 response)
