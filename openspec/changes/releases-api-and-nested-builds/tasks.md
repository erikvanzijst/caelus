## 1. Models

- [x] 1.1 Add `DeploymentReleaseWithBuildRead(DeploymentReleaseRead)` to
      `api/app/models/core.py` with `build: Optional["BuildRead"] = None`, placed
      next to `DeploymentReleaseRead`. Keep `build_id` inherited — the response
      carries both the id and the object. **Both** release endpoints return this
      model.
- [x] 1.1a Leave `DeploymentRead.applied_release` typed as the build-less
      `DeploymentReleaseRead`. Widening it would pull builds into every
      deployment read, and under `lazy="raise"` would *raise* rather than merely
      cost joins, because deployment queries carry no `joinedload` (design D3).
- [x] 1.2 Export it from `api/app/models/__init__.py` and add
      `DeploymentReleaseWithBuildRead.model_rebuild()` alongside the existing
      `DeploymentRead.model_rebuild()`, so the `BuildRead` forward reference
      resolves after `models/build.py` is imported (design D3).
- [x] 1.3 Add the ORM relationship to `DeploymentReleaseORM`:
      `build: Optional["BuildORM"] = Relationship(sa_relationship_kwargs={
      "viewonly": True, "lazy": "raise"})`. No import of `BuildORM` into
      `core.py` — the forward reference resolves from the mapper registry, and
      importing it would be a cycle (design D3).
- [x] 1.4 Use `lazy="raise"`, **not** `lazy="joined"`: the latter nests under
      `DeploymentORM`'s two already-joined release relationships and takes every
      deployment read from 13 joins to 15 (design D3).
- [x] 1.5 Confirm no schema change is needed: `deployment_release` already holds
      every field read here, `build_id` already carries the foreign key the join
      uses, and status stays derived. **No Alembic migration.**

## 2. Release service

- [x] 2.1 Add `list_releases(session, *, deployment_id, user_id=None)` to
      `api/app/services/deployments.py`. Resolve the deployment through
      `_get_deployment_orm` first so a foreign or missing deployment raises
      `NotFoundException` identically, and treat `DEPLOYMENT_STATUS_DELETED` as
      not found, matching `get_deployment`.
- [x] 2.2 Order the listing by `DeploymentReleaseORM.number` **descending** —
      number, not a timestamp (spec: ordering must not depend on clock
      resolution) — and return `list[DeploymentReleaseWithBuildRead]`.
- [x] 2.3 Add `get_release(session, *, deployment_id, number, user_id=None)`
      returning `DeploymentReleaseWithBuildRead`. Same deployment resolution, then
      a lookup on `(deployment_id, number)`; raise `NotFoundException` for a
      number the deployment has never reached.
- [x] 2.4 Apply `.options(joinedload(DeploymentReleaseORM.build))` to **both**
      the `get_release` and the `list_releases` queries, so the builds arrive on
      the same statement as the releases — one SELECT with a `LEFT OUTER JOIN`,
      never a lookup per row (design D3).
- [x] 2.5 The join must stay **outer**. A release naming no build is the normal
      case for products that build nothing; an inner join would silently drop
      those rows from the listing, which the spec forbids.
- [x] 2.6 Never read `release.build` without an eager load anywhere. `lazy="raise"`
      makes that an `InvalidRequestError` rather than an N+1, which is the point
      — do not "fix" such an error by relaxing the relationship.

## 3. Release API routes

- [x] 3.1 Add `api/app/api/releases.py` with
      `APIRouter(prefix="/users/{user_id}/deployments/{deployment_id}/releases",
      tags=["releases"])` (design D1).
- [x] 3.2 `GET ""` → `list[DeploymentReleaseWithBuildRead]`, `Depends(require_self)`,
      passing `None if current_user.is_admin else user_id` as the service scope.
      Document 403/404 in `responses=` and write the docstring in the house
      style of the neighbouring routes (Authorization / Parameters / Behavior /
      Errors).
- [x] 3.3 `GET "/{number}"` → `DeploymentReleaseWithBuildRead`, with `number: int =
      Path(..., ge=1, description=...)` — the per-deployment release number, not
      the `uuid4` (design D2). Same guard and scope as 3.2.
- [x] 3.4 Register the router in `api/app/main.py` under the `/api` prefix.

## 4. Relocate the builds API

- [x] 4.1 Change `api/app/api/builds.py`'s router to
      `APIRouter(prefix="/users/{user_id}/builds", tags=["builds"])`.
- [x] 4.2 Add `Depends(require_self)` to all four routes (create, list, get,
      log) and delete `_resolve_scope` entirely (design D4).
- [x] 4.3 Remove the `user_id` query parameter from `list_builds`; scope the
      service call with `None if current_user.is_admin else user_id` from the
      path.
- [x] 4.4 Keep `create_build` taking its owner from `current_user.id` — the path
      `user_id` is the authorization subject, not the input — and keep
      `BuildCreate`'s `extra="forbid"` so a body `user_id` is still a 422.
- [x] 4.5 Update the `Location` header on create to
      `/api/users/{user_id}/builds/{build_id}`.
- [x] 4.6 Update the docstrings and `responses=` on all four routes: the listing
      no longer describes a query parameter, and each route now documents 403
      for naming another account.
- [x] 4.7 Update the cross-reference in `api/app/api/artifacts.py:41` ("then
      `POST /api/builds` with the `artifact_id`") to the nested path.

## 5. API tests

- [x] 5.1 Repoint every path in `api/tests/test_builds.py` to
      `/api/users/{user_id}/builds…` and delete the two `?user_id=` cases
      (`test_builds.py:333`, `:344`), replacing them with path-based
      equivalents: an admin listing another user's builds succeeds, a non-admin
      doing so is 403.
- [x] 5.2 Add a test that the old `/api/builds` and `/api/builds/{id}` paths
      return 404 (spec: the root-level build paths are gone).
- [x] 5.3 Add a test that `POST /api/users/{other_id}/builds` is 403 for a
      non-admin, and that a successful create's `Location` is the nested path.
- [x] 5.4 New `api/tests/test_release_api.py`: listing returns releases
      numbered highest-first; queued, failed and in-flight releases all appear;
      another deployment's releases do not.
- [x] 5.5 Single-release tests: read by number; an unreached number is 404; the
      same number on two deployments returns each one's own release.
- [x] 5.6 Inlining tests, against **both** endpoints: a release naming a build
      returns the build object with its `image`; a release naming none returns
      `build: null` and still appears in the listing (the outer join).
- [x] 5.7 **Query-count regression test.** List a deployment's releases while
      counting statements on the engine (an `after_cursor_execute` listener) and
      assert the count is constant — the same for three releases as for ten.
      This is the spec's "listing many releases does not multiply queries" and
      is what stops a later refactor from turning the join back into an N+1;
      `lazy="raise"` guards the accidental case, this guards the deliberate one.
- [x] 5.8 Assert the deployment endpoints did **not** get wider: a deployment
      listing must still not load builds. Cheapest form is the same statement
      counter plus an assertion on the emitted SQL.
- [x] 5.9 Authorization tests: a non-admin naming another account is 403; a
      foreign `deployment_id` under the caller's own account is 404 (not 403);
      an admin reads another user's releases; a deleted deployment is 404.
- [x] 5.10 A status test covering the derived values — at minimum `queued` (no
      `started_at`), `failed` (`ended_at` + `error`), and `abandoned` (started
      longer ago than `reconcile_job_lease_seconds`, not ended).

## 6. `caelus` CLI parity

- [x] 6.1 Add `caelus list-releases <user_id> <deployment_id>` to
      `api/app/cli.py`, next to `get-deployment`, using `_require_cli_user`,
      `_exit_for_domain_error` and `_echo_yaml_entity` like its neighbours
      (design D9).
- [x] 6.2 Add `caelus get-release <user_id> <deployment_id> <number>` the same
      way.
- [x] 6.3 Scope both to the acting user unless they are an admin, matching
      `list-deployments`/`get-deployment`.
- [x] 6.4 Add CLI tests alongside the existing deployment-command tests: output
      shape, a 404 for an unreached number, and the non-admin scope refusal.

## 7. `freepod` client — shared table helpers

- [x] 7.1 Create `cli/src/freepod/table.py` holding `parse_time`, `format_time`,
      `format_duration`, `abbreviate`, `render`, `GAP`, `BLANK` and
      `SHORT_DIGEST`, moved verbatim from `history.py` (design D7). Keep it a
      leaf module — it must import nothing from the package but `.` errors, if
      that.
- [x] 7.2 Rewrite `history.py` to import them from `table.py`, keeping its
      build-specific pieces (`COLUMNS`, `LIVE_MARKER`, `list_builds`,
      `deployed_image`, `duration`, `rows`) in place.
- [x] 7.3 Confirm `cli/tests/` still passes unchanged — the move must not alter
      behavior. Where a test imports a moved helper from `history`, repoint the
      import rather than re-exporting from `history`.

## 8. `freepod releases`

- [x] 8.1 Add `cli/src/freepod/releases.py`: `list_releases(api, user_id,
      deployment_id)` calling
      `GET /api/users/{uid}/deployments/{did}/releases`, preserving the
      platform's order and validating the response is a list of objects (the
      shape `history.list_builds` checks for).
- [x] 8.2 Add `applied_number(deployment)` reading
      `deployment["applied_release"]["number"]`, returning `None` for every way
      of not knowing (design D8). Never read `desired_release`.
- [x] 8.3 Add `rows(...)` and `COLUMNS = ("", "RELEASE", "STATUS", "CREATED",
      "DURATION", "IMAGE")`, with duration measured from `started_at` (not
      `created_at`) via the shared helpers, and `LIVE_MARKER` on the applied
      release. The image comes from the **inlined build** on each listed
      release, so the table needs no second request; abbreviate it with the
      shared `abbreviate` and show `BLANK` where a release names no build.
- [x] 8.4 Wire `freepod releases` into `cli/src/freepod/cli.py` with `--limit`
      (default matching the builds command) and `--all`, refusing a non-positive
      `--limit` as a `UsageError`.
- [x] 8.5 Preflight in the command: `require_project`, then refuse with a
      `UsageError` naming the fix when the project records no deployment, and
      when the project's environment differs from the target — mirroring
      `delete.delete`'s two checks.
- [x] 8.6 Call `api.me()` before the reads (the id the nested paths need, and
      the request that exercises the credential), then read the deployment for
      the mark and the releases for the table.
- [x] 8.7 Table to stdout; the mark's legend and the withheld count to stderr
      via `context.say`, so a redirected listing carries rows only.
- [x] 8.8 Surface a failed release's error to the reader — either in a column or
      as a stderr note per failed row — without breaking the table's column
      alignment.

## 9. `freepod builds` follows the relocation

- [x] 9.1 `history.list_builds(api)` takes a `user_id` and calls
      `GET /api/users/{user_id}/builds`; update its docstring, which names the
      old path in two places.
- [x] 9.2 Update the `builds` command in `cli.py` to pass the `user_id` it
      already reads from `api.me()`.
- [x] 9.3 Repoint `cli/src/freepod/build.py`: `create_build`
      (`POST /api/users/{uid}/builds`), the log poll (`build.py:268`) and the
      final build read (`build.py:366`). Each needs the `user_id` threaded in
      from the caller in `deploy.py`, which already has it.
- [x] 9.4 Update `deploy.py`'s call sites to pass `user_id`, and its module
      docstring where it names the old endpoints.

## 10. `freepod` client tests

- [x] 10.1 Repoint the fake platform's paths in `cli/tests/test_deploy.py`
      (`:257`, `:263`, `:348`, `:693`, `:742`) and `cli/tests/test_tos.py`
      (`:271`, `:288`) to the nested build paths.
- [x] 10.2 New `cli/tests/test_releases.py`: the listing is the project's
      deployment; order is preserved; the applied release is marked and a failed
      newest release does not move the mark; no applied release means no mark.
- [x] 10.3 Refusal tests: no project file, a project with no deployment, and a
      project on another environment each fail as usage errors naming the fix.
- [x] 10.4 Bounding tests: `--limit` truncates and reports the withheld count to
      stderr, `--all` lifts it, a non-positive `--limit` is a usage error.
- [x] 10.5 Stream-discipline test: the table is on stdout and the legend and
      counts are not, matching the equivalent build-history test.

## 11. Release the client

- [x] 11.1 Bump `__version__` in `cli/src/freepod/__init__.py` — a client built
      before this change cannot talk to a platform carrying it. `USER_AGENT`
      derives from it, so nothing else needs touching.
- [x] 11.2 Do **not** tag or publish as part of the implementation; the
      `freepod-v*` tag is a deliberate, separate act (AGENTS.md § Client CLI).

## 12. Documentation

- [x] 12.1 `api/README.md`: update the endpoint table (`:382`), the three-phase
      build flow (`:836`), the log section (`:875`), and add the two release
      endpoints.
- [x] 12.2 `AGENTS.md`: update the Builds architecture note where it describes
      the subsystem's routes, and add the release read surface.
- [x] 12.3 `cli/DEVELOPMENT.md`: add `table.py` and `releases.py` to the module
      map, add a "The releases listing" section covering the mark and the
      project-scoping, and update "The build history" where it names
      `GET /api/builds` (`:424`).
- [x] 12.4 `cli/README.md`: document `freepod releases` — it is end-user surface,
      so this file changes.

## 13. Verification

- [x] 13.1 `cd api && uv run --no-sync pytest` passes.
- [x] 13.2 `cd cli && uv run pytest` passes.
- [x] 13.3 `openspec validate releases-api-and-nested-builds --strict` passes.
- [x] 13.4 Check the generated OpenAPI (`/api/openapi.json`) shows the two
      release routes and the nested build routes, and no route at `/api/builds`.
