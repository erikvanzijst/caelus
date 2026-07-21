## Why

Deploying an application on Freepod is the point at which a user enters into the
Terms of Service (the ToS itself says agreement is formed by "clicking 'I
agree'" or using the Service), yet nothing in the deploy flow captures that
consent. We need an explicit, recorded act of agreement at new-deployment time,
and — because the ToS text changes over time — a durable record of *which
version* of the Terms each deployment was created under. That record is what
makes a later "please re-accept the updated Terms" flow possible; this change
only captures consent, it does not build re-approval.

## What Changes

- Add a required **"I agree to the Terms of Service"** checkbox to the deploy
  dialog. Launch stays disabled until it is checked. The Privacy Policy and
  Acceptable Use Policy are linked (not separately checked): the ToS is the
  contract that is actively accepted, GDPR makes the Privacy Policy something
  the user is *informed* by rather than "agrees" to, and the AUP is
  incorporated by reference into the ToS. The DPA (a B2B controller/processor
  instrument) is out of scope for a per-deployment checkbox.
- Let the user read the full ToS **without losing dialog state**: the agreement
  text contains a link that opens the document in a nested modal over the deploy
  dialog. The deploy form stays mounted underneath, so nothing entered is lost.
  The modal reuses the existing legal-document renderer, extracted into a shared
  component.
- Version the legal documents by their existing **`Effective date`** line
  (already present in each markdown file, e.g. `2026-07-01`). The UI content
  registry parses this into an explicit `version` field per document, backed by
  a test that fails the build if a document lacks a parseable ISO date. This is
  chosen over `GIT_COMMIT`: the commit SHA changes on every unrelated commit and
  would make a future re-approval flow re-prompt everyone constantly, whereas
  the effective date changes only when the terms actually change and is both
  human-readable and orderable.
- **Record the accepted ToS version on the deployment.** The UI sends the ToS
  version it displayed on create; the API stores it verbatim and returns it on
  reads. The API is a plain recorder — it does not reject a "stale" version
  (recording exactly what the user saw is the legally honest thing; drift is the
  future re-approval flow's job), but it does require the field to be present
  and well-formed. Optionally also record `GIT_COMMIT` as separate build
  provenance.
- Keep CLI/REST parity: the create-deployment CLI command gains an equivalent
  `--tos-version` option.

Out of scope for this change: re-prompting existing deployments after the ToS
changes; separate acceptance of Privacy Policy / AUP / DPA; storing the full ToS
text snapshot or acceptor IP for stronger clickwrap evidence (the version plus
git history reconstructs the exact text if ever needed).

## Capabilities

### New Capabilities

- `legal-doc-versioning`: the UI legal-document registry exposes a `version` per
  document, parsed once from the document's `Effective date` line, with a
  build-failing guard against a missing or malformed date.
- `deploy-tos-consent-ui`: the deploy dialog's required ToS agreement checkbox
  gating Launch, the nested-modal reader reusing the extracted legal-document
  body, and submission of the displayed ToS version on create.
- `deployment-tos-record`: persistence of the accepted ToS version on the
  deployment (new NOT NULL column, existing rows backfilled to the current ToS
  effective date), its inclusion in deployment read responses, and CLI parity
  for supplying it.

### Modified Capabilities

- `deployment-create-contract`: the deployment create input (REST `POST
  /deployments` and the equivalent CLI command) gains a required `tos_version`
  field; creates without it are rejected.

## Impact

- `ui/src/content/legal/index.ts`: add a parsed `version` field to each
  `LegalDoc`; add a test asserting every document yields a valid ISO date.
- `ui/src/pages/LegalDoc.tsx`: extract the markdown body into a shared
  `LegalDocBody` component; the page keeps its print/nav chrome.
- `ui/src/components/`: new nested-modal ToS reader; agreement checkbox added to
  `DeployDialogContent` and wired into `DeployDialog`'s `launchDisabled` and
  create payload.
- `api/`: `Deployment` gains a `tos_version` column (NOT NULL) and optional
  `tos_git_commit`; `DeploymentCreate` requires `tos_version`;
  `create_deployment` validates and persists it; `DeploymentRead` returns it;
  CLI create command gains `--tos-version`.
- `api/alembic/`: migration adding the new column(s) and backfilling existing
  deployments to `2026-07-01` (the current ToS effective date) before enforcing
  NOT NULL. Acceptable because there is no production data yet — the existing
  test deployments are treated as having accepted the current terms.
- Tests: UI (checkbox gating, modal open/close preserves form state, version
  parse guard), API/CLI (create requires and records the version, reads return
  it, malformed version rejected).
