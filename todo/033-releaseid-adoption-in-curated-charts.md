# Issue 033: `caelus.releaseId` Adoption In Curated Charts

## Goal
Make a var-only change actually restart the pod for curated products, so that
they can adopt deployment vars at all.

## Why This Blocks Something
`helm upgrade` does not restart pods when only a Secret's *contents* change —
the rendered pod spec is byte-identical, so Helm has nothing to roll. The
platform already projects `caelus.releaseId` into the merged values on every
reconcile (`api/app/services/reconcile.py:_build_release_overrides`), and
`products/custom/chart` stamps it into the `caelus.dev/release-id` pod label,
which is what makes the pod template differ per release.

**The curated charts ignore `releaseId`.** A curated product that adopted vars
today would take the new Secret and keep running the old configuration,
silently and indefinitely. That is why `deployment-vars` deliberately kept
curated products out of v1 (design.md D14) — the trap cannot be sprung by
accident while no curated schema declares a runtime property.

## Scope
1. In each curated chart (`nextcloud`, `immich`, `vaultwarden`, `matrix`),
   stamp `caelus.releaseId` onto the **pod template** only:
   - never `spec.selector.matchLabels` (immutable), never the Service selector
     — see `custom.podLabels` in `products/custom/chart/templates/_helpers.tpl`
     for the precedent and the reasoning.
   - emit no label at all when `releaseId` is empty, so the chart still renders
     standalone.
2. Bump each chart version and repoint its catalog `chart_version`.
3. Alternative worth considering per chart: a checksum annotation over the vars
   Secret. `releaseId` is preferred because it is already injected for every
   product and needs no per-chart knowledge of which Secrets exist.

## Required Tests
1. Rendering with a `releaseId` puts it on the pod template and nowhere else
   (mirror `test_custom_chart.py::test_the_release_id_never_reaches_a_selector`).
2. Two renders differing only in `releaseId` differ only in the pod template.
3. The chart still renders with no `releaseId` set.

## Acceptance Criteria
1. A var-only change to a curated deployment rolls its pods.
2. Every curated chart renders unchanged when `releaseId` is absent.

## Notes
Prerequisite for migrating any curated product onto vars (design.md D14 and
§ Migration Plan, in `openspec/changes/deployment-vars/design.md`).
