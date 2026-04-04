## Why

Users can currently enter nested hostname prefixes (e.g. `foo.bar`) in the free wildcard domain mode, resulting in multi-level subdomains like `foo.bar.dev.deprutser.be`. Wildcard TLS certificates only cover a single level (`*.dev.deprutser.be`), so these nested hostnames would fail TLS verification. The system should enforce single-level prefixes for free wildcard domains while leaving custom domain input unrestricted.

## What Changes

- **Frontend**: The `HostnameField` wildcard-mode prefix input rejects dots, preventing users from entering nested hostnames like `foo.bar`.
- **Backend**: The hostname validation service gains a new check that rejects FQDNs with multi-level prefixes under configured wildcard domains (e.g. `foo.bar.dev.deprutser.be` is rejected, but `foo.dev.deprutser.be` is accepted).
- Custom domain mode remains unchanged — any FQDN that resolves to the Caelus LB IPs is valid regardless of depth.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `hostname-validation`: Add a new validation check that rejects multi-level prefixes under wildcard domains. New reason `"nested_subdomain"` (or reuse `"invalid"`).
- `hostname-field-ui`: In wildcard mode, the prefix input must reject dots to prevent multi-level subdomain entry.

## Impact

- **Backend**: `api/app/services/hostnames.py` — new validation step in the ordered check chain.
- **Frontend**: `ui/src/components/HostnameField.tsx` — input restriction on the prefix field in wildcard mode.
- **API contract**: The hostname check endpoint may return a new reason value if a new reason is introduced, which the frontend tooltip mapping would need to handle.
- **Existing deployments**: No migration needed — this only affects new hostname submissions.
