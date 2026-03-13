## Context

Caelus provisions user-owned webapp instances on Kubernetes. When deploying, users provide a hostname (FQDN) for their app's ingress. Today this is an unrestricted text field — any string is accepted, with only a DB uniqueness constraint catching duplicates at commit time. The field is named `domainname` throughout the stack, which is semantically incorrect.

Configuration is managed via scattered `os.environ.get()` calls with no centralized validation. The UI inlines all logic into large page components without extracting reusable pieces.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        HOSTNAME VALIDATION FLOW                            │
│                                                                            │
│  UI (HostnameField.tsx)                                                    │
│  ┌──────────────────────────────────────────┐                              │
│  │  Mode A: Caelus Wildcard                  │     GET /api/domains        │
│  │  ┌──────────┐.┌──────────────┐           │◀────(list of wildcard       │
│  │  │ myapp    │ │app.deprutser▼│ [✓]       │      domains)               │
│  │  └──────────┘ └──────────────┘           │                              │
│  │                                           │     GET /api/hostnames/     │
│  │  Mode B: Custom FQDN                     │        {fqdn}               │
│  │  ┌──────────────────────────────┐        │────▶(debounced)             │
│  │  │ myapp.example.com        [✗]│        │                              │
│  │  └──────────────────────────────┘        │◀──── { fqdn, reason }       │
│  └──────────────────────────────────────────┘                              │
│                                                                            │
│  API (hostnames.py router) — all sync                                      │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │  GET /api/hostnames/{fqdn}                                    │          │
│  │                                                               │          │
│  │  try:                                                         │          │
│  │      require_valid_hostname_for_deployment(session, fqdn)     │          │
│  │      → { "fqdn": "...", "reason": null }                      │          │
│  │  except HostnameException as e:                               │          │
│  │      → { "fqdn": "...", "reason": e.reason }                  │          │
│  │                                                               │          │
│  │  GET /api/domains  (no explicit auth required)                │          │
│  │      → ["app.deprutser.be", ...]                              │          │
│  └──────────────────────────────────────────────────────────────┘          │
│                                                                            │
│  Service (hostnames.py) — single public function                           │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │                                                               │          │
│  │  require_valid_hostname_for_deployment(session, fqdn)         │          │
│  │      raises HostnameException(reason=...)                     │          │
│  │                                                               │          │
│  │      internally:                                              │          │
│  │      1. format check  → reason="invalid"                      │          │
│  │      2. blacklist     → reason="reserved"                     │          │
│  │      3. availability  → reason="in_use"                       │          │
│  │      4. DNS resolve   → reason="not_resolving"                │          │
│  │                                                               │          │
│  └──────────────────────────────────────────────────────────────┘          │
│                                                                            │
│  Config (CaelusSettings) — all CAELUS_ prefixed                            │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │  CAELUS_DATABASE_URL          (str)                           │          │
│  │  CAELUS_STATIC_PATH           (Path)                          │          │
│  │  CAELUS_LOG_LEVEL             (str)                           │          │
│  │  CAELUS_LB_IPS               (list[str])   # v4 + v6         │          │
│  │  CAELUS_WILDCARD_DOMAINS      (list[str])                     │          │
│  │  CAELUS_RESERVED_HOSTNAMES    (list[str])                     │          │
│  └──────────────────────────────────────────────────────────────┘          │
│                                                                            │
│  Deployment Service (deployments.py)                                       │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │  create_deployment():                                         │          │
│  │      1. validate user_values_json against schema              │          │
│  │      2. hostname = _derive_hostname(...)                      │          │
│  │      3. require_valid_hostname_for_deployment(session, fqdn)  │          │
│  │      4. flush to DB (unique index = race safety net)          │          │
│  │      5. enqueue reconcile job                                 │          │
│  │      6. commit                                                │          │
│  │                                                               │          │
│  │  update_deployment():                                         │          │
│  │      (same hostname validation before flush)                  │          │
│  └──────────────────────────────────────────────────────────────┘          │
└────────────────────────────────────────────────────────────────────────────┘
```

## Goals / Non-Goals

**Goals:**
- Validate hostnames at both API check-time and deployment create/update-time using identical logic.
- Provide real-time hostname validation feedback in the UI during form entry.
- Rename `domainname` to `hostname` across the entire stack as a clean break.
- Centralize configuration via Pydantic Settings with `CAELUS_` prefix.
- Support both "bring your own domain" and Caelus-provided wildcard domains in the UI.

**Non-Goals:**
- Admin UI for managing reserved hostnames, LB IPs, or wildcard domains (deferred — static config via env vars for now).
- Async database layer (DB access remains synchronous; the entire hostname flow is sync).
- Backward compatibility for the `domainname` field name or `DATABASE_URL`/`STATIC_PATH` env var names.
- Short-circuiting DNS checks for hostnames under known wildcard domains.
- Communicating "pending deletion" granularity — a hostname in `deleting` status reports as `in_use`.

## Decisions

### 1. All-synchronous implementation

The hostname check endpoint, validation service, and DNS resolution are fully synchronous. FastAPI dispatches `def` (non-async) endpoints to a threadpool, which handles concurrent requests safely.

**Why not async?** The database layer uses synchronous SQLModel sessions. Mixing `async def` endpoints with sync DB calls would block the event loop. Using sync throughout avoids this trap and keeps the code simple. DNS resolution via `socket.getaddrinfo()` is blocking but fast (typically <200ms) and runs in FastAPI's threadpool alongside the DB queries.

**Alternative considered:** Async endpoint with `aiodns` for DNS + `run_in_executor` for DB calls. Rejected due to added complexity for minimal benefit — the debounced UI calls are infrequent and threadpool concurrency is sufficient.

### 2. Single public service function

The hostname service exposes exactly one public function: `require_valid_hostname_for_deployment(session, fqdn)`. It either returns `None` (success) or raises `HostnameException(reason=...)`.

**Why not multiple granular functions?** Services are internal APIs and should be minimal. The caller (endpoint or deployment service) never needs partial results — it either needs "is this hostname OK?" or "why isn't it OK?" Both are answered by the single function + exception pattern. Internal check functions remain private.

### 3. Static configuration for blacklist, LB IPs, wildcard domains

All three are configured via `CAELUS_` environment variables parsed by Pydantic Settings. No database tables, no admin CRUD endpoints.

**Why?** These values change rarely. Env vars are simple, require no migration, and match the existing deployment model (Terraform sets env vars on the API container). Admin-configurable DB storage is planned as a future change.

### 4. DNS check skipped when lb_ips is empty

When `CAELUS_LB_IPS` is not set (empty list), the DNS resolution check is skipped entirely and the hostname passes that check. This supports local development without requiring fake DNS configuration.

### 5. FQDN as path parameter

`GET /api/hostnames/{fqdn}` uses the FQDN as a path segment. Dots are legal in a single path segment (they are not path separators), so `myapp.app.deprutser.be` is captured correctly by FastAPI without needing `{fqdn:path}`.

**Alternative considered:** Query parameter (`?fqdn=...`). Rejected in favor of RESTful resource-style paths — the hostname is the resource being described.

### 6. Clean break on rename

The `domainname` → `hostname` rename is applied everywhere with no backward compatibility. The schema title convention changes to `title: "hostname"`. Existing product templates in the database will be manually updated by the operator.

**Why no compat shim?** The system has few API consumers (the UI and CLI, both under our control). Supporting both names adds code complexity and testing burden for no real benefit.

### 7. Evaluation order: format → reserved → available → DNS

Checks run cheapest-first: pure string validation, then in-memory list lookup, then DB query, then network DNS call. Short-circuits on first failure, returning the most specific reason.

### 8. TOCTOU safety via DB constraint

The hostname availability check queries the DB before flush, but the partial unique index on `hostname` (where `status != 'deleted'`) is the definitive safety net. A race between the check and flush results in a standard `IntegrityException`, which is acceptable for this extremely rare case.

## Risks / Trade-offs

- **[Breaking API contract]** Renaming `domainname` → `hostname` breaks any external API consumers. → Mitigation: The only consumers are the UI and CLI, both updated in the same changeset.

- **[Breaking env var names]** Existing deployments using `DATABASE_URL` or `STATIC_PATH` will fail on startup. → Mitigation: Update Terraform configs and local `.env` files as part of the deployment. Pydantic Settings fails fast with clear error messages on missing required values.

- **[DNS resolution latency]** `socket.getaddrinfo()` can take 1-5 seconds for non-existent domains or slow resolvers. → Mitigation: The UI debounces at ~400ms and shows a spinner. The sync endpoint runs in FastAPI's threadpool so it doesn't block other requests. Server-side validation during create/update adds latency but this is a one-time cost per deployment.

- **[DNS resolver availability]** The API host's DNS resolver must be functional for hostname validation to work. → Mitigation: If DNS resolution fails entirely (socket error), the check fails with `not_resolving`. The deployment can still proceed through the CLI or direct API if needed, since the DB constraint is the true enforcement and the DNS check is an additional validation layer.

- **[Stale DNS cache]** System-level DNS caching may cause the check to see stale records. → Accepted trade-off: users can retry after TTL expires. No custom caching layer is added.
