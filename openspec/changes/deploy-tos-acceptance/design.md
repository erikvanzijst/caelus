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

A consequence of the symlink layout is decisive for the design: **the ToS text
is a UI-owned asset. The API and CLI never import or see it.** Each document
already carries a human-authored `**Effective date:**` line (ToS/AUP
`2026-07-01`, Privacy `2026-06-30`) that changes only on real revisions.

`GIT_COMMIT` is available at runtime in production (baked via `ARG GIT_COMMIT`
in both Dockerfiles from CI); it defaults to `unknown` in local dev.

## Goals / Non-Goals

**Goals:**

- An explicit, recorded act of ToS agreement at new-deployment time, gating
  Launch.
- A durable per-deployment record of the ToS version accepted, sufficient to
  later drive a re-approval flow.
- Let the user read the full ToS without losing anything typed into the deploy
  form.
- A version scheme that changes only when the terms change, is human-readable,
  and is orderable.
- Reuse the existing legal-document renderer rather than duplicating it.
- CLI/REST parity for the new create input.

**Non-Goals:**

- Re-prompting existing deployments after the ToS changes (a later change; this
  change only records enough to make it possible).
- Separate explicit acceptance of Privacy Policy, AUP, or DPA.
- Server-side authority over "the current ToS version" (the UI owns the text, so
  it owns the version).
- Full-text snapshot or acceptor IP capture for stronger clickwrap evidence.

## Decisions

### D1: Version = the document's `Effective date`, not `GIT_COMMIT`

The recorded ToS version is the ISO date on the document's `**Effective date:**`
line (e.g. `2026-07-01`). It changes only when the document is revised, is
human-readable in the database and admin views, and is orderable — the three
properties a future "is what this user accepted older than current?" comparison
needs.

*Alternatives considered:*
- **`GIT_COMMIT`** (the originally proposed option): available in prod, zero
  authoring, but changes on *every* commit — a typo fix elsewhere would bump the
  "ToS version" of every new deployment, so a future re-approval flow would
  re-prompt everyone constantly. It tracks "which build," not "which terms."
  Rejected as the semantic version. **May optionally be recorded separately** as
  `tos_git_commit` for build provenance ("which build served this text"),
  which keeps the two concerns distinct.
- **Content hash of the markdown**: zero authoring and changes only on edits,
  but opaque in the database and not orderable (answers "differs?" but not
  "older?"). Rejected in favor of the already-present, orderable date.

### D2: The version is parsed once, centrally, and fails loud

The version is extracted from the prose line in `ui/src/content/legal/index.ts`
at module load (the `?raw` import is already a constant, so this is a one-time
parse, not per-render work), and exposed as `LegalDoc.version`. The parser
throws if a document has no valid `YYYY-MM-DD` effective date, and a unit test
asserts every registered document yields a valid ISO date.

Rationale: keeping the human-facing `Effective date` as the single source of
truth avoids duplicate bookkeeping, but a loose regex over prose can *silently*
capture the wrong or empty value if someone reformats the line — the worst
outcome for a legal record. Throwing at module init turns that into a failed
dev/CI build instead of a corrupted consent record: fail at build, not at
consent. (If richer per-document metadata is ever needed — a monotonic integer,
per-doc re-acceptance flags — revisit with YAML frontmatter; not warranted for a
single date field today.)

### D3: The API is a recorder, not a validator of currency (no CAS)

On create, the UI sends the ToS version string it displayed; the API stores it
verbatim and returns it on reads. The API does **not** compare it against a
server-side "current" version.

This deliberately differs from the existing template Compare-And-Swap guard in
`create_deployment` (which rejects stale template submissions because a stale
schema yields invalid data — a correctness concern). ToS acceptance is a consent
concern: recording exactly the version the user *saw and accepted* is the honest
record, even if it is a few seconds behind the very latest text. Forcing it to
match server-current would record a version the user never read. Drift between
what a deployment accepted and the current terms is precisely what the future
re-approval flow handles — with the user's consent — so it must not be silently
erased here.

The API still applies two light guards: the field MUST be present on create
(enforcing that the client went through the consent flow) and MUST be a
well-formed ISO date (rejecting obvious garbage). Neither requires the API to
know the ToS text.

A useful corollary: because the UI owns both the text and the current version,
even the future re-approval comparison ("does this deployment's stored version
differ from the one I bundle?") is a UI-side computation. The API stays a pure
recorder forever.

### D4: Read the ToS in a nested modal reusing an extracted body component

The agreement label links to the ToS; activating it opens a second MUI
`<Dialog>` stacked over the deploy dialog. MUI stacks dialogs natively and the
deploy dialog stays mounted underneath, so closing the ToS modal returns the
user to their form exactly as they left it — no navigation, no lost input.

To avoid duplicating the renderer, the markdown body of `LegalDoc.tsx` (the
`<Markdown>` element plus its `articleSx` styling and external-link handling) is
extracted into a shared `LegalDocBody` component. The full-page `LegalDoc` keeps
its sticky nav / print chrome and renders `LegalDocBody`; the modal renders the
same body. This follows the repo convention of extracting focused components
under `ui/src/components/` rather than inlining.

*Alternatives considered:*
- **New browser tab to `/legal/terms`**: zero state risk and reuses the page
  as-is, but a heavier context switch and clunky on mobile. Rejected as the
  primary mechanism (the underlying anchor's `href` can still point at
  `/legal/terms` so right-click / middle-click open-in-tab keeps working as
  progressive enhancement).
- **Inline expander/accordion** inside the deploy dialog: cramps a long legal
  document into a small dialog. Rejected.

### D5: One checkbox for the ToS; other documents linked, not checked

A single required checkbox covers the Terms of Service. The Acceptable Use
Policy is incorporated by reference into the ToS, and the Privacy Policy is
linked for GDPR transparency (users are informed by it, not asked to "agree").
The DPA is a B2B controller/processor instrument offered separately, not a
per-deployment consumer checkbox. Suggested label:

> ☐ I agree to the Freepod **Terms of Service** and **Acceptable Use Policy**,
> and acknowledge the **Privacy Policy**.

Only the ToS version is recorded. Because the AUP is incorporated by reference,
an AUP revision that changes the deal should bump the ToS effective date too; a
separate AUP version is not tracked in this change.

### D6: Persistence and migration

`DeploymentORM` gains `tos_version: str` (NOT NULL) and, if adopted,
`tos_git_commit: Optional[str]`. The Alembic migration adds the column, backfills
every existing deployment to `2026-07-01` (the current ToS effective date), and
then enforces NOT NULL (the standard add-nullable → backfill → alter-not-null
sequence). This is acceptable because there is no production data yet: the
existing test deployments are treated as having explicitly accepted the current
terms.

A NOT NULL column with a backfill is preferred over a permanently nullable one:
it lets the database enforce the invariant the API/CLI contract already promises
(every deployment has an accepted version), and it collapses "never accepted"
and "accepted an older version" into one comparable state, so a future
re-approval flow is a uniform `stored_version < current_version` check with no
null special-case.

### D7: CLI parity

The Typer create-deployment command gains a `--tos-version` option mirroring the
REST field, consistent with the API/CLI parity convention. A machine/operator
caller supplies the version string explicitly (it has no rendered text to read),
recording the version the operator is accepting on the user's behalf.

## Risks / Trade-offs

- **Client-supplied version is trusted.** A hand-crafted request could submit
  any well-formed date. This is acceptable and standard for clickwrap: the
  record captures what the client asserted was shown, and the acceptor is the
  party bound by it. The ISO-format guard rejects only obvious garbage.
- **Authoring discipline for the effective date.** The version only advances if
  editors bump the `Effective date` when they change the terms. The parse test
  guarantees the date is *present and well-formed*, not that it was *bumped*; a
  content-changed-but-date-unchanged check could be added later if needed.
- **AUP/Privacy changes are not separately versioned.** Accepted for now
  (AUP incorporated by reference; Privacy is disclosure, not agreement).

## Migration / Rollout

The migration adds the new column, backfills existing rows to `2026-07-01`, and
enforces NOT NULL. The create contract also becomes stricter (a required field),
so the UI and any API clients must send `tos_version` from the moment the API is
deployed; the UI change ships together with it. Safe to run without downtime
because there is no production data — the only affected rows are dev/test
deployments.
