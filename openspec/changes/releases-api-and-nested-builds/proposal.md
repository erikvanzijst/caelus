## Why

The release ledger (`deployment-release-ledger`) records every rollout of a
deployment — its number, template, build, values, outcome and timing — but
nothing can read it. A deployment read exposes only `applied_release`, so the
one release a caller can see is the one currently running: the four that failed
before it, and the two queued behind it, are unreachable over the API. A user
who wants to know what they deployed last Tuesday, or why yesterday's rollout
failed, has no endpoint to ask.

The builds surface has the opposite problem — it is readable but misplaced.
`/api/builds` sits at the root and carries a `user_id` query parameter to select
whose builds to list, while every other user-owned resource on this platform is
addressed under its owner (`/api/users/{user_id}/deployments`, per AGENTS.md
§ Conventions). One resource models ownership in the query string and the rest
model it in the path, so `require_self` cannot guard builds and the router
carries a hand-rolled `_resolve_scope` instead.

## What Changes

- **New `GET /api/users/{user_id}/deployments/{deployment_id}/releases`** — the
  deployment's releases, most recent first (highest number first). Guarded by
  `require_self`, like every other route under `/users/{user_id}`.
- **New `GET /api/users/{user_id}/deployments/{deployment_id}/releases/{number}`**
  — one release, addressed by its **per-deployment number**, not its `uuid4`.
  The ledger spec already requires that the number "SHALL be the identifier
  presented to users and accepted from them", and the deployment log endpoint
  already pins by number; the `uuid4` stays the unguessable value stamped onto
  pods. **Both** responses **inline the build object** rather than just its id,
  so reading what a rollout shipped costs one request instead of two — and
  comparing what several rollouts shipped costs one request, not one per row.
  The build is loaded by an eager `LEFT OUTER JOIN`, so a listing performs the
  same number of queries whatever its length; see design D3.
- **BREAKING — the builds API moves under its owner.** `/api/builds*` becomes
  `/api/users/{user_id}/builds*`, the whole router: `POST` (create),
  `GET` (list), `GET /{build_id}`, and `GET /{build_id}/log`. Ownership comes
  from the path and is enforced by `require_self`; `_resolve_scope` and the
  `user_id` **query parameter are removed**. Build creation still takes the
  owner from the authenticated session — the path `user_id` is authorization,
  not input, and the body still forbids a `user_id` field.
- **BREAKING — no compatibility aliases.** The old `/api/builds*` paths are
  removed outright rather than kept as deprecated routes. Installed `freepod`
  clients (≤ 0.4.0) call `POST /api/builds` during `deploy` and will fail
  against a platform carrying this change until they upgrade.
- **New `freepod releases` command** — lists the current project's deployment's
  releases through the new endpoint. Unlike `freepod builds`, this one is
  inherently project-scoped: a release belongs to a deployment, so the command
  requires a project file that records one and says so plainly when there is
  none.
- **`freepod builds` follows the relocation** and is otherwise unchanged. It
  already calls `GET /api/me` before its reads, so the `user_id` the new path
  needs is in hand.
- **`caelus` CLI parity** — `caelus list-releases <user_id> <deployment_id>` and
  `caelus get-release <user_id> <deployment_id> <number>`, thin shells over the
  same service functions, as AGENTS.md § Contribution Checklist requires for new
  REST surface.

## Capabilities

### New Capabilities

- `deployment-release-api`: the read surface of the release ledger — listing a
  deployment's releases most-recent-first, reading one by its per-deployment
  number, inlining the build on the single-release read, and scoping both to the
  deployment's owner so another account's releases are indistinguishable from
  ones that do not exist.
- `cli-releases`: the `freepod releases` command — a project-scoped listing of
  the current deployment's rollouts, what each row reports, how the running one
  is marked, and the stdout/stderr split the other listing commands obey.

### Modified Capabilities

- `build-api`: builds are addressed under the owning user rather than at the
  root, and the scope of a read comes from the request path rather than a
  `user_id` query parameter. The existing authorization *rules* are unchanged —
  a caller reads their own builds, an administrator may read anyone's, another
  user's build is indistinguishable from a missing one — but what carries the
  scope changes, and the previous root paths cease to exist.

<!-- Not modified: `cli-build-history`. Its requirements are path-agnostic — the
     history is still the account's builds, in the platform's order, with the
     project's running build marked. Only the URL the client calls changes,
     which is implementation, not behavior. -->

## Impact

- **API** — `api/app/api/builds.py` re-prefixed to `/users/{user_id}/builds`
  with `require_self`, `_resolve_scope` deleted; new release routes added
  alongside the deployment routes in `api/app/api/users.py`; `app/main.py`
  include unchanged in shape but the builds router now nests.
- **Services** — `api/app/services/deployments.py` gains `list_releases` and
  `get_release` (by deployment + number), both scoped by `user_id` and raising
  `NotFoundException` for a deployment that is not the caller's, matching
  `_get_deployment_orm`. No schema change: the `deployment_release` table and
  its `uq_release_number` constraint already carry everything read here, so
  **no Alembic migration**.
- **Models** — a detail variant of `DeploymentReleaseRead` carrying a nested
  `BuildRead`; `status` continues to be derived on read from the ORM property.
- **`caelus` CLI** — two new commands for parity.
- **`freepod` CLI** — new `releases` command and module; `history.list_builds`
  and `build.py`'s three build calls re-pointed at the nested paths. The client
  version is bumped, since a client built before this change cannot talk to a
  platform carrying it.
- **Clients in the field** — every installed `freepod` breaks on `deploy`,
  `builds` and any build read until upgraded. This is the accepted cost of the
  hard cut; see design § "No compatibility aliases".
- **UI** — none. `ui/` calls no build endpoint today.
- **Docs** — `api/README.md` (endpoint tables, the three-phase build flow, the
  log section), `cli/DEVELOPMENT.md` (module map, the build-history section, a
  new releases section), `cli/README.md` (the `releases` command is end-user
  surface), and `AGENTS.md` where it describes the builds subsystem's routes.
