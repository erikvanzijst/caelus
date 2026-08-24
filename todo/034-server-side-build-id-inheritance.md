# Issue 034: Server-Side `build_id` Inheritance On Deployment Update

## Goal
Stop a deployment update that says nothing about builds from dropping the new
release's link to the build that produced the image it is running.

## Problem
`deployment_release.build_id` is written from the request. An update that omits
`build_id` writes `NULL`, so the release ships an image with no record of which
build produced it. The image itself is safe — it comes from
`user_values_json` — but the release's provenance is lost, and the loss is
silent.

Every client therefore has to pass the applied release's `build_id` back
explicitly, and two already do:

- `ui/src/components/DeployDialog.tsx` reads
  `applied_release.build_id` and passes it on every update, including the
  "apply staged vars" path;
- `freepod deploy --no-build` does the same (design.md D11).

That is the same rule implemented twice in two languages, free to drift, and
wrong by default for any client that does not know about it.

## Scope
1. In `update_deployment`, when the payload omits `build_id`, inherit it from
   the deployment's **applied** release rather than writing NULL.
2. Decide explicitly what an *explicit* `build_id: null` means — clearing the
   link, or the same as omitting it. `DeploymentUpdate.build_id` is
   `Optional[UUID]` with a `None` default, so telling the two apart needs
   `model_fields_set`, the same way `VarWrite.value` does.
3. Remove the client-side workarounds once the server owns the rule.

## Required Tests
1. An update omitting `build_id` produces a release naming the same build as
   the applied release.
2. An update supplying a different `build_id` overrides it.
3. A deployment whose applied release names no build still updates.
4. The UI/CLI paths keep working while their explicit pass-through is still in
   place (it should be a no-op, not a conflict).

## Acceptance Criteria
1. Release provenance survives an update from any client, including one that
   knows nothing about builds.
2. No client needs to echo `build_id` back to preserve it.

## Notes
Listed as deferred in `openspec/changes/deployment-vars/design.md`
§ Deferred work: "Changes behavior for existing clients", which is why it was
not folded into that change.
