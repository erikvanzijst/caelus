---
name: code-reviewer
description: Expert code review workflow for this monorepo (FastAPI API + Typer CLI + React UI). Use when reviewing diffs, PRs, or commits and prioritize correctness, regressions, API/CLI parity, migration safety, and test coverage gaps.
---

# Code Reviewer

## Overview

Use this skill to perform high-signal reviews of repository changes with findings-first output.
Default to behavioral and operational risk, not style comments.

## When To Use

Use this skill when the user asks to:
- review a PR, commit range, or diff
- check for regressions before merge
- assess risk in backend/frontend changes
- verify API and CLI feature parity

Do not use this skill for feature implementation unless the user explicitly combines review and implementation.

## Inputs To Gather

Collect enough context before issuing findings:
- changed files and diff (`git diff`, `git show`, or explicit patch)
- related tests added/changed
- migration files under `api/alembic/versions/` when models change
- touched services in `api/app/services/` and their API/CLI callers

If context is incomplete, state assumptions explicitly.

## Review Workflow

1. Scope changes
- Identify behavior changes, not just file changes.
- Mark user-facing, data-model, and infra/provisioning impacts.

2. Run targeted checks
- Prefer narrow commands first (for speed): lint/tests on touched areas.
- If unavailable, perform static review and call out what was not executed.

3. Find defects and risks
- Prioritize: correctness, security, data integrity, backward compatibility, reliability, and operability.
- Check edge cases and failure paths, not only happy path.
- IMPORTANT: always prefer simple solutions over complex ones. DRYness is key. Do not create unnecessary or premature abstractions.

4. Verify monorepo invariants
- API and CLI remain in lockstep for the same capability.
- DB logic stays in `api/app/services/` (no duplication in route/CLI handlers).
- Schema changes include migrations and compatibility notes.

5. Evaluate tests
- Ensure tests cover new behavior and regressions.
- Flag missing tests for failure modes and validation boundaries.

## Output Format

Always return sections in this order:

1. Findings
- Sort by severity: Critical, High, Medium, Low.
- For each finding include:
  - title
  - severity
  - evidence with file + line reference
  - impact (what can break and for whom)
  - concrete fix recommendation

2. Open Questions / Assumptions
- List unresolved items that affect confidence.

3. Change Summary
- 2-5 bullets max, only after findings.

4. Residual Risk & Test Gaps
- Explicitly state what was not validated.

If no issues are found, state: "No findings." Then provide residual risks and test gaps.

## Severity Guidance

- Critical: production outage, data loss/corruption, auth bypass, severe security flaw.
- High: likely functional regression, broken contract, migration hazard, significant reliability issue.
- Medium: edge-case bug, incomplete validation, degraded observability or maintainability with real risk.
- Low: minor issue with limited impact.

## Monorepo-Specific Checks

Use `references/monorepo-review-checklist.md` for detailed checks by area:
- API/FastAPI + SQLModel
- CLI/Typer parity
- DB + Alembic migrations
- Provisioning boundary (`api/app/provisioner.py`)
- UI/React + TypeScript + MUI integration risks

