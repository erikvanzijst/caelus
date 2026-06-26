## Context

Custom domain validation today works by resolving a user-supplied FQDN to IP addresses via `socket.getaddrinfo()` and checking them against `settings.lb_ips`. This couples users' DNS records to the platform's load balancer IPs. Whenever the platform migrates IPs, every custom-domain deployment breaks until the user updates their A record.

CNAME delegation solves this: the user points their domain at `freepod.eu` once. The platform owns `freepod.eu`'s A records and can change them freely without touching user DNS.

The stdlib `socket.getaddrinfo()` follows CNAME chains transparently and returns only IPs — it cannot be used to check whether a CNAME record exists or what it points to. Explicit CNAME querying requires a DNS library that speaks the wire protocol directly.

## Goals / Non-Goals

**Goals:**
- Replace IP-based validation with CNAME record validation
- Remove `lb_ips` from config and Terraform entirely
- Guide users in the UI on exactly what DNS record to create

**Non-Goals:**
- Following CNAME chains (one hop only)
- Accepting CNAMEs to subdomains of `freepod.eu` (e.g. `ingress.freepod.eu`)
- Backwards compatibility for existing A-record users
- A grace period or dual-mode validation

## Decisions

### Use `dnspython` for CNAME queries

`socket.getaddrinfo()` resolves FQDNs to addresses and cannot distinguish A records from CNAME records. `dns.resolver.resolve(fqdn, 'CNAME')` queries the CNAME record type directly, raises `dns.resolver.NoAnswer` when no CNAME exists (e.g. A-record-only domains), and `dns.resolver.NXDOMAIN` when the domain doesn't exist.

**Alternatives considered:**
- `subprocess` + `dig`: fragile, not portable across container images.
- A raw UDP socket implementation: significant complexity for no benefit.

### Exact match on `freepod.eu`, no chain following

The CNAME target (trailing dot stripped) must equal `settings.domain` exactly. No subdomains, no recursion. This keeps validation simple, unambiguous, and easy to explain to users.

**Alternatives considered:**
- Allow subdomains (e.g. `ingress.freepod.eu`): technically works but opens a confusing surface area with no current use case.
- Follow chains: enables CDN proxy setups but massively complicates validation and error messaging.

### Use `CAELUS_DOMAIN` / `settings.domain` instead of a dedicated `lb_domain` field

Rather than introducing a new `lb_domain` config value, we reuse the platform's canonical domain via `CAELUS_DOMAIN = var.domain` in the Terraform configmap. `var.domain` already carries `"freepod.eu"` in prod and `"dev.freepod.eu"` in dev, so no new Terraform variable is needed. The empty-string default of `domain` preserves the skip-if-unconfigured behaviour for environments that don't set `CAELUS_DOMAIN`. Removing `lb_ips` from config and Terraform eliminates the now-irrelevant IP list.

### Query authoritative nameservers directly to defeat negative caching

The validation runs while the user waits in the UI, and the common failure flow is: user enters their domain, sees `not_resolving`, *then* creates the CNAME. A normal recursive lookup poisons the picture here — per RFC 2308 the recursive resolver caches the negative (NXDOMAIN/NODATA) answer for the zone's SOA negative TTL (often 5–60 min), so the freshly created CNAME isn't picked up until that expires.

dnspython itself never caches (no `resolver.cache` is set), and the user's authoritative nameservers never cache either — only the recursive resolver in the middle does. So `_check_cname` resolves the zone's authoritative nameservers (`zone_for_name` → `NS` → their A/AAAA records) and queries *them* directly via a `dns.resolver.Resolver(configure=False)` with explicit `nameservers`. This sidesteps the recursive negative cache entirely; the only remaining latency floor is the user's DNS provider publishing the record to its own authoritative servers (typically seconds).

If the authoritative servers can't be determined or reached (e.g. cluster egress to port 53 is restricted), the check falls back to the default system resolver so validation still functions in a degraded (cache-subject) mode rather than failing outright. A short resolver timeout/lifetime (3s/5s) keeps the UI responsive.

**Operational note:** this requires outbound DNS (UDP/TCP 53) to arbitrary internet hosts. Egress NetworkPolicies must allow it for the aggressive path; otherwise the fallback degrades to recursive (cached) resolution.

**Alternatives considered:**
- Attach a TTL-0 cache / public resolver: doesn't help — the negative TTL is set by the zone's SOA and honored by whichever recursive resolver we use.
- Flush the recursive cache: not possible for shared/managed resolvers (CoreDNS, public DNS).

### Single error reason: `not_resolving`

Both "no CNAME record" and "CNAME points to wrong target" surface as `not_resolving`. The distinction isn't actionable from the user's perspective — either way they need to create the correct CNAME. The UI helper text explains what to do.

## Risks / Trade-offs

- **Existing A-record users are immediately broken on edit** → Accepted. Users are prompted to create a CNAME. The deployment continues serving until they next edit it; only re-validation (on deploy or edit) fails.
- **`dnspython` is a new runtime dependency** → Minimal risk; `dnspython` is stable, widely used, and small.
- **DNS timeout causes a hard validation failure** → Accepted. Flaky DNS is the user's problem at their registrar, not a platform error to swallow.
- **`domain` is now always validated** → Dev environments that create custom-domain deployments will need a real CNAME or a mocked DNS resolver in tests.

## Migration Plan

1. Deploy backend with `domain` config set, `lb_ips` removed.
2. Existing deployments are unaffected (ingress routing doesn't care about DNS record type).
3. Users with A-record custom domains will see a `not_resolving` error the next time they edit their deployment; the UI guides them to create a CNAME.
4. No rollback complication: reverting re-adds `lb_ips` and the old check; no data is mutated.
