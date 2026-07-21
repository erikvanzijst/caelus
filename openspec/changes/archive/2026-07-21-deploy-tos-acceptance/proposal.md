## Why

Deploying an application on Freepod is the point at which a user enters into the
Terms of Service (the ToS itself says agreement is formed by "clicking 'I
agree'" or using the Service). But acceptance of the Terms is a **user-level**
act, not a per-deployment one: a person agrees to the contract once, not afresh
on every launch. The initial implementation of this change recorded consent on
each *deployment*, which forces re-acceptance on every deploy and — once ToS
revisions are tracked — would re-prompt each user n times (once per deployment).

This change moves the record to the **user**, captures it **once**, and defers
the prompt to the user's first deployment so we don't front-load legal friction
at signup. It also gives the API a lightweight notion of the *current* ToS
version so it can reject inconsistent or stale submissions instead of recording
whatever a client sends. Recording only enough to later drive a "please
re-accept the updated Terms" flow remains a goal; building that re-approval flow
does not.

## What Changes

- **Record acceptance on the User, once.** `UserORM` gains
  `tos_accepted_version` (ISO date string, nullable, NULL until accepted) and
  `tos_accepted_at` (`datetime` — the instant of the click). The per-deployment
  `tos_version` column is dropped.
- **Defer the prompt to first deploy.** The deploy dialog shows the agreement
  checkbox only when the current user has not yet accepted the current ToS
  version, surfaced via `GET /api/me/tos-acceptance`. On first launch the UI
  records acceptance (POST) and then creates the deployment; second and
  subsequent deployments show no checkbox and add no friction.
- **The API knows the current ToS version (one string, never the text).** A new
  `settings.current_tos_version` release constant (defaulted in code, not
  environment-specific) lets the API validate that a submitted `tos_version`
  **equals** the current version. This closes the "record anything" hole — a
  crafted request can otherwise future-date acceptance to permanently dodge
  re-approval, or record a stale/nonexistent version. The ToS **text** stays
  UI-owned; the API needs only the current effective date.
- **A CI test binds the two sources.** An `api/` test parses the ToS markdown's
  `**Effective date:**` line and asserts it equals `settings.current_tos_version`,
  so the code-side constant cannot silently drift from the terms it represents.
- **Acceptance is its own resource, not a deployment field.** Recording happens
  at `POST /api/me/tos-acceptance` (body `{version}`, validated `== current`,
  409 on mismatch) and is read at `GET /api/me/tos-acceptance` (always 200;
  `version` null until accepted). Deployment create carries **no** ToS field;
  it simply **requires prior acceptance** and rejects an unaccepted user with
  400 (a server-side guard so the two-step flow can't be bypassed). This keeps
  `DeploymentCreate` purely about deployments and models acceptance as the
  user-level fact it is — piggybacking a `tos_version` on the deployment payload
  was rejected as a kludge that re-coupled the two concerns.
- **Unchanged from the initial implementation:** the UI legal-document
  versioning (`LegalDoc.version` parsed from `Effective date`), the shared
  `LegalDocBody` renderer, and the nested ToS reader modal that preserves deploy
  form state.
- **CLI parity:** the create-deployment `--tos-version` option becomes
  conditionally required (required only when the acting user has not accepted),
  mirroring the API.

Out of scope: re-prompting on a ToS revision (this change records enough to make
it a later `user.tos_accepted_version < current` check); an append-only
acceptance/audit log (a single last-write-wins field now — a `tos_acceptance`
table can follow if stronger evidentiary needs arise); separate acceptance of
the Privacy Policy / AUP / DPA.

## Capabilities

### New Capabilities

- `legal-doc-versioning`: the UI legal-document registry exposes a `version` per
  document, parsed once from the document's `Effective date` line, with a
  build-failing guard against a missing or malformed date. *(Unchanged from the
  initial implementation.)*
- `deploy-tos-consent-ui`: the deploy dialog's ToS agreement checkbox, shown
  **only when the current user has not yet accepted** the current version,
  gating Launch; the nested-modal reader reusing the extracted `LegalDocBody`;
  and submission of the displayed ToS version on create when acceptance is being
  recorded.
- `user-tos-record`: persistence of the accepted ToS version and acceptance
  timestamp on the user (nullable, set once), its exposure on `GET /api/me`, and
  the one-time recording semantics driven by the deployment-create flow.
- `api-current-tos-version`: the API's configured `current_tos_version` release
  constant and the CI guard asserting it equals the ToS markdown's effective
  date.

### Modified Capabilities

- `deployment-create-contract`: the deployment create input (REST
  `POST /users/{user_id}/deployments` and the equivalent CLI command) gains an
  **optional** `tos_version`, required only when the acting user has not yet
  accepted; when supplied it MUST equal the current version; the accepted
  version is recorded on the user.

## Impact

- `ui/src/content/legal/index.ts`, `ui/src/pages/LegalDoc.tsx`,
  `ui/src/components/` (LegalDocBody, LegalDocModal, TosAgreement): retained from
  the initial implementation; the agreement checkbox becomes conditional on the
  `/api/me` acceptance state, and the version is submitted only when recording.
- `ui/src/api/`: `me` typing gains `tos_accepted_version` /`tos_accepted_at`;
  `createDeployment` sends `tos_version` conditionally.
- `api/app/models/core.py`: `UserORM`/`UserRead` gain `tos_accepted_version` and
  `tos_accepted_at`; `DeploymentORM`/`DeploymentRead` lose `tos_version`;
  `DeploymentCreate.tos_version` becomes optional.
- `api/app/config.py`: add `current_tos_version` (default in code).
- `api/app/services/`: `create_deployment` enforces the conditional requirement
  and equality-to-current, and writes the accepted version to the user.
- `api/app/cli.py`: `--tos-version` becomes conditionally required.
- `api/alembic/`: replace the dropped per-deployment migration with one that adds
  the nullable user columns and removes `deployment.tos_version` (no backfill —
  nullable start; no production data).
- Tests: UI (conditional checkbox, modal preserves state, version parse guard),
  API/CLI (conditional requirement, equality-to-current rejection, recording on
  the user, `/api/me` exposure, CI drift guard).
