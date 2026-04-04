## Context

Caelus uses wildcard TLS certificates (e.g. `*.dev.deprutser.be`) for free-domain deployments. These certificates only cover a single subdomain level. The current system allows users to type multi-level prefixes like `foo.bar` in the wildcard prefix field, producing `foo.bar.dev.deprutser.be` — a hostname the wildcard cert cannot cover.

The validation pipeline in `api/app/services/hostnames.py` runs checks in order: format, reserved, availability, DNS resolution. None of these currently reject a well-formed multi-level subdomain under a wildcard domain.

The frontend `HostnameField` component has a dedicated prefix `<TextField>` in wildcard mode but does not restrict dots in the input.

## Goals / Non-Goals

**Goals:**
- Prevent creation of multi-level subdomains under wildcard domains, both in the UI and at the API level.
- Maintain the existing validation order and short-circuit behavior.

**Non-Goals:**
- Changing custom domain validation — any valid FQDN pointing to the LB IPs remains acceptable.
- Retroactively fixing existing deployments that may have nested subdomains.
- Changing the wildcard TLS certificate setup itself.

## Decisions

### Decision 1: Frontend — strip dots from prefix input

**Choice:** Filter out dot characters from the prefix `<TextField>` onChange handler in wildcard mode.

**Rationale:** This is the simplest UX — dots silently don't appear, making it impossible to construct nested prefixes. An alternative would be showing a validation error after the user types a dot, but that's unnecessarily noisy for a character that has no valid use in this field. The backend check serves as the authoritative guard.

**Alternative considered:** Regex validation with error message — rejected because it adds UI complexity for a constraint that's simpler to enforce at input level.

### Decision 2: Backend — new `_check_wildcard_depth` step after format check

**Choice:** Add a new validation function `_check_wildcard_depth(fqdn, settings)` that checks if the FQDN falls under a configured wildcard domain and, if so, verifies the prefix is exactly one label (no dots).

**Rationale:** This must be a server-side check regardless of frontend enforcement, since the API can be called directly. Placing it after `_check_format` and before `_check_reserved` is the natural position — the hostname must be well-formed first, but the wildcard depth check is a structural constraint that should run before more expensive checks (DB lookup, DNS).

The updated validation order becomes: format → wildcard depth → reserved → availability → DNS resolution.

### Decision 3: Introduce a dedicated `"nested_subdomain"` reason

**Choice:** The `_check_wildcard_depth` function raises `HostnameException("nested_subdomain")`, and the frontend maps this to the tooltip message "Only a single subdomain level is allowed".

**Rationale:** Reusing `"invalid"` was considered but rejected — a hostname like `foo.bar.dev.deprutser.be` is technically well-formed per RFC 1123, so "Invalid hostname format" would be misleading. A distinct reason gives the user a clear explanation of *why* their hostname was rejected, especially if they bypass the frontend dot-stripping (e.g. direct API call).

**Alternative considered:** Reuse `"invalid"` reason — rejected because the error message doesn't accurately describe the problem.

## Risks / Trade-offs

- **[Risk] Silent dot stripping may confuse users who paste hostnames with dots** → Mitigation: The wildcard mode prefix field is clearly labeled and positioned next to a `.domain` suffix, making it visually obvious this is a single label input. Users who need dots belong in custom domain mode.
- **[Risk] Existing deployments with nested subdomains** → Mitigation: Out of scope — this change only affects new hostname submissions. Existing deployments continue to work.
