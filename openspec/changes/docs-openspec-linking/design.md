## Context

See `proposal.md` § Why for the motivation. The constraints that shape the
approach:

- **Two OpenSpec artifacts, two different jobs.** `openspec/specs/<capability>/
  spec.md` is normative and answers *what must be true* (requirements and
  scenarios). `openspec/changes/archive/<date>-<slug>/design.md` answers *why
  it is that way*. They are not interchangeable. Worked example: `api/README.md`
  justifies the `{fingerprint:path}` route with "measured over 2000 random
  digests, 976 contained `/` and 971 contained `+`". That measurement appears
  in `openspec/changes/archive/2026-08-28-account-ssh-keys/design.md` and
  **not** in `openspec/specs/ssh-key-api/spec.md`, which states only that the
  route must accept such a fingerprint intact.
- **Archive paths are stable.** Changes archive to a dated, immutable
  directory. Capability directories under `openspec/specs/` are *not* stable —
  `openspec archive`/`sync` can rename or merge them.
- **`AGENTS.md` § Documentation Layering already landed on this branch.** The
  rule exists; this change makes the tree match it and adds the
  capability-rename rule to it (D5).
- **The docs in scope are uncontested.** Neither in-flight branch
  (`erik/cli-rust`, `erik/sftp-reachability`) touches `AGENTS.md`,
  `api/README.md`, `ui/README.md`, `cli/DEVELOPMENT.md` or `tf/README.md`
  against its merge base, so this rewrite races nothing.

## Goals / Non-Goals

**Goals:**

- Every capability-restating section in the docs in scope becomes a terse
  entry plus links, per `AGENTS.md` § Documentation Layering.
- No information is lost: content that exists only in a README is relocated,
  not deleted.
- Link rot — the one failure the rewrite introduces — is guarded by the
  Documentation Layering rule that a capability rename updates the prose links
  pointing at it, so this does not trade a staleness problem for a rot
  problem.
- Each document lands as its own reviewable step.

**Non-Goals:**

- Rewriting the specs themselves. Specs are the link target, not the subject.
  The one exception is errata — see D6.
- `cli/README.md`. It ships to PyPI as the package's landing page, is written
  for end users, and carries no platform internals; it has nothing to link.
- Shrinking the docs for its own sake. Line count is a symptom. A section that
  is long because it carries real operational detail stays long.
- Changing the vendored OpenSpec skills under `.claude/`, `.agents/`,
  `.codex/`, `.gemini/`, `.opencode/`. They are five copies of an upstream
  artifact and are overwritten on the next version bump.

## Decisions

### D1: Link to both the spec and the archived design document

A prose entry links to `openspec/specs/<capability>/spec.md` for the contract
and, where the reasoning is what a reader needs, to the originating
`openspec/changes/archive/<date>-<slug>/design.md`.

*Alternative considered:* link only to `openspec/specs/**`, the narrower rule.
Rejected on the evidence in Context: rationale largely is not in the specs. A
specs-only rule leaves every "why" paragraph with no home, and it will stay in
the README — which is most of the duplication by volume.

### D2: A terse entry survives; the section does not become a bare link

Each capability keeps two to four sentences: what it is, who owns it, and any
one fact that changes how a reader navigates (for example "nothing consumes
these keys yet"). Then the links.

*Alternative considered:* delete the sections and put a single capability index
table at the top of each README. Rejected — 114 capability names are not
self-describing, and a reader scanning `api/README.md` for "how do vars reach a
pod" would have to open several spec files to find out which one to read. The
terse entry is the index; it earns its place by making the link decidable.

### D3: Relative markdown links, resolved from the file's own directory

`[ssh-key-api](../openspec/specs/ssh-key-api/spec.md)` from `api/README.md`;
`[…](openspec/specs/…)` from the root `README.md` and `AGENTS.md`. These
resolve in the GitHub web UI, in IDE previews, and in a local clone.

*Alternative considered:* absolute `https://github.com/...` URLs. Rejected —
they break on a fork, pin a branch, and cannot be followed offline.

### D4: Link to the file, name the requirement in the link text

Prefer `[ssh-key-api § A fingerprint survives being placed in a URL](../openspec/specs/ssh-key-api/spec.md)`
over a `#anchor`. Heading anchors into specs break silently whenever a
requirement is reworded, which happens on every delta sync; a file-level link
plus a named requirement degrades to "right file, find the heading" instead of
"page jumps to the top and the reader does not notice".

### D5: Link rot is guarded by a process rule, not a checker

No link-checking script or CI job lands. `AGENTS.md` § Documentation Layering
gains one rule instead: renaming or merging a capability directory updates the
prose links pointing at it in the same change. The exposure this change
introduces — roughly a hundred new links into `openspec/` — is real but small
on the evidence: the repo's 555 tracked markdown files carry 27 relative links
today, the current tree does not pass a whole-tree check (one genuinely broken
link in an out-of-scope file, the rest prose examples and regex-shaped false
positives), and no capability directory has ever been renamed in this repo's
589-commit history. Rot is a rare, bounded failure, detectable on follow; the
staleness it replaces was ambient and silent.

*Alternative considered:* `scripts/check-doc-links.py` over every tracked
`*.md`, called from a new `docs-links` CI job. Rejected on the evidence above:
its "must pass on the current tree" gate fails before the change starts, and
making it pass means fixing unrelated files or teaching the parser to skip
fenced code, inline code and regex-shaped prose. A version scoped to the five
in-scope documents, or to links targeting `openspec/` only, passes today — but
it maintains a script and a CI job to police a failure this repo has never
seen, where the process rule directs the same behavior at less cost. A
third-party action (`lycheeverse/lychee-action`) was also weighed: validating
external URLs is what makes it flaky (rate limits, transient 5xx on sites this
repo does not own), and it would gate merges on third-party uptime.

### D6: Orphan rationale is relocated before its README section is cut

The audit sorts each paragraph into one of three buckets:

1. **Duplicate** — the spec or design document says it. Delete, link.
2. **Operational** — how to run, test, debug or operate. Keep in the README;
   it was never spec material.
3. **Orphan** — a decision or a measurement that exists *only* in the README.
   If normative, it moves into the governing spec as an errata edit under an
   existing requirement. If it is reasoning about a change already archived,
   it moves into that change's `design.md` with a dated note saying it was
   recovered from the README.

Bucket 3 is why this is an audit and not a deletion. Editing an archived
`design.md` is unusual — archives are a record — so the note is required and
the alternative (leave the paragraph in the README, marked) is acceptable
where the edit would misrepresent what was decided at the time.

### D7: Order — `AGENTS.md` first, then by counter-example size

`AGENTS.md` Architecture Notes (80 lines), then `api/README.md` (~1,280 lines
in scope), `cli/DEVELOPMENT.md` (~820), `ui/README.md` (~240), `tf/README.md`
(~22). `AGENTS.md` leads because it is the file every agent and contributor
reads first: while its own Architecture Notes restate specs and point at
`api/README.md` rather than at `openspec/`, the instruction and the example
contradict each other.

## Risks / Trade-offs

- **Link rot from a renamed capability directory** → D5's process rule: the
  rename updates the prose links in the same change. Unobserved in this repo's
  history (zero renames under `openspec/specs/` in 589 commits); accepted as
  process-guarded rather than tool-enforced.
- **Over-deletion loses information** → D6's three-bucket audit, per-section
  review, one document per commit. `git log -p` retains anything cut in error.
- **An extra hop for the reader.** Someone who wants the endpoint table now
  opens a spec. Accepted: the current alternative is an endpoint table that may
  silently disagree with the spec, which is worse than a click.
- **Onboarding narrative is not spec-shaped.** Specs are requirements and
  scenarios; they read poorly as a first introduction → `api/README.md`
  § Codebase Map, § Request Flow and § First 30 Minutes for a New Agent are
  bucket 2 and stay, as the narrative entry point that hands off to the links.
- **The rule can overshoot.** A future contributor may read "do not restate" as
  "do not explain", and strip operational detail that no spec covers →
  § Documentation Layering states positively what prose owns, and D6 bucket 2
  names it again here.
- **Partial landing.** If the change stops after two documents, the tree is
  inconsistent → D7's order is by leverage, so the early stops are the valuable
  ones, and each document is independently coherent.

## Migration Plan

Documentation only; nothing deploys and there is no runtime rollback concern.
One commit per document, in D7's order, each self-contained. Reverting any
single commit restores that document's prose from history without affecting the
others.

## Open Questions

- Whether the root `README.md` (34 lines) and `k8s/README.md` (164 lines,
  mostly VM and cluster operations — bucket 2) need any entry at all. Both look
  out of scope on inspection; confirm during the audit. Neither answer changes
  the approach or the task breakdown.

  **Resolved (task 6.1):** both are out of scope; no entry added. The root
  `README.md` is pure orientation (repo layout, devcontainer, deployment, the
  `k8s/` pointer) — every line is bucket 2 and it already links the sub-READMEs.
  `k8s/README.md` is VM management, cluster access, backups, and a Helm
  onboarding walkthrough (a Nextcloud example with a sample schema); it is
  operational and restates no capability, so it stays as-is.
