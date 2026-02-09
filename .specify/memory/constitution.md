# Database CRUD Application Constitution

## Core Principles

### I. Data Integrity
Validate all inputs, enforce schema constraints, and use transactions for multi-step writes.

### II. Least Privilege
Database access uses scoped roles; API only exposes required CRUD operations.

### III. Clear Errors
Return stable, user-friendly error codes/messages; no leaking of secrets or raw SQL.

### IV. Minimal Surface Area
- Use an ORM and model entity classes.
- Keep endpoints and schema lean; avoid unused fields and over-generalization.
- Ensure a properly RESTful API.

### V. Observability
Log CRUD operations with request IDs and latency; store audit fields on writes.

## Security Requirements

- Validate input against entity schemas/objects.
- Use ORM to prevent injection.
- Store secrets outside code; rotate credentials when compromised.

## Development Workflow

- Every change includes tests for happy path and basic validation errors.
- Review required for schema changes; migrations must be reversible.

## Governance

This constitution supersedes other project practices. Amendments require a documented rationale and impact note.

**Version**: 1.0.0 | **Ratified**: 2026-02-09 | **Last Amended**: 2026-02-09
