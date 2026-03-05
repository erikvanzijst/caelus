## Context

The deployment `domainname` contract is inconsistent across interfaces. REST and CLI currently allow `domainname` in write paths, while the backend still needs a persisted `domainname` value for read responses. The UI Dashboard also still has a dedicated `Domain name` input. This change aligns write contracts across API/CLI/UI and moves `domainname` persistence derivation into service logic based on template schema + `user_values_json`.

## Goals / Non-Goals

**Goals:**
- Remove `domainname` from API and CLI write contracts for deployment create and update operations.
- Ensure payloads/inputs containing `domainname` fail validation with stable client-facing errors.
- Preserve `domainname` in deployment read responses.
- Derive `DeploymentORM.domainname` during create and update from `user_values_json` using recursive template schema field discovery by title.
- Remove Dashboard's dedicated `Domain name` TextField and keep request serialization free of `domainname`.
- Keep API and CLI behavior in lockstep through updated unit tests.

**Non-Goals:**
- Redesigning deployment UI beyond removing the dedicated `Domain name` input.
- Introducing a replacement custom-domain flow in this change.
- Changing deployment read response fields (other than explicitly keeping current `domainname` behavior).

## Decisions

1. Enforce `domainname` removal at API and CLI write-input boundaries (`POST` and `PUT`).
Rationale: early validation prevents contract drift and keeps service methods focused on business logic.
Alternative considered: silently ignoring `domainname`; rejected because it hides client bugs.

2. Keep `domainname` in `GET /deployment` response without exposing it in write payloads.
Rationale: existing consumers may rely on read-time visibility, and persistence is still required.
Alternative considered: removing `domainname` from read responses now; rejected due to unnecessary compatibility risk.

3. Derive persisted `DeploymentORM.domainname` in create/update services from template schema title matching.
Rationale: source-of-truth for domain data should be `user_values_json` keyed by template definition, not a separate top-level field.
Alternative considered: deriving by hard-coded property name `domainname`; rejected because template property keys may vary while title is stable.

4. Recursively search the entire schema document, match `title` to `domainname` case-insensitively, and use the first match's corresponding `user_values_json` value.
Rationale: template schemas may nest fields and use title casing variations; deterministic first-match behavior keeps outcomes predictable.
Alternative considered: error on multiple matching fields; rejected to avoid unnecessary failures in existing templates.

5. Update API and CLI unit tests for validation plus derivation behavior.
Rationale: this change is contract and behavior sensitive; tests must pin both rejection and derived persistence behavior.
Alternative considered: rely on integration tests only; rejected because unit tests provide faster and clearer regression signals.

## Risks / Trade-offs

- [Risk] External clients may break if still sending `domainname`.
  Mitigation: treat as explicit breaking contract change and document in proposal/spec/tasks.

- [Risk] Backend model config might currently allow extra fields silently.
  Mitigation: ensure create/update request models forbid extras or explicitly validate/block `domainname`.

- [Risk] Template schema traversal may not find a `title: domainname` field or may find multiple.
  Mitigation: use first-match rule and persist `null` when no match exists; cover both in unit tests.

- [Risk] CLI and API can diverge if only one surface is updated.
  Mitigation: require paired CLI/API test updates and parity checks in tasks.
