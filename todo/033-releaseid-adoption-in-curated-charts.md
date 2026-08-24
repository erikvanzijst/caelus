# Issue 033: `caelus.releaseId` Adoption In Curated Charts

## Goal
Let a curated deployment's log lines be attributed to the release that produced
them, as `custom` already allows.

## Status: no longer a blocker for vars
This started as a prerequisite for curated products adopting vars: a Secret
whose *contents* change leaves the rendered pod spec byte-identical, so Helm
has nothing to roll, and the curated charts ignore `caelus.releaseId`.

Vars Secrets are now named per release (`{deployment}-vars-{number}`, design.md
D10), so a var change alters the pod template on its own and the rollout
restarts the pod in any chart, stamped or not. **This issue is now only about
log attribution**, which is what `releaseId` was built for: without the label,
a curated deployment's log lines cannot be attributed to one release while two
rollouts' pods write concurrently.

## Scope
1. In each curated chart (`nextcloud`, `immich`, `vaultwarden`, `matrix`),
   stamp `caelus.releaseId` onto the **pod template** only:
   - never `spec.selector.matchLabels` (immutable), never the Service selector
     — see `custom.podLabels` in `products/custom/chart/templates/_helpers.tpl`
     for the precedent and the reasoning.
   - emit no label at all when `releaseId` is empty, so the chart still renders
     standalone.
2. Bump each chart version and repoint its catalog `chart_version`.
3. A checksum annotation over the vars Secret is *not* an alternative here:
   the restart it would force already happens through the Secret's name.

## Required Tests
1. Rendering with a `releaseId` puts it on the pod template and nowhere else
   (mirror `test_custom_chart.py::test_the_release_id_never_reaches_a_selector`).
2. Two renders differing only in `releaseId` differ only in the pod template.
3. The chart still renders with no `releaseId` set.

## Acceptance Criteria
1. A curated deployment's pods carry `caelus.dev/release-id`.
2. Every curated chart renders unchanged when `releaseId` is absent.

## Notes
Was a hard prerequisite for D14 (curated products adopting vars) until
per-release Secret naming landed; see `openspec/changes/deployment-vars/design.md`
§ D10.
