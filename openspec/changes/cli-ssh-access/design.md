## Context

See `proposal.md` § Why. `var/ssh_access.md` D10 is the client's design; the edge, the
resolver, the `dev` profile and the account key store are all shipped.

Six facts were read from the merged code, and they decide almost everything below.

1. **The client already has the key record it needs.** `cli/src/freepod/keys.py` provides
   the per-environment local record, fingerprint computation, and the generated key's
   path. Nothing about key handling has to be built.
2. **The API already reports what the client must diagnose from.** The access endpoint
   returns the edge host and port, the username, and `account_has_ssh_key`; the database
   endpoint returns the pooler host and port, the database, the role and the password.
3. **The forward destination is rendered from the same values the client reads.** The
   chart renders the allowlist as `caelus.database.host:port`, which is exactly what the
   database endpoint reports. Passing it through unchanged makes the two spellings one
   fact rather than two that must agree.
4. **Refusals are uniform by design.** The resolver keeps `unknown_username`,
   `deployment_not_reachable` and `key_not_registered` in the operator log and tells the
   client only "no". Any cause the client states from an SSH failure alone is a guess.
5. **The database endpoint returns no composed URL** — host, port, database, role and
   password as separate fields. The client composes its own, which it would have to
   anyway: the URL it prints addresses the *local* end of a tunnel, not the platform's.
6. **The edge's host key is nowhere in the API.** `sftp_platform_public_key` is the
   *upstream* key the sidecars trust, not the host key the edge presents to clients.

## Goals / Non-Goals

**Goals:**

- Three commands that need no argument in a project directory.
- A user never has to know the edge's address, their username, which key is registered, or
  how their database is spelled internally.
- Every predictable failure is explained before a connection is attempted.

**Non-Goals:**

- Implementing SSH. The client drives the system `ssh`.
- Changing anything about authentication or authorization, which are settled at the edge.
- `freepod db backup`. Running `pg_dump` server-side works over these commands today; a
  first-class command waits on the session-pooled path.
- Choosing a deployment other than the project's. A `--deployment` selector is additive
  and not needed to make the commands useful.

## Decisions

### The client states only what the platform told it

The edge refuses uniformly. That is a deliberate property — a refusal discloses nothing
about whether a username exists — and it means the obvious client behavior, turning
`Permission denied` into "your key is not registered", is a fabrication that will be wrong
whenever the real cause was something else.

So the client checks first, from facts the platform publishes: `account_has_ssh_key`
answers the most likely cause, and the deployment's status answers the second. Both are
already in responses the client fetches anyway. When those pass and the edge still refuses,
the client reports the refusal and what it verified, and stops there.

This is a correction to `var/ssh_access.md` D10, which assumed the client could name the
cause. It could not, and inventing one would be worse than the opaque failure it replaces:
a user told the wrong reason stops looking for the right one.

### Host key verification requires publishing the host key, so publish it

Pinning was specified before checking whether the value was obtainable. It is not: the
edge's host key lives in Terraform state and is never handed out.

The alternatives were trust-on-first-use into a client-managed store, or nothing. Both mean
the first connection from every machine accepts whatever answers, which is the one
connection worth attacking, and the platform knows the correct answer and simply is not
saying it. Publishing it is a settings value and a dedicated per-environment endpoint.

The endpoint is dedicated rather than a field on the SFTP credentials endpoint for two
reasons. The host key is a per-environment fact, and that endpoint's availability is gated
on a per-deployment cluster check that 404s for deployments whose chart the check does not
match, so a field there would make the key un-fetchable for exactly the deployments that
differ from the check's assumptions. And the value is public key material that confers
nothing, so the endpoint is public: self-registration already makes a session trivially
obtainable, and the edge presents the same key to every client during the handshake, so
gating it behind one protects nothing.

The client keeps its own known-hosts beside the token cache rather than touching the user's.
Two reasons: a mismatch must be the client's failure to report and not a modification of a
file the user curates, and a user who has their own entry for the edge should not have it
silently overridden.

### The forward destination is passed through, never reconstructed

`PermitOpen` matches the destination as the client wrote it and resolves it afterwards. So
a client that "helpfully" resolves, normalises, or shortens the address produces a refusal
that reads like an authorization failure.

Passing the platform's string through unchanged makes the chart's rendered allowlist and
the client's `-L` argument the same fact with two readers. Nothing has to be kept in
agreement because nothing is duplicated.

### One key, always, and the reason belongs in the code

`IdentitiesOnly` with a single identity is not hygiene here. The edge answers every offered
key with a partial success, so a client that offers several — which any user with a
populated agent does by default — burns the server's authentication budget and is refused
before reaching the right one.

That is surprising enough that the reason has to sit next to the flag, or someone will
remove it as redundant.

### The URL addresses the local end, and the client composes it

The database endpoint returns components, not a URL, and that turns out to be right: the
URL a user wants points at their own forwarded port, which the platform cannot know.

The client must encode it properly rather than concatenating. Today's generated passwords
are hexadecimal so concatenation happens to work, which is precisely why the requirement is
written against correctness instead — a generator change would otherwise produce a URL that
parses to a different password, intermittently, for some users only.

## Risks / Trade-offs

- **A mixed fleet during rollout** → deployments on the old chart still label their
  Services with the old marker, so a check written for only the new one breaks them
  instead. Whatever the implementation, it must be verified against both a migrated and an
  unmigrated deployment before shipping, and the dev cluster currently has both.
- **`ssh` becomes a runtime requirement** of a Python client. Accepted deliberately: the
  alternative is an SSH implementation to maintain, and protocol incompatibilities that
  are someone else's problem today become the platform's.
- **The client reports "refused, cause unknown"** in the residual case. Less satisfying
  than a specific message and more honest than a wrong one; the operator log has the cause,
  which is where the disclosure decision put it.
- **Publishing the host key on a public endpoint** widens its reach to anyone, not just
  callers entitled to a deployment's access details. It is public key material and confers
  nothing, and the edge presents it to every client during the handshake anyway, so the
  widening is real but harmless. The live risk is a reviewer mistaking it for the upstream
  key, which has the same shape and very different consequences. Naming them distinctly in
  the code is worth more than a comment.
- **A forwarded database port is reachable by anything on the developer's machine** for as
  long as the command runs. It binds the loopback interface only, and the tunnel ends when
  the command does.

## Migration Plan

1. **Publish the edge host key**: settings value, dedicated public endpoint.
2. **Key selection and host verification** in the client, over the existing key record.
3. **The three commands**, `db proxy` first, since the others reuse its connection
   assembly.

**Rollback**: removing the commands. Nothing persists beyond a client-managed known-hosts
file and the key record that already existed.

## Open Questions

- **Whether `freepod db shell` should pass through arguments** to the underlying database
  client. Additive, and easier to settle once it has been used.
- **Whether a `--deployment` selector is wanted** for acting on a deployment other than the
  project's. Additive; the project-scoped form is what makes the commands need no
  arguments at all.
