## Why

Everything under a `custom` deployment's SSH access now works, and no `freepod` command
uses it. A developer can already open a shell in their application container, attach a
debugger and forward a port to their database — provided they know the edge's hostname and
port, that their username is the deployment name, which of their private keys is
registered, and the in-cluster address of their database pooler spelled exactly as the
forward allowlist spells it. That is a lot to hold, and all of it is knowable from the
platform.

This change is the last component of the SSH line of work: the client that turns those
facts into three commands.

Two things have to be fixed on the way, both discovered while reading the shipped code.

**The connection-details endpoint is broken for every migrated deployment.** It decides
whether a deployment has SSH access by looking for a Service labelled
`caelus.dev/component=sftp`, and the chart now labels them `component=ssh`. On the dev
cluster, five deployments — including the `custom` one this profile exists for — return
404 from that endpoint today, so the web UI's access panel has disappeared for them. SSH
itself is unaffected, because the edge resolves from the database rather than from labels.

**The edge's host key is not published anywhere.** Without it a client cannot verify what
it is connecting to on first use, and the alternative is trusting whatever answers. The
key already exists and is stable; it is simply never handed out.

## What Changes

- **`freepod shell`** — an interactive session in the deployment's application container.
- **`freepod db proxy`** — a local port forwarded to the deployment's database, printing
  the connection URL and holding the tunnel open in the foreground.
- **`freepod db shell`** — an interactive database session, run server-side so no local
  PostgreSQL client is needed and no client-version mismatch is possible.
- **Key selection becomes automatic**: the client offers exactly the registered key this
  machine holds, recovering the association by fingerprint when its local record is
  missing.
- **Failures are diagnosed before connecting**, from what the platform reports rather than
  from the SSH refusal — which is deliberately uniform and says only "no".
- **The edge's host public key is published** on a dedicated public endpoint, and the
  client pins it, so a connection is verified rather than trusted on sight.
- **The availability check is repaired** to match the label the charts now render.

The client shells out to the system `ssh`. It does not implement the protocol.

## Capabilities

### New Capabilities

- `cli-ssh-access`: the three commands, how the client chooses a key and an address, how it
  diagnoses a failure it cannot see the cause of, and its output discipline.
- `ssh-edge-host-key`: the dedicated public endpoint that publishes the edge's address and
  host key, so a client can verify the edge instead of trusting it on first use.

### Modified Capabilities

- `sftp-credentials-api`: availability is determined by the label the charts actually render.

## Impact

**API**

- One selector corrected. This alone restores the access panel for every migrated
  deployment and is worth shipping ahead of the rest.
- The edge's host public key becomes platform configuration and is published on a dedicated
  public endpoint (`GET /api/ssh`) alongside the edge's host and port.

**Client**

- Three commands, over the existing key record and API client. `ssh` becomes a runtime
  requirement, documented as such.
- A client-managed `known_hosts`, written beside the token cache and keyed by environment
  like everything else there.

**Not affected**

- The edge, the resolver, the sidecar image, the charts, and the account key store. This
  change consumes them; it changes none of them.
- Authentication and authorization, which are settled at the edge and are not something a
  client can influence.

**Depends on**

- The `dev` profile, the resolver, and the account key store — all shipped.
