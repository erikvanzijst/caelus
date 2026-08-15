## 1. Package scaffolding

- [x] 1.1 Create `cli/pyproject.toml`: name `freepod`, `requires-python = ">=3.9"`, deps `click`, `httpx`, `pathspec>=1.0`, console script `freepod = freepod.cli:main`, src layout
- [x] 1.2 Create the `cli/src/freepod/` package skeleton with the modules from design D1 (`cli`, `config`, `auth`, `api`, `project`, `values`, `archive`, `build`, `deploy`) and `__main__.py`
- [x] 1.3 Add `cli/tests/` with a pytest config and a shared `conftest.py` providing a temp-HOME fixture and a mock HTTP transport
- [x] 1.4 Verify a clean install into an isolated environment yields a runnable `freepod --help` that exits 0 and imports nothing from `api/`

## 2. Environments and configuration

- [x] 2.1 Implement `config.py`: the `prod`/`dev` environment table (client id, API base, issuer) with `prod` as default and `FREEPOD_ENV` override
- [x] 2.2 Reject an unrecognized environment name with a usage error naming the accepted values
- [x] 2.3 Implement the config directory resolution (`${XDG_CONFIG_HOME:-~/.config}/freepod`), creating it mode `0700`
- [x] 2.4 Tests: default is `prod`, explicit selection wins over `FREEPOD_ENV`, unknown name is a usage error, directory permissions are `0700`

## 3. Authentication

- [x] 3.1 Port the loopback + PKCE flow from `cli/freepod_cli.py` into `auth.py`: ephemeral `127.0.0.1` port, exact `/callback` path, `state` verification, bounded wait, 404 for other paths
- [x] 3.2 Port the device authorization grant: PKCE on the device endpoint, verifier on every poll, handling of `authorization_pending`, `slow_down`, `expired_token`, `access_denied`
- [x] 3.3 Port browser-reachability detection and the "which flow and why" message, with `--loopback` / `--device` overrides
- [x] 3.4 Implement the token cache: `tokens.json` keyed by environment, file mode `0600` inside the `0700` directory, refresh-then-fall-back-to-login on load
- [x] 3.5 Guarantee no raw token is ever printed; expose decoded claims under `--verbose` only, never used for a trust decision
- [x] 3.6 Implement `freepod login`, `freepod logout` (local only, stating where server-side revocation happens), and `freepod whoami` (`GET /api/me`)
- [x] 3.7 Tests: state mismatch is refused, loopback timeout does not hang, `slow_down` widens the interval, cache is per-environment, permissions are `0600`/`0700`, no token appears in any output

## 4. API client and the status-code contract

- [x] 4.1 Implement `api.py` over `httpx`: base URL from the environment, bearer auth, per-request timeouts
- [x] 4.2 Implement the status-code contract from design D15 and Appendix A: 401 stops, edge 403 (non-JSON body) refreshes, API 403 (JSON `detail`) stops, 404 `Not authenticated` is reported as a platform condition
- [x] 4.3 Enforce refresh-at-most-once per request; a second 403 becomes a permission error, never a login loop
- [x] 4.4 Make the 401 message name the `freepod-dev` group requirement when the target is `dev`
- [x] 4.5 Implement bounded-backoff retries for safe reads only (5xx and network errors); never auto-retry unsafe requests
- [x] 4.6 Tests: each row of the Appendix A table, the bounded-refresh rule against a always-403 endpoint, and that an unsafe request is not repeated

## 5. Project file

- [x] 5.1 Implement `project.py`: load, save, and upward-walking discovery of `.freepod.json`
- [x] 5.2 Implement the file format (`version`, `env`, `deployment`, `user_values`) with `deployment` null before first deploy
- [x] 5.3 Refuse when the file's `env` disagrees with the selected environment, reporting both
- [x] 5.4 Guarantee `image` is never written to the file, as a value or as null
- [x] 5.5 Report a clear "not initialized" error, naming `freepod init`, when no project file is found
- [x] 5.6 Tests: discovery from a subdirectory, environment mismatch refused, a successful deploy leaves `user_values` unchanged

## 6. Schema-driven values and prompting

- [x] 6.1 Implement `values.py`: walk `values_schema_json.properties`, prompt for each `required` key, skip optional keys
- [x] 6.2 Validate answers locally against `pattern`, `minLength`, `maxLength`, and `enum`, re-prompting with the constraint explained
- [x] 6.3 Implement hostname handling: identify by case-insensitive `"title": "hostname"`, lowercase, append the first `GET /api/domains` suffix when the input has no dot
- [x] 6.4 Implement the hostname check against `GET /api/hostnames/{fqdn}`, re-prompting with the reported `reason`
- [x] 6.5 Make the routine reusable by both `init` and `deploy` (design D5), taking a "prompt for these missing keys only" mode
- [x] 6.6 Fail with the field named when a value is missing and no prompt can be presented
- [x] 6.7 Tests: an unknown required property is prompted for, constraint violations re-prompt, a bare label is completed to a platform subdomain, an unusable hostname re-prompts

## 7. `freepod init`

- [x] 7.1 Resolve the `custom` product by slug from `GET /api/products`; report "this instance does not offer user-supplied deployments" when absent
- [x] 7.2 Read `product.template.values_schema_json` and drive prompting from it
- [x] 7.3 Write `.freepod.json` with the selected environment and collected values; make no API writes
- [x] 7.4 Refuse to overwrite an existing project file unless `--force`, and warn that `--force` discards the deployment pointer
- [x] 7.5 Tests: no deployment is created, a failed file write leaves nothing behind, existing file is protected, missing product is explained in the user's terms

## 8. Project archive

- [x] 8.1 Implement the ignore stack in `archive.py` using `pathspec.GitIgnoreSpec`: hard excludes, built-in defaults, `.gitignore` (with `--no-gitignore`), `.freepodignore` last
- [x] 8.2 Implement the directory walk with per-directory `.gitignore` layering, patterns rewritten relative to the project root
- [x] 8.3 Prune excluded directories rather than walking and filtering, matching git's rule that a file under an excluded directory cannot be re-included
- [x] 8.4 Include `.freepod.json`; exclude `.env.local` and `.env.*.local` but **not** `.env` (design D11)
- [x] 8.5 Drop and report entries the builder's `data` filter would refuse: sockets, FIFOs, device nodes, symlinks resolving outside the project
- [x] 8.6 Emit project files at the archive root with relative paths, sorted by path, `uid`/`gid` 0, blank `uname`/`gname`
- [x] 8.7 Write to a `SpooledTemporaryFile` (~32 MiB memory threshold) and remove it on success and failure alike
- [x] 8.8 Print the packed size, and the largest entries under `--verbose`
- [x] 8.9 Tests: the `node_modules/` + `!node_modules/keep.txt` divergence resolves the way git does, the `node_modules/*` idiom re-includes, `.git/` cannot be re-included, a committed `.env` is packed, repacking is reproducible, excluded directories are not enumerated

## 9. Upload and build

- [x] 9.1 Mint the upload slot with `POST /api/artifacts` **after** packing
- [x] 9.2 Compare the packed size against the slot's `max_bytes` before transferring; refuse reporting both numbers
- [x] 9.3 Enforce that no other platform bound is hardcoded — no entry-count or uncompressed-size check anywhere in the client (design D12)
- [x] 9.4 Submit `multipart/form-data` with every `fields` entry verbatim and in order, file part named `file` last, wrapped in a `click.progressbar`
- [x] 9.5 On a 403 from the object store, re-mint once and resubmit the same archive (design D9 — the retry must carry the whole archive again; `httpx` rewinds a seekable file field itself, so the binding requirement is that the progress-reporting wrapper expose `seek`/`tell`, without which the retry becomes a chunked zero-byte upload that the policy's lower bound of 1 rejects, blaming the platform for a client bug); fail with the store's response if the resubmit is refused too
- [x] 9.6 Create the build with `POST /api/builds` carrying only `artifact_id`; treat a 200 as re-attaching to an in-flight build and say so
- [x] 9.7 Stream the log by `Range: bytes={offset}-`, writing chunks to `sys.stdout.buffer` and flushing, advancing the offset by `len(chunk)`
- [x] 9.8 Read `X-Build-Status` from every response; stop on `succeeded`/`failed`/`canceled` with no extra status request; treat an empty 206 as normal
- [x] 9.9 Poll at 1s while output arrives, backing off to 3s while empty; print `Queued…` while the status is `queued`
- [x] 9.10 On interrupt, report that the build continues and name its id
- [x] 9.11 On a non-successful terminal status, stop before release and exit 4; on success read `image` from `GET /api/builds/{id}`
- [x] 9.12 Tests: fields sent verbatim and file last, oversized archive refused before transfer, an expired slot re-minted once **with the resubmit carrying the same byte count as the first attempt** (assert the count, not merely that a retry occurred — it is the only thing separating a real replay from an empty one), 200 reported as re-attach, no byte displayed twice, empty range is not an error, streaming stops at a terminal status

## 10. Deploy preflight and release

- [x] 10.1 Implement preflight in the design D6 order: project file → environment check → `GET /api/me` → `GET /api/products` → recorded deployment → the plan, on a first deploy only. The plan read was added to preflight after dev showed why: the `custom` product there publishes no plans at all, and selecting the plan where the create request needs it meant a guaranteed refusal arriving after a full build
- [x] 10.2 Report a deployment recorded but absent from the platform before packing, naming `--recreate`
- [x] 10.3 Prompt for any `required` key of the target template missing from `user_values`, persist it, and continue — never redirect to `init`
- [x] 10.4 Check the hostname only when it is new or changed relative to the recorded deployment (design D14)
- [x] 10.5 Implement first-deploy creation: select the first plan whose current template has `price_cents == 0`, refuse clearly when none exists, `POST` with `desired_template_id`, `plan_template_id`, and `user_values_json` carrying the built image
- [x] 10.6 Write the deployment's `id` and `name` to the project file immediately on creation
- [x] 10.7 Implement subsequent-deploy update: wait for `ready`/`error` with the status shown, then `PUT` with `product.template.id` and the complete user-values document
- [x] 10.8 Announce a product template move (`Product template 4 → 5`) when the canonical template differs from the deployment's
- [x] 10.9 Detect a template-compatibility failure at release from the **409** whose `detail` begins `user_values_json is invalid:` and report it as such, naming the template move and the platform's message. Preflight (10.3) only catches a target template that *added* a required key; a tightened `pattern`, a removed property under `additionalProperties: false`, or any other narrowing passes preflight and fails here, after the build has been spent. The status carries no signal — schema failure raises `IntegrityException`, which `ERROR_STATUS` maps to 409 alongside six unrelated causes — so the `detail` prefix is the only discriminator available. Treating it as a generic conflict tells the user to retry something that can never succeed
- [x] 10.10 Poll the deployment to a terminal status using the `generation` from the create/update response; report the live address on success and `last_error` with exit 5 on failure
- [x] 10.11 Discriminate the release 409 on its `detail`, not on the status, which cannot carry the distinction. On the update path it means any of: `Deployment is not in ready state`; an operation already in progress; `Can only upgrade to newer versions, not downgrade`; `Upgrade template must belong to the same product`; a hostname reason (`in_use` and the other four); `user_values_json is invalid:` (10.9); or `product template has an invalid values_schema_json:` — the last being a **platform defect**, not something the user can fix, and it must not be reported as though their values were at fault. Only the first two are worth suggesting a retry for. Prefix matching on a human-readable string is fragile, so pin each mapping with a test and fall back to reporting the raw detail verbatim rather than guessing when nothing matches
- [x] 10.12 Implement `--recreate`: discard the deployment pointer and create a new deployment
- [x] 10.13 Tests: build precedes creation, a single rollout on first deploy, no free plan is refused, partial user values are never sent, a stale `ready` is not mistaken for success, an unchanged hostname is not re-checked, and each of the seven release-409 causes maps to its own message — the `user_values_json is invalid:` case naming the template move, the broken-schema case reported as a platform defect, and an unrecognized detail quoted verbatim rather than guessed at

## 11. Command surface and cross-cutting behavior

- [x] 11.1 Wire the `click` entry point: global `--env`, `--verbose`, `--quiet`, `--timeout`; `deploy` adds `--no-gitignore` and `--recreate`; `init` adds `--force`
- [x] 11.2 Enforce stream discipline: results on stdout, progress and diagnostics on stderr
- [x] 11.3 Implement the exit-code table (0/1/2/3/4/5) and map every failure path onto it
- [x] 11.4 Resolve `--timeout` against the per-operation defaults from design D16 (login 300s, build 1800s, rollout 600s), state in the help text that it applies to whichever wait is in progress, and report a timeout as having stopped waiting rather than as a failure
- [x] 11.5 Suppress color for a non-TTY stdout and when `NO_COLOR` is set
- [x] 11.6 Tests: piped stdout carries only results, each exit code is produced by its condition, a timeout message states the operation continues

## 12. End-to-end verification

- [x] 12.1 Verify `login` against `dev` with both flows — loopback on a desktop, device inside a container
- [x] 12.2 Confirm the `custom` product is visible to a **non-admin** on the target environment before attempting 12.3–12.4: `GET /api/products` unauthenticated must list it. An `admin`-visibility product resolves for administrators and correctly reports "this instance does not offer user-supplied deployments" for everyone else — correct behavior, but not a passing end-to-end, and it will read as a client bug to whoever hits it
- [x] 12.3 Verify `init` in an empty project **as a non-admin**: product resolved by slug, hostname completed and checked, `.freepod.json` written, nothing created server-side
- [x] 12.4 Verify a first `deploy` end to end on `dev`: one rollout, no placeholder page, live at the reported address
- [x] 12.5 Verify a second `deploy`: waits for `ready`, updates, and rolls out the new image
- [ ] 12.6 Verify interrupt handling mid-build: the build continues and its id is reported
- [x] 12.7 Verify `logout` then `deploy` reports "not authenticated" and exits 3
- [ ] 12.8 Verify the edge-403 refresh path live, which unit tests cannot reach: let a deploy sit in log streaming past the 300s access-token lifetime and confirm the refresh happens transparently, with no re-authentication and no interruption to the stream
- [ ] 12.9 Repeat 12.4 against `prod` once dev is green

## 13. Documentation and cleanup

- [x] 13.1 Write `cli/README.md`: installation, the five commands, the two flows and their traps, the status-code contract, ignore rules with the re-inclusion idiom **and the anchoring requirement** (an unanchored negation such as `!keep.txt` does not reach inside a default-excluded directory — name the path, `!node_modules/keep.txt`; and anchoring is needed at every level it must reach, so `!node_modules/**/keep.txt` re-includes only the shallow one), and the security note that a token carries full account authority
- [x] 13.2 Delete `cli/freepod_cli.py` once the package covers everything its README documented
- [x] 13.3 Update `AGENTS.md`: add `cli/` to the monorepo layout, its quick-start commands, and its place in the contribution checklist
- [x] 13.4 Cross-check that no remaining file references `cli/freepod_cli.py`

## 14. CI

- [x] 14.1 Add a CI job that installs `cli/` and runs its test suite
- [x] 14.2 Build the wheel and sdist in CI and verify the wheel installs and runs `freepod --help` in a clean environment
- [x] 14.3 Verify the test suite passes on the lowest supported Python (3.9) as well as the current one

## 15. Terms of Service acceptance

- [x] 15.1 Implement `tos.py`: read `/api/me/tos-acceptance`, distinguish the accepted version from the platform's current one, and record acceptance with the version the platform reported
- [x] 15.2 Settle acceptance in deploy preflight, before packing and only when a deployment is about to be created — the platform's own refusal is a 400 from the create call, after the build is spent
- [x] 15.3 Order it after the non-interactive preflight reads, so a deploy that cannot succeed anyway never presents the terms
- [x] 15.4 Offer acceptance from `login` without gating on it: a decline, or no terminal, still completes the login, because automation and read-only use do not need it
- [x] 15.5 Present all three documents with links on the target environment, using the web UI's agreement wording verbatim
- [x] 15.6 Refuse to guess a version the platform does not report; present nothing and direct the user to the web interface
- [x] 15.7 Report the cause of a refusal distinctly (declined / no terminal / version unreported), never one as another
- [x] 15.8 Map the create-time 400 `Terms of Service must be accepted before deploying` to its own message, as a backstop for acceptance withdrawn mid-deploy
- [x] 15.9 Tests: an unaccepted first deploy packs nothing, an update never asks, a declined agreement records nothing, the submitted version is the reported one, no date literal appears anywhere in the package, and each refusal cause maps to its own message
- [x] 15.10 Verify live once the API reports `current_version`: accept from `login` as a fresh non-admin account, then deploy
