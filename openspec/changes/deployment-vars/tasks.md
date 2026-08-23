## 1. Encryption keyring

- [ ] 1.1 Add `cryptography` to `api/pyproject.toml` and lock it.
- [ ] 1.2 Add `var_encryption_keys: list[str] = []` to `api/app/config.py` (env
      `CAELUS_VAR_ENCRYPTION_KEYS`, comma-separated, newest-first). Document that only the
      first key encrypts and that all of them decrypt.
- [ ] 1.3 New `api/app/services/var_crypto.py`: build `{fingerprint: Fernet}` from the
      configured list, where fingerprint is the first 4 bytes of
      `sha256(urlsafe_b64decode(key))` as lowercase hex (design.md D5). Expose
      `encrypt(plaintext) -> (ciphertext, key_id)`, `decrypt(ciphertext, key_id)`, and
      `current_key_id()`. Do **not** use `MultiFernet`; decryption is a direct lookup by
      `key_id`, and a missing key raises an error naming the fingerprint.
- [ ] 1.4 Startup verification, run by both `app.main` and `caelus worker`: fail on a
      fingerprint collision between configured keys; fail when the list is empty while any
      reachable template declares vars; fail when any `key_id` present in `deployment_var`
      is not configured. All three are fatal, not warnings (design.md D5).
- [ ] 1.5 A `caelus vars-rotate` operator command that sweeps rows where
      `key_id <> current`, re-encrypting in place in batches, resumable and safe to
      interrupt.
- [ ] 1.6 Unit tests: round-trip encrypt/decrypt; fingerprint is stable and independent of
      list position; prepending a key leaves existing rows readable and their `key_id`
      unchanged; a dropped key produces the naming error; each startup check fails as
      specified; a half-swept table is fully readable.

## 2. Data model and migration

- [ ] 2.1 Add `DeploymentVarORM` and `ReleaseVarORM` to `api/app/models/core.py` per the
      DDL in design.md D4, including the tombstone check constraint, both cascades, and
      indexes `ix_deployment_var_head` and `ix_deployment_var_key_id`.
- [ ] 2.2 Alembic migration creating both tables and all indexes. No existing table is
      altered.
- [ ] 2.3 Verify the migration on both backends the project supports, and confirm
      `distinct on` head resolution behaves identically (see the existing
      `cross-database-partial-index-parity` spec for the precedent).
- [ ] 2.4 Tests: cascade from `deployment` removes both var rows and release bindings; the
      check constraint rejects a row with a value and no `key_id`, and one with a `key_id`
      and no value.

## 3. Schema projections and marker validation

- [ ] 3.1 In `api/app/services/template_values.py`, add `derive_projections(schema)`
      returning the chart and vars projections by partitioning the root's `properties` and
      `required` on `x-caelus-target`, with the vars half's `additionalProperties` taken
      from the root's `x-caelus-vars-additional` (default `false`) — design.md D1.
- [ ] 3.2 Add `validate_vars(vars, vars_projection)`: coerce string values to the declared
      type per the table in design.md D7, then validate. Build error messages from
      `exc.json_path` and `exc.validator` only — **never** `exc.message`, which embeds the
      submitted value (design.md D13).
- [ ] 3.3 Point the existing `validate_user_values` at the chart projection so a runtime
      property is not also validated as a chart value.
- [ ] 3.4 Marker meta-validation in `api/app/services/templates.py` and
      `api/app/services/catalog.py`: `x-caelus-target: runtime` only on a top-level scalar
      property; name matching `^[A-Za-z_][A-Za-z0-9_]{0,63}$`; not a reserved name (D12);
      `x-caelus-sensitive` only on a runtime property. Reject at template creation and at
      catalog load.
- [ ] 3.5 Tests: the worked vaultwarden and `custom` examples in design.md derive exactly
      the projections shown; an unmarked schema derives an empty closed vars projection; a
      template with no schema rejects vars; each illegal marker is rejected with an error
      naming the property; a validation failure on a sensitive var yields a message
      containing neither the value nor any substring of it.

## 4. Vars service

- [ ] 4.1 New `api/app/services/vars.py` with head resolution (the `distinct on` query in
      design.md D4, tombstones filtered) in exactly one function.
- [ ] 4.2 Write path: take `select ... for update` on the deployment first (D4), diff
      against head, and insert rows only where the value or `sensitive` actually differs
      (D9 step 4). Tombstone on delete.
- [ ] 4.3 Merge (`PATCH`) and replace (`PUT`) semantics, `null` as delete, and an absent
      `value` meaning "leave unchanged" — rejecting an absent `value` for a key not in
      head.
- [ ] 4.4 Sensitivity resolution: schema-authoritative where declared, 400 on
      contradiction, caller-declared on an open projection defaulting to `false`. Flipping
      to non-sensitive requires a new value (design.md E6).
- [ ] 4.5 Enforce the limits and reserved names in design.md D12.
- [ ] 4.6 `snapshot_release(session, release_id, deployment_id)` inserting `release_var`
      for every non-tombstone head row.
- [ ] 4.7 `pending(deployment)` comparing head against the **applied** release's snapshot
      — never the desired one (design.md D8).
- [ ] 4.8 Tests covering edge cases E1–E6 and E9–E10 from design.md by name.

## 5. Vars API

- [ ] 5.1 Routes under `/api/users/{user_id}/deployments/{deployment_id}/vars`: `GET`,
      `PATCH`, `PUT` on the collection; `GET`, `DELETE` on `.../vars/{key}`. Owner and
      admin only, with the existing authorization guards.
- [ ] 5.2 Response serialization in one place, omitting `value` entirely for a sensitive
      var — not a mask, not a null, no digest (design.md D7). Every read of vars uses it.
- [ ] 5.3 Status codes per `deployment-vars-api`: 400, 403, 404, 409.
- [ ] 5.4 OpenAPI documentation for each endpoint, matching the docstring style already
      used in `api/app/api/users.py`.
- [ ] 5.5 Tests: the round-trip property (reading the collection and submitting it back
      unchanged deletes nothing and alters nothing); an admin reading another user's vars
      gets no sensitive values; a non-owner is refused; every limit and reserved name is
      rejected.

## 6. Deployment create/update and the release snapshot

- [ ] 6.1 Add write-only `vars` to `DeploymentCreate` and `DeploymentUpdate`. It must not
      appear on any read model.
- [ ] 6.2 Wire the transaction in `create_deployment` and `update_deployment` in the order
      given in design.md D9: lock, validate both halves, diff-insert vars, mint the
      release, bind the snapshot, enqueue. `vars` merges on update; it never replaces.
- [ ] 6.3 Confirm `update_deployment` never derives vars from `user_values_json`
      (design.md D3) — assert it in a test, since the failure mode is silent.
- [ ] 6.4 Tests: creating with vars gives the first release a non-empty snapshot; an update
      omitting `vars` leaves head intact and the new release captures it; a redeploy
      submitting values identical to head writes no new rows; a failed rollout leaves head
      unchanged and `pending` true (design.md D9).

## 7. Read models

- [ ] 7.1 `DeploymentRead.vars` (head) and `DeploymentRead.pending`, on the
      single-deployment read only. Do not add vars to the list response (design.md D8).
- [ ] 7.2 `DeploymentReleaseRead.vars` reporting that release's snapshot.
- [ ] 7.3 Tests: a deployment read reports head, not the applied snapshot; a release read
      reports its own snapshot and stays correct after head changes; the list response
      carries no vars and issues no per-row query.

## 8. Reconciler and chart

- [ ] 8.1 `vars_secret_name(deployment)` returning `f"{deployment.name}-vars"` — derived
      from the deployment, stable across releases. Read the caution in design.md D10 before
      naming it from anything else.
- [ ] 8.2 In `reconcile.py`, decrypt the desired release's snapshot and `upsert_secret` it
      into the tenant namespace before Helm runs, following `_ensure_object_storage`.
      Fail the reconcile naming the missing fingerprint if any row cannot be decrypted;
      never write a partial Secret (design.md E11).
- [ ] 8.3 `_build_vars_overrides` projecting only `{"caelus": {"vars": {"secretName": ...}}}`,
      returning `None` for an empty snapshot so no block and no Secret are produced.
- [ ] 8.4 In `products/custom/chart`, consume `caelus.vars.secretName` with `envFrom`,
      ordered **before** the object-storage source, and bump the chart version.
- [ ] 8.5 Tests: merged values contain the Secret name and no var value; a known plaintext
      appears in no captured log record from a full reconcile; an empty snapshot yields no
      Secret and no block; a var named like a platform credential does not reach the pod
      ahead of the platform's value.

## 9. CLI

- [ ] 9.1 `freepod var list|get|set|rm` in `cli/`, with `--json` emitting the wire shape
      verbatim and sensitive values shown as hidden in human output.
- [ ] 9.2 `freepod deploy --no-build`: mint a release from the applied release's image,
      passing its `build_id` through explicitly (design.md D11). Refuse when there is no
      applied release.
- [ ] 9.3 `var set`/`rm` apply by default over `--no-build`, with `--stage` to defer;
      several vars in one invocation produce one release; a write that would roll a
      deployment which is not ready fails and suggests `--stage`.
- [ ] 9.4 `--secret`, `-f FILE` (wire shape or `KEY=VALUE` lines, `-` for stdin), and a
      no-echo prompt for a bare `KEY` on a TTY.
- [ ] 9.5 `freepod deploy` reports pending vars before rolling.
- [ ] 9.6 Tests: the `list --json` → `set -f -` round trip changes nothing; batching
      produces one release; the staged path works against a provisioning deployment while
      the applying path returns 409.
- [ ] 9.7 Update `cli/README.md` and `cli/DEVELOPMENT.md`, and bump `__version__`.

## 10. UI

- [ ] 10.1 Carry `target` and `sensitive` through `flattenSchema` onto `SchemaField` in
      `ui/src/components/UserValuesForm.tsx`.
- [ ] 10.2 Partition the submission by `target` into `user_values_json` and `vars`.
- [ ] 10.3 Render a sensitive field as a `password` input that starts empty with an
      "unchanged" affordance and submits **no** `value` when untouched — an empty string
      would wipe the secret. No reveal control.
- [ ] 10.4 Show a pending indicator and an apply action on a deployment whose `pending` is
      true.
- [ ] 10.5 Tests: a schema with mixed targets produces two correctly partitioned payloads;
      an untouched sensitive field submits no `value`; an unmarked schema still submits
      everything as chart values.

## 11. Deployment wiring

- [ ] 11.1 Add the keyring to `secrets.auto.tfvars` and render it into a Kubernetes Secret
      in `tf/`, mounted into **both** the API and `caelus worker` (not `build-worker`).
- [ ] 11.2 Document the two-phase key introduction (distribute, then promote) in the
      runbook, including why skipping phase A breaks the reconciler (design.md § Migration
      Plan).
- [ ] 11.3 Deploy in the order given in the migration plan: migration → keyring → API and
      worker → chart → CLI.

## 12. Documentation

- [ ] 12.1 `api/README.md`: a "Deployment vars" section covering the two tables, head vs
      snapshot, the markers, and the write-only rule.
- [ ] 12.2 `AGENTS.md`: note that vars are the single channel into a pod's environment and
      that `user_values_json` configures the chart, not the process.
- [ ] 12.3 `products/catalog/catalog.schema.json`: regenerate so the markers are accepted,
      and verify with `openspec`-adjacent catalog checks that existing files still load.
- [ ] 12.4 Record in the repo's todo the two prerequisites this change deliberately leaves
      open: `caelus.releaseId` adoption in curated charts, and server-side `build_id`
      inheritance (design.md § Deferred work).
