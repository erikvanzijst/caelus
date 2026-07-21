## Context

Freepod's four legal documents live as markdown under `ui/src/content/legal/`
(canonical copies); repo-root `legal/*.md` are symlinks into that directory so
the documents stay browsable at the repo root without breaking the UI Docker
build, whose context is `ui/`. Vite imports each document with `?raw`, inlining
it as a build-time string constant. The full-page renderer is
`ui/src/pages/LegalDoc.tsx` (markdown + print chrome, public route
`/legal/:slug`). The deploy flow is `DeployDialog` → `DeployDialogContent`
(a single MUI `<Dialog>`); the Launch button is already driven by a
`launchDisabled` boolean, and create goes through `createDeployment` →
`POST /users/{user_id}/deployments` → `create_deployment` service → `DeploymentORM`.

Two facts about the authentication topology shape this design decisively:

1. **The API knows a user only by email.** `oauth2-proxy` injects
   `X-Auth-Request-Email`; `get_current_user` (`api/app/deps.py`) JIT-provisions
   the `UserORM` row on first request. The API never sees Keycloak tokens or
   attributes, so acceptance state recorded in Keycloak could not be read by the
   app without new claim→header plumbing. Acceptance therefore lives in the
   Caelus DB, on the user.
2. **The ToS text is a UI-owned asset.** Because of the symlink layout the API
   and CLI never import or see the document body. Each document already carries a
   human-authored `**Effective date:**` line (ToS/AUP `2026-07-01`, Privacy
   `2026-06-30`) that changes only on real revisions.

`GET /api/me` is already the session-init endpoint the UI calls, making it the
natural place to expose the user's acceptance state to the deploy dialog.

## Goals / Non-Goals

**Goals:**

- Record ToS agreement **once per user**, as an explicit act, deferred to the
  user's first deployment (no signup-time friction).
- A durable per-user record of the ToS version accepted, sufficient to later
  drive a re-approval flow (`user.tos_accepted_version < current`).
- Reject inconsistent/stale/future version submissions rather than record them,
  without the API ever importing the ToS text.
- Let the user read the full ToS without losing anything typed into the deploy
  form.
- A version scheme that changes only when the terms change, is human-readable,
  and is orderable.
- Reuse the existing legal-document renderer rather than duplicating it.
- CLI/REST parity for the new create input.

**Non-Goals:**

- Re-prompting existing users after the ToS changes (a later change; this change
  only records enough to make it possible).
- An append-only acceptance/audit log (single last-write-wins field now).
- Separate explicit acceptance of Privacy Policy, AUP, or DPA.
- The API importing or rendering the ToS text.
- Recording acceptance in Keycloak (blocked by the email-only header topology,
  version-naive native T&C, and unmanaged realm IaC — see D8).

## Decisions

### D1: Version = the document's `Effective date`, not `GIT_COMMIT`

The recorded ToS version is the ISO date on the document's `**Effective date:**`
line (e.g. `2026-07-01`). It changes only when the document is revised, is
human-readable in the database and admin views, and is orderable — the three
properties a future "is what this user accepted older than current?" comparison
needs.

*Alternatives considered:*
- **`GIT_COMMIT`**: available in prod, zero authoring, but changes on *every*
  commit — a typo fix elsewhere would bump the "ToS version" of every new
  acceptance, so a future re-approval flow would re-prompt everyone constantly.
  It tracks "which build," not "which terms." Rejected as the semantic version.
- **Content hash of the markdown**: zero authoring and changes only on edits, but
  opaque in the database and not orderable (answers "differs?" but not
  "older?"). Rejected in favor of the already-present, orderable date.

### D2: The UI version is parsed once, centrally, and fails loud

The version is extracted from the prose line in `ui/src/content/legal/index.ts`
at module load (the `?raw` import is already a constant, so this is a one-time
parse) and exposed as `LegalDoc.version`. The parser throws if a document has no
valid `YYYY-MM-DD` effective date, and a unit test asserts every registered
document yields a valid ISO date. Rationale: a loose regex over prose can
*silently* capture the wrong or empty value if someone reformats the line — the
worst outcome for a legal record. Throwing at module init turns that into a
failed dev/CI build instead of a corrupted consent record.

### D3: Acceptance is recorded on the User, once — not on the deployment

`UserORM` gains `tos_accepted_version` (nullable) and `tos_accepted_at`. The
first successful deployment by an unaccepted user records both; later deployments
read the existing value and record nothing. This matches the domain (a user
agrees to a contract once) and makes future re-approval a single
`user.tos_accepted_version < current` check with no per-deployment fan-out.

The earlier per-deployment column is removed. A per-deployment snapshot is
reconstructable if ever needed (deployment `created_at` plus the user's accepted
version) and is not worth the repeated-consent semantics it forced.

*Types:* `tos_accepted_version` is the document's effective **date** (stored as
an ISO date string, recorded verbatim as displayed). `tos_accepted_at` is the
**moment of the click** and is a `datetime` — the timestamp is the evidentiary
value and it stays consistent with every other `_at` column in `core.py`
(`created_at`, `deleted_at`, `last_reconcile_at`).

### D4: The API validates the submitted version against a configured current version

On create, when acceptance is being recorded, the API requires
`tos_version == settings.current_tos_version` and rejects otherwise (`409`,
"terms have changed, please re-review"). This deliberately revises the initial
design's "pure recorder, no currency check": a pure recorder accepts any
well-formed date, and a crafted request can then **future-date** acceptance to
permanently escape a future `stored < current` re-prompt, or record a
stale/nonexistent version. Equality-to-current closes both.

Crucially this does **not** require the API to see the ToS *text* — only the
current effective **date**, a single string. `settings.current_tos_version` is
that string. The initial design's honesty concern ("record exactly what the user
saw, don't silently upgrade") is preserved differently at the user level: the
user always accepts the *current* terms, so the honest record and the current
version coincide; a genuine mid-flight revision surfaces as a rejection the UI
turns into a re-review prompt, not a silent substitution.

The field remains ISO-shape validated (`YYYY-MM-DD`) as a cheap first guard
before the equality check.

### D5: `current_tos_version` is a code-default release constant, not env config, guarded by CI

`settings.current_tos_version` is defined with a default in `api/app/config.py`
and is **not** populated in `.env` or Terraform. It is a property of the
*release* (it must match the ToS markdown that ships in the same image), not of
the *environment* (dev and prod run the same terms). A code default gives
dev/prod parity *by construction* — one value, everywhere — whereas an env var
gives parity only if the same value is replicated into every environment, and
lets prod drift to a version the shipped markdown doesn't match (reopening the
very hole D4 closes). The pydantic `CAELUS_CURRENT_TOS_VERSION` override still
exists as an emergency escape hatch but is never set in normal operation.

A CI test in `api/tests/` reads the canonical
`ui/src/content/legal/terms-of-service.md` (not the `legal/` symlink, to avoid
symlink-following surprises off Linux), parses its `**Effective date:**` line
with the same `\d{4}-\d{2}-\d{2}` shape the UI uses, and asserts equality with
`get_settings().current_tos_version`. Bumping the markdown without bumping the
constant (or vice-versa) fails the build. This is the mechanism that lets a
single string in `config.py` stand in for the UI-owned document without silent
drift. Trade-off: it couples an `api/` test to the `ui/` file path — an
intentional, loud coupling.

### D6: Acceptance is its own resource; the deployment only requires it

Recording acceptance is **not** a field on `DeploymentCreate`. It is a dedicated
resource on the caller: `POST /api/me/tos-acceptance` (body `{version}`) records
it and `GET /api/me/tos-acceptance` reads it. `DeploymentCreate` carries no ToS
field at all; `create_deployment` merely enforces the precondition — if the
owning user's `tos_accepted_version` is null it raises `ValidationException` (400).

*Why not a conditional `tos_version` on `DeploymentCreate`* (an option we built
first and rejected): piggybacking the version on the deployment payload quietly
re-couples a user-level fact to the deployment and its transaction — the very
coupling this change set out to remove. Worse, "roll back acceptance if the
deployment fails" is the *wrong* semantics: acceptance is a durable user fact
that should persist independently of any single deployment. Splitting the calls
fixes the semantics and lets a future re-approval flow and any first-login
interstitial reuse the same endpoint. The cost — two requests on first launch,
and a window where a user has accepted but not yet deployed — is exactly the
correct, harmless outcome.

`GET` returns **200 with a status document** (`{version, accepted_at}`, both null
when unaccepted) rather than 404: a 404 overloads "route not found" onto a normal
state the client must disambiguate. Acceptance is deliberately **not** exposed on
`GET /api/me` (the identity model), keeping that model about identity. The
submitted version is still validated `== current_tos_version` (D4), now in the
acceptance endpoint, with 409 on mismatch.

### D7: Read the ToS in a nested modal reusing an extracted body component
*(Unchanged from the initial implementation.)*

The agreement label links to the ToS; activating it opens a second MUI `<Dialog>`
stacked over the deploy dialog, which stays mounted underneath so nothing typed
is lost. The markdown body of `LegalDoc.tsx` is extracted into a shared
`LegalDocBody` component rendered by both the full-page route and the modal.

### D8: One checkbox for the ToS; other documents linked, not checked
*(Unchanged from the initial implementation.)*

A single required checkbox covers the Terms of Service. The AUP is incorporated
by reference; the Privacy Policy is linked for GDPR transparency; the DPA is a
separate B2B instrument. Only the ToS version is recorded.

### D9: Why not record acceptance in Keycloak (Option 1)

Considered and rejected for now: (a) the API sees only the email header, so a
Keycloak-stored attribute would need new claim→header plumbing to reach the app;
(b) Keycloak's native Terms & Conditions required action is version-naive
(boolean/timestamp attribute, no "which version"), and re-prompting on a
revision means scripting an admin-API reset across all users; (c) it would
duplicate the ToS text into a login-theme `terms.ftl`, splitting the UI-owned
source of truth; (d) the realm is a bare `kubernetes_deployment`, not managed by
the Keycloak Terraform provider, so this is unmanaged-infrastructure work, not a
checkbox. May revisit as a UX polish later; not the mechanism here.

### D10: Persistence and migration

`UserORM` gains two **nullable** columns (`tos_accepted_version: str | None`,
`tos_accepted_at: datetime | None`); no backfill is needed because NULL correctly
means "has not accepted yet." The per-deployment `deployment.tos_version` column
is dropped. Because this change is not yet merged and there is no production
data, the migration is rewritten wholesale (add the user columns, drop the
deployment column) rather than layered on top of the initial column-add
migration; the dev database is reset to match.

### D11: CLI parity

The Typer create-deployment command's `--tos-version` becomes conditionally
required, mirroring the API: required only when the acting user has not yet
accepted, otherwise optional/ignored. A machine/operator caller supplies the
version string explicitly (it has no rendered text to read), recording the
version accepted on the user's behalf.

## Risks / Trade-offs

- **Client-supplied version is still trusted for identity, but bounded.** A
  crafted request can no longer future-date or invent a version — equality to
  `current_tos_version` (D4) rejects anything but the real current date. What
  remains standard-for-clickwrap is that the *acceptor* is the party bound.
- **Two places to bump on a real ToS change** (the markdown effective date and
  `current_tos_version`). The CI guard (D5) turns a forgotten bump into a red
  build rather than a silent inconsistency — a feature, making "we changed the
  terms" explicit on both sides.
- **No acceptance history.** Last-write-wins stores only the latest accepted
  version. Accepted for now (B2C, no prod data); a `tos_acceptance` audit table
  can be added later without disturbing this shape.
- **`api/` test couples to a `ui/` path.** Intentional (D5); it breaks loudly if
  the legal docs move.

## Migration / Rollout

The migration adds the nullable user columns and drops the deployment column; no
backfill. The create contract becomes stricter for unaccepted users (a
conditionally required, equality-validated field), so the UI ships together with
the API. Safe without downtime because there is no production data — the only
affected rows are dev/test deployments, and the dev DB is reset.
