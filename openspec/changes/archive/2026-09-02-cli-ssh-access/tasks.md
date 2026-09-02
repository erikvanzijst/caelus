## 1. Publish the edge host key

- [x] 1.1 Add the edge's **host** public key as platform configuration, per environment,
      sourced from the same Terraform-held key the edge presents. Name it so it cannot be
      confused with the existing upstream key, which has the same shape and an entirely
      different meaning (design.md § *Publishing the host key widens the response*). Verify
      the configured value equals what the edge actually presents.
- [x] 1.2 Publish it on a dedicated public endpoint (`GET /api/ssh`) alongside the edge's
      host and port, publicly readable. Verify a client receives it and that each
      environment reports its own.
- [x] 1.3 Add `GET /api/ssh` to the oauth2-proxy `skip_auth_routes` so it is reachable
      without a session in production — the API-level public read is inert at the edge
      until the route is listed there. Verify an unauthenticated request returns the key,
      not a login redirect.

## 2. Key selection and host verification in the client

- [x] 2.1 Resolve this machine's registered key for the target environment using the
      existing record in `cli/src/freepod/keys.py`, falling back to fingerprint recovery and
      recording what it finds. Verify the recorded path is used directly on the next
      invocation with no search.
- [x] 2.2 Offer exactly that key: `-o IdentitiesOnly=yes -i <path>`. Put the reason beside
      the flag in the code — the edge answers every offered key with a partial success, so
      a populated agent exhausts the authentication budget before the right key is reached.
      Verify with several keys loaded in an agent that exactly one is offered.
- [x] 2.3 Write and use a client-managed `known_hosts` beside the token cache, keyed by
      environment, populated from the published host key. Verify the user's own
      `known_hosts` is neither consulted as authority nor modified.
- [x] 2.4 Refuse a host key that does not match the published value, reporting the mismatch.
      Verify no prompt to accept it appears and nothing is recorded.
- [x] 2.5 Report a missing `ssh` executable as a named prerequisite rather than an unhandled
      error. Verify on a path with no `ssh`.

## 3. Pre-flight diagnosis

- [x] 3.1 Before connecting, check `account_has_ssh_key` and the deployment's state, and
      explain a predictable failure in those terms rather than attempting a connection that
      will be refused. Verify against an account with no key and against a deployment the
      platform does not admit connections for.
- [x] 3.2 When the checks pass and the edge still refuses, report the refusal and what was
      verified, and **assert no cause** (design.md § *The client states only what the
      platform told it*). Verify the message names no specific reason.
- [x] 3.3 Verify a deployment whose application container is failing is still connected to,
      not blocked by the pre-flight — that state is what these commands exist for.

## 4. `freepod db proxy`

- [x] 4.1 Forward a local port to the destination the database endpoint reports, passing the
      address through **verbatim**. Verified the requested destination is byte-identical to
      the reported one, and that it matches what the chart renders into the allowlist.
- [x] 4.2 Accept a local port and choose a free one when none is given, reporting which.
      Verified the conventional port being occupied does not fail the command, and that an
      explicitly requested unavailable port is reported specifically.
- [x] 4.3 Compose the connection URL for the **local** end, correctly percent-encoded.
      Verified with a password containing characters that require encoding — constructed in
      the test rather than relying on the current generator, which emits hexadecimal — and
      asserted the parsed URL yields the reported credential exactly.
- [x] 4.4 Print the URL on stdout and everything else on stderr, following `freepod log`'s
      discipline. Verified capturing stdout yields the URL alone.
- [x] 4.5 Hold the tunnel in the foreground and close it on interrupt, releasing the port.
      Verified the port is free afterwards.
- [x] 4.6 Explain a forward refused by the far end as a destination that was not permitted,
      distinguishably from an authentication failure. Verified by requesting a destination
      outside the allowlist.

## 5. `freepod shell` and `freepod db shell`

- [x] 5.1 `shell` opens an interactive session that lands in the **application container**.
      Verify by reading a file the application wrote and an environment variable it was
      started with. Note that interactive sessions over ssh to our sidecar _require_
      `-tt` passed to `ssh`, or else ForceCommand will not allocate a tty.
- [x] 5.2 `db shell` opens an interactive database session server-side. Verified with no
      local PostgreSQL client on PATH (the sidecar's psql answers), and interactively
      against the dbprobe deployment. The "app container stopped" case holds by
      construction — the sidecar is a separate container and its psql reaches the
      database via the pooler, not through the app container.
- [x] 5.3 Verify neither command prints a database credential, and that no command prints
      private key material in any mode including verbose.

## 6. Verification

- [x] 6.1 End to end on dev against a `custom` deployment, from a machine with no prior
      state: register a key, then shell, proxy and db shell each work with no arguments
      beyond the command.
- [x] 6.2 Verify the same three commands behave sensibly against a deployment on the `sftp`
      profile — which offers no shell and no forwarding — reporting the platform's refusal
      rather than appearing to hang or claiming a cause.
- [x] 6.3 Verify an unregistered key, a revoked key, and an account with no keys each
      produce the intended message.
- [x] 6.4 Verify a local client connects through the proxy and can query the deployment's
      own database.

## 7. Documentation

- [x] 7.1 Update `cli/README.md`: the three commands, and `ssh` as a runtime requirement.
- [x] 7.2 Update `cli/DEVELOPMENT.md`: the known-hosts store's location and per-environment
      keying, why exactly one identity is offered, and why the forward address is passed
      through unmodified.
- [x] 7.3 Update `api/README.md` for the published host key and the corrected availability
      check. Be very terse and just link to the appropriate spec design doc!
- [x] 7.4 Update `SKILL.md` with the new commands and their usage. Include the use of `pg_dump`
      as an example use-case.
- [x] 7.5 Document how to take a database dump over these commands, since it works today and
      is the most likely first thing a user reaches for.
