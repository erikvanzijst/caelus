## Context

See `proposal.md` § Why. `var/relational_storage_v2.md` D5, D6, D8 and D12 describe the
credentials, their delivery path and the quota ladder this change reports on;
`var/ssh_access.md` D17 records why the connection details must come from an API rather
than out of the running pod.

Four existing facts shape the approach.

1. **Provisioning precedes the ready state.** `_ensure_database` runs inside
   `_reconcile_apply` before Helm and before the result that carries
   `DEPLOYMENT_STATUS_READY`, and it raises rather than swallowing, so a failed provision
   fails the reconcile. A settled deployment whose product opts in therefore has its
   database; the record's absence on such a deployment is not a state the endpoint has to
   report.
2. **The password is encrypted under the platform keyring**, and the API already holds it
   and refuses to start when its keyring cannot cover what is stored. Decryption on this
   path introduces no new key management.
3. **Usage is measured on a sweep, not on demand.** The record carries both `size_bytes`
   and `measured_at`, and the housekeeping worker updates them on a tick. Any figure this
   endpoint reports is as old as the last sweep.
4. **The pooler is a ClusterIP with no public endpoint**, and network policy makes it the
   only route to a tenant database. The address this endpoint returns is real and correct
   and cannot be reached from a laptop today.

## Goals / Non-Goals

**Goals:**

- An owner can see their own database credentials, from the platform, without a shell.
- A degraded database explains itself, rather than presenting as inexplicable write
  failures.
- The endpoint is the input a client needs later to open a forwarded connection, so the
  SSH work has nothing left to invent about where a tenant database lives.
- Exactly one connection URL exists in the product, on the one command that can make it
  work.

**Non-Goals:**

- Making the database reachable from outside the cluster. That is the forwarding work.
- Rotating credentials, or offering any write operation. This change only reads.
- Showing an address, or composing a connection URL, on any surface a person reads.
- Any `freepod` command that *connects*. `db status` reads and prints; `db proxy` and
  `db shell` stay with the forwarding work that makes them possible.
- Live usage measurement. Reporting the sweep's figure with its age is correct and cheap;
  measuring on request would put a tenant-triggered query on the shared cluster.

## Decisions

### The password goes to the owner and is withheld from administrators

The owner gets everything. An administrator gets the connection details without the
password, and is told it was withheld.

The alternative — mirroring the SFTP credentials endpoint, where an administrator reads
the password — is the more consistent choice and I think the wrong one. A database
password is read access to everything the tenant stores. Administrative reach exists to
operate the platform, and the platform already takes the stricter line elsewhere: a var
marked sensitive is write-only on read *for everyone, administrators included*. This
endpoint follows the vars precedent rather than the SFTP one.

Two things worth being honest about. First, an administrator with cluster access can read
the Secret directly, so this is not a security boundary against a determined operator; it
is about not making casual disclosure the default path, and about not producing an audit
trail in which reading a tenant's data credentials looks like ordinary use. Second, it
makes the two credential endpoints inconsistent, and the resolution is to tighten SFTP
later rather than loosen this one.

If that trade is judged wrong, it inverts by deleting one condition — but the withholding
must then be removed from the spec too, not left as an unimplemented requirement.

### Withheld is a stated fact, not a missing field

When the password is withheld the response says so, rather than omitting the field
silently. A client that cannot distinguish "withheld" from "absent" has to guess, and a UI
that guesses wrong shows an administrator either an error or an empty box where an
explanation belongs.

### No connection URL exists in this change, on any surface

An earlier draft of this design had the server compose a `postgresql://` URL beside the
components, on the reasoning that every client would otherwise have to percent-encode
identically and one that concatenated naively would work until a password contained a
character with meaning in a URL. Composing it once, correctly, would remove that class of
bug from every client.

The reasoning was sound and the premise was wrong: there are no such clients.

A URL is built around a host and a port, and the only ones this change knows are the
pooler's, which resolve from inside the cluster and nowhere else. A URL composed around
them is a string that looks exactly like the input to `psql` and is one for nobody
holding it. The two surfaces a person reads — the panel and `freepod db status` — would
each have been offering a copy affordance for a value whose only correct use is to be
thrown away.

The client that will genuinely need a URL is `freepod db proxy`, and **it cannot use a
server-composed one either**: its whole job is to replace the host and port with its own
local ones, so it assembles the URL itself whatever this endpoint returns. The
encode-correctly requirement is real, and it belongs there — at the one place a URL is
built, by the one component that has the address that makes it true. It moves to the
forwarding change with the command that needs it.

What is left is the honest shape: the endpoint returns components, `db proxy` returns the
single connection URL that exists in the product, and there is never a moment where two
`freepod db` commands print two different URLs and only one connects.

### The reader's surfaces show identity and credential, not address

The panel and `db status` show the database name, the role and the password. They do not
show the pooler host or port.

The seam is which half of the details survives forwarding. The **address** is exactly what
`db proxy` replaces; showing it now is showing the reader the one field that will be wrong
the moment it becomes usable. The **identity and credential** are unchanged by any tunnel:
a graphical client pointed at a future local port asks for a database name, a role and a
password, field by field, and those are what these surfaces hand over. So the trim is not
merely subtraction — it leaves precisely the part that stays correct.

The endpoint still returns the address, because `db proxy` must know what to forward to,
and because the withheld half is a presentation decision rather than a change to the
platform's read model. If forwarding ever makes a case for showing it, the field is there.

Removing the address does put an obligation on both surfaces: a role and a password with
no host raises "so where do I point this?" more sharply than a full set of details did.
Both specs therefore require the surface to say where the database can be reached from.
Omitting the wrong answer is not the same as giving the right one.

### Two absence states, because a database is never pending on a settled deployment

"This product has no database" and "no such deployment" are the two answers, and they are
the same two the SFTP credentials endpoint already gives. There is no third.

An earlier draft of this design argued for a distinct "not provisioned yet" state. That
was wrong, and the reconciler says so: `_ensure_database` runs inside `_reconcile_apply`
*before* Helm and before the result carrying `DEPLOYMENT_STATUS_READY`, and it raises
rather than swallowing, so a failed provision fails the reconcile. A deployment therefore
has its database whenever it is settled, and the interval in which the record is missing
is exactly an interval in which the deployment is not settled — which the deployment's own
status already describes.

Adding a database-specific pending state would duplicate that status in a second place,
where it could disagree with the first.

The transient window still has to be handled, and the deployment view already handles it:
`DeploymentCard` computes `settled` from the deployment's status and re-requests the SFTP
credentials when it flips. The database panel does the same thing, and needs nothing new.

Only the first answer is this capability's to implement. "No such deployment" is the
platform's existing readable-deployment rule — missing, not yours, and deleted answer
identically — and it arrives by calling `get_deployment_orm` rather than by re-deriving
anything. An administrator pairing a real deployment with the wrong owner in the path is
covered by the same rule; everyone else is refused by `require_self` before the service
runs.

Worth noting only so it is not rediscovered as a defect: a deleted deployment keeps its
`deployment_database` record and its database until the grace period elapses and the
housekeeping worker purges them, with the role set `NOLOGIN`. The record therefore
outlives the deployment's readability, and the readable-deployment rule is what makes that
irrelevant here. `get_sftp_credentials` open-codes the same check instead of calling the
helper; that is duplication to follow the helper on, not a pattern to copy.

### Usage is reported with its measurement time

The response reports the size, the allowance, and when the size was measured, and
distinguishes never-measured from measured-at-zero.

A figure without its age is read as current. On a fleet where the sweep is periodic, a
tenant who has just deleted a large table and sees no change would reasonably conclude the
platform is wrong. Reporting the timestamp costs one field and makes the number
interpretable.

### `freepod db status` ships now, and creates the group the forwarding change fills

An earlier draft deferred the whole client surface to the forwarding change, on the
grounds that a `freepod db` group has nothing to hold until `proxy` and `shell` exist.
That is backwards. `db status` needs nothing but this endpoint, and the developer asking
why their writes are failing is at a prompt, not in a browser — making them open the
dashboard to read a state the client could print is the same gap the endpoint was written
to close.

`var/ssh_access.md` D10 already reserves the group for `proxy` and `shell`. Creating it
here with its read-only member costs the forwarding change nothing: it inherits a group,
its help text, and the deployment-resolution rule, and adds two commands.

`status` is the right name once the address is gone: what the command answers is "what is
the state of my database", and the identity and credential are part of that answer rather
than a connection recipe competing with it. A second `db info` split along the seam
between the credential and the quota figures would make the reader choose which command
answers a question they have not decomposed.

### The client masks the password, and that is not a disclosure rule

The default output masks the password; `--show-password` prints it.

The endpoint returns the password to the owner and the client runs as the owner, so
nothing is being withheld from anyone. What masking buys is that the routine invocation —
how much room is left, why are writes failing — does not write a live database credential
into scrollback, a screen share, or a terminal-logging setup. Revealing it stays one flag
away.

An earlier draft also gave the command a `--url` flag, printing the composed URL as the
sole content of stdout for a shell to capture. It is worth recording why it went, because
it is the clearest case against the URL generally: a result form exists to be captured and
handed to a tool, and there is no tool on that machine the URL would work with. A flag
whose entire purpose is unachievable is a defect in the surface, not a convenience, and
`db proxy` is where that flag belongs — there the captured URL connects.

Its absence leaves the stream question with an easy answer: everything `db status` prints
is human-facing, the reachability statement included, so the command has no result that a
pipe must carry and the whole output can follow the client's ordinary discipline.

### Both surfaces say where the database can be reached from

The panel and the command each state that the database is reachable from the running
application and not from the reader's machine.

This is the same discipline as the SSH key panel shipping ahead of its consumer: the
honest description costs a sentence, and the alternative is a support request whose answer
is "that was never reachable from there". The wording must describe the present without
promising the forwarding feature, because that change may land in a different order than
planned.

Not showing the address does not retire this requirement — it sharpens it. A reader given
a role and a password and no host will ask where to point them, and a surface that answers
by omission is answering with a gap.

## Risks / Trade-offs

- **A panel or a command showing a password nobody can currently use** → invites
  connection attempts that cannot succeed. Mitigated first by showing no address to
  attempt one against, and then by the wording requirement, which is a spec requirement on
  both surfaces rather than a copy suggestion precisely because it is the thing most likely
  to be trimmed.
- **The forwarding change inherits an unwritten requirement** — that `db proxy` encode its
  composed URL correctly — which no spec in this change carries any more. Mitigated by
  recording it here and in the API spec's own reasoning; the residual risk is that the
  forwarding change is written without reading either, and the failure it would cause is
  intermittent and baffling: naive concatenation works until a password contains a
  character with meaning in a URL. The current generator emits hexadecimal, so nothing
  fails today and nothing would fail on the day the generator changes either — it would
  fail later, for some tenants.
- **The endpoint returns a live secret over the API for the first time** → the SFTP
  endpoint set this precedent, but a database password has a larger blast radius.
  Mitigated by owner-only disclosure, masking in the UI, and an explicit no-logging
  requirement covering the failure paths, which are the ones that leak.
- **Divergence from the SFTP endpoint's authorization** → two similar endpoints with
  different rules is a thing a future reader will want to "fix" in the wrong direction.
  Mitigated by recording the reasoning here and in the endpoint's own documentation.
- **Stale usage figures** → mitigated by reporting the measurement time; the residual risk
  is a tenant acting on a figure up to one sweep old, which is inherent to the sweep and
  not introduced here.
- **Quota state is reported from the control plane**, and the enforcement it describes is
  applied on the tenant cluster and re-asserted on a tick, so the two can disagree briefly
  after a state change. Acceptable: the report is advisory, and the authoritative
  behavior is what the database does.

## Migration Plan

1. Read model and service function assembling the record, the plan allowance and pooler
   configuration into one response, with the withholding rule applied in the service so
   both the API and `caelus` inherit it.
2. Endpoint and `caelus` parity over that service.
3. UI panel, mounted beside the SFTP panel on the deployment view.
4. `freepod db status`, over the endpoint from step 2. Independent of step 3 and orderable
   either way.

**Rollback**: removing the endpoint, the panel and the command. Nothing is written, so
there is no migration to reverse and no state to clean up.

## Open Questions

- **Should the panel offer a "rotate password" action?** Genuinely useful once a
  credential can be exposed by a person, and out of scope here: rotation is a write path
  that must coordinate with the reconciler's re-assertion of the stored password. It
  changes nothing in this change's specs.
- **Should the SFTP endpoint be tightened to match this one's administrator rule?** Worth
  doing, and separable: it is a change to a shipped endpoint with its own compatibility
  question, and bundling it here would put two authorization changes in one review.
