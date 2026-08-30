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
  rule exists; this change makes the tree match it.
- **The docs in scope are uncontested.** Neither in-flight branch
  (`erik/cli-rust`, `erik/sftp-reachability`) touches `AGENTS.md`,
  `api/README.md`, `ui/README.md`, `cli/DEVELOPMENT.md` or `tf/README.md`
  against its merge base, so this rewrite races nothing.
- **CI has no markdown job today.** `.github/workflows/ci.yml` runs UI tests,
  catalog lint, the CLI gate, the ssh-sidecar harness and API tests.

## Goals / Non-Goals

**Goals:**

- Every capability-restating section in the docs in scope becomes a terse
  entry plus links, per `AGENTS.md` § Documentation Layering.
- No information is lost: content that exists only in a README is relocated,
  not deleted.
- Links are mechanically verified, so this does not trade a staleness problem
  for a rot problem.
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

### D5: A repo-local link checker, not a third-party action

Add `scripts/check-doc-links.py` — resolve every relative markdown link in the
repo's tracked `*.md`, fail on a target that does not exist — and call it from
a new `docs-links` job in `.github/workflows/ci.yml`. It needs no network and
no dependency beyond the Python already installed for `catalog-lint`.

*Alternative considered:* `lycheeverse/lychee-action`. More capable — it also
validates external URLs — but that capability is what makes it flaky (rate
limits, transient 5xx on unrelated third-party sites) and it would gate merges
on the uptime of sites this repo does not own. The risk this change actually
introduces is *internal* link rot from a renamed capability directory, which
the local script catches exactly.

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

- **Link rot from a renamed capability directory** → D5's CI job. This is the
  single largest new failure mode and the reason the checker is in scope rather
  than deferred.
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
One commit per document, in D7's order, each self-contained. `scripts/
check-doc-links.py` and its CI job land in the first commit so every subsequent
commit is verified as it arrives. Reverting any single commit restores that
document's prose from history without affecting the others.

## Open Questions

- Whether the root `README.md` (34 lines) and `k8s/README.md` (164 lines,
  mostly VM and cluster operations — bucket 2) need any entry at all. Both look
  out of scope on inspection; confirm during the audit. Neither answer changes
  the approach or the task breakdown.
