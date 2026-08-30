## Why

OpenSpec already records this platform's intent, behavior and decision lineage:
114 capability specs under `openspec/specs/` and a design document per change
under `openspec/changes/archive/`. The prose docs then say it all again.
`api/README.md` is 1501 lines, `cli/DEVELOPMENT.md` 1099, `ui/README.md` 390,
and `AGENTS.md` carries a further 80 lines of Architecture Notes — the large
majority of which restates requirements, endpoint tables, field lists,
validation rules and rationale that a spec or a design document already owns.

Duplication of this size is not merely wasteful. Two texts describing one
behavior drift, and once they disagree a reader cannot tell which is current
without reading the code. The rule that produced it was explicit — the
`AGENTS.md` contribution checklist said "update api/README.md, ui/README.md,
cli/DEVELOPMENT.md, tf/README.md, and AGENTS.md when workflow changes" with no
statement of what each document owns — and that rule has now been replaced
(same branch) with a **Documentation Layering** section that makes OpenSpec the
source of truth and prose docs a terse index over it.

The rule governs new writing. The ~2,400 existing lines of restated prose still
pull against it: an agent or a contributor who reads `api/README.md` will match
the register it finds. This change retires that counter-example.

## What Changes

- **Rewrite the capability-restating sections** of `api/README.md`,
  `cli/DEVELOPMENT.md`, `ui/README.md`, `tf/README.md` and the `AGENTS.md`
  Architecture Notes into the form the new `AGENTS.md` § Documentation Layering
  prescribes: a few sentences of orientation, then markdown links to the
  governing `openspec/specs/<capability>/spec.md` and, where the reasoning
  matters, to `openspec/changes/archive/<date>-<slug>/design.md`.
- **Keep, unchanged, what prose legitimately owns**: how to run, build, test
  and operate each component; the codebase map; troubleshooting; and narrative
  that spans several capabilities and therefore lives in no single spec.
- **Relocate rather than delete** any rationale found in a README that is
  *absent* from its spec and design document. The audit is part of the work: a
  paragraph that exists only in a README is not duplication, and deleting it
  loses information. It moves into the spec (if normative) or is left in place
  with a note (if operational).
- **Add a markdown link check** to CI over the repo's `*.md`, so a spec
  directory renamed during a future `openspec archive`/`sync` breaks the build
  instead of silently rotting every link this change introduces.
- Done per-document, in the task order below, so each step is reviewable on its
  own and the change can stop after any of them.

## Capabilities

### New Capabilities

<!-- None. This change alters no system behavior: no endpoint, schema,
     reconciler path, CLI command or UI surface changes. It rewrites prose
     documentation and adds a CI link check. Per the proposal instruction,
     a docs-and-tooling change declares `skip_specs: true` rather than
     inventing a requirement to satisfy validation. -->

### Modified Capabilities

<!-- None. The specs under openspec/specs/ are the target of the new links,
     not the subject of the change. Where the audit finds rationale that
     belongs in a spec but is missing from it (see "Relocate rather than
     delete" above), that spec is edited as an errata fix under its existing
     requirements — it does not change what the system must do, so it is not
     a delta. -->

## Impact

- **Docs:** `api/README.md`, `cli/DEVELOPMENT.md`, `ui/README.md`,
  `tf/README.md`, `AGENTS.md`. Expected reduction on the order of 2,000 lines;
  the exact figure falls out of the audit, and shrinkage is a side effect of
  the rule, not the goal.
- **Specs:** possible errata edits to `openspec/specs/**` where the audit finds
  rationale that a README held and a spec should have.
- **CI:** one new workflow step (markdown link check). No test, build or
  deployment path changes.
- **No code, schema, API, chart or Terraform change.** Nothing ships to users;
  `cli/README.md` (the PyPI landing page) is explicitly out of scope, as it is
  written for end users and carries no platform internals.
- **Readers:** a reader who wants the contract now follows one link instead of
  reading prose that may or may not still be true. The cost is the extra hop;
  the design document weighs that trade-off.
