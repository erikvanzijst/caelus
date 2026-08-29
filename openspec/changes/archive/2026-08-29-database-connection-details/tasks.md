## 1. Read model and service

- [x] 1.1 Add the read model for a deployment's database connection details: pooler host
      and port, database name, role name, password, quota state, size, allowance and
      measurement time. No composed URL — nothing in this change assembles one (design.md
      § *No connection URL exists in this change*). Verify every field the specs require is
      present, that no field carries a URL, and that the model can represent a withheld
      password distinguishably from an absent one.
- [x] 1.2 Add a service function in `api/app/services/` assembling that model from the
      `deployment_database` record, the deployment's plan allowance, and the platform's
      pooler configuration. Put the whole rule in the service so the API and `caelus`
      inherit identical behavior. Verify with a unit test against a provisioned record.
- [x] 1.3 Return the pooler's host and port, never the tenant cluster's. Verify by test
      that the response's host and port come from the pooler settings.
- [x] 1.4 Keep the pooler host and port in the model even though no surface displays
      them: `freepod db proxy` needs to know what to forward to, and withholding them is a
      presentation decision rather than a change to the read model. Verify they are
      returned by the service and that the two reader surfaces are what omit them.
- [x] 1.5 Implement the one absence state this capability owns: the product offers no
      relational storage. Reach the deployment through `get_deployment_orm`, so missing,
      not-yours and deleted answer identically without this service deciding anything —
      do not open-code that check the way `get_sftp_credentials` does. Do not add a
      "provisioning" state either: a database is provisioned before its deployment is
      settled (design.md § *Two absence states*). Verify a settled deployment with
      relational storage always yields details, that a product without it yields the stable
      not-found the UI keys on, and that a deleted deployment and one requested under the
      wrong owner both yield the platform's standard not-found.
- [x] 1.6 Report quota state, `size_bytes`, `measured_at` and the plan allowance, with
      never-measured distinguishable from measured-at-zero. Verify both cases.
- [x] 1.7 Apply the withholding rule in the service: the password is returned to the owner
      only, and the model states that it was withheld otherwise (design.md § *The password
      goes to the owner*). Verify an administrator read carries no field containing the
      password, in any form.
- [x] 1.8 Verify reading has no side effects: the stored record, the password and the
      quota state are unchanged after a read, and two consecutive reads return the same
      password.

## 2. Endpoint

- [x] 2.1 Add the read endpoint under the deployment resource, following the nested-route
      convention and the existing SFTP credentials endpoint's shape. Verify the route
      exists at the deployment scope with no root-level alternative.
- [x] 2.2 Wire authorization so the owner and administrators may read, and anyone else is
      refused with the platform's standard error. Verify a non-owner is refused.
- [x] 2.3 Verify the administrator path end to end through the API: details present,
      password absent, withholding stated.
- [x] 2.4 Ensure the password never reaches a log on any path. Verify by exercising a
      successful read and a failure occurring after decryption, and asserting the captured
      log output contains the password in no form.
- [x] 2.5 Document the endpoint, including why its administrator rule differs from the
      SFTP credentials endpoint's, and why it returns components rather than a composed
      URL — so both divergences read as deliberate rather than as oversights to be
      "fixed".
- [x] 2.6 Add `caelus` CLI parity over the same service, subject to the same withholding
      rule. Verify an operator who is not the owner sees no password.

## 3. UI panel

- [x] 3.1 Implement the panel as its own component under `ui/src/components/`, mounted on
      the deployment view beside the SFTP panel and following its conditional-display
      pattern. Verify the page composes it rather than defining it inline.
- [x] 3.2 Render the database name, role name and a masked password, with a copy
      affordance for each. Render no host, no port and no connection URL. Verify the
      password can be copied without first revealing it, and that the rendered panel
      contains neither the pooler address nor a `postgresql://` string.
- [x] 3.3 Hide the panel entirely when the product offers no relational storage. Verify no
      placeholder is rendered.
- [x] 3.4 Take transitional deployments from the deployment's own status: re-request the
      details when a transitional deployment settles, following `DeploymentCard`'s existing
      `settled` pattern for the SFTP panel, and add no database-specific "being prepared"
      state. Verify the panel populates on settling without a page reload.
- [x] 3.5 State that the database is reachable from the running application and not from
      the reader's machine, without asserting that a local connection is available
      (design.md § *Both surfaces say where the database can be reached from*). Verify a reader cannot
      conclude the credentials it shows can be pointed at anything on their own machine.
- [x] 3.6 Show measured size against allowance with the measurement time, and say the size
      is not yet known rather than showing zero when it has never been measured. Verify
      both.
- [x] 3.7 Present read-only and suspended states prominently, each explaining its
      consequence in the owner's terms — writes rejected, application cannot connect.
      Verify both states render distinctly from a healthy database.
- [x] 3.8 Verify the password is masked on first render, is not written to browser storage
      or the address bar, and is revealed only on an explicit action.
- [x] 3.9 Render the administrator view: details shown, password stated as withheld, no
      error state and no reveal affordance that cannot work. Verify against an API
      response carrying a withheld password.

## 4. `freepod db status`

- [x] 4.1 Add a `db` command group to the client, holding `status`. Give the group help
      text that says what it covers today without promising the forwarding commands
      `var/ssh_access.md` D10 reserves for it. Verify the group and subcommand are
      reachable and that `--help` works on both.
- [x] 4.2 Read the endpoint through the existing `ApiClient`, resolving the deployment
      from the project file with `_project_deployment` rather than from an argument.
      Verify the command refuses a project recording no deployment with the same usage
      error the other project-scoped commands give.
- [x] 4.3 Report the database name, role name, password, size, allowance, measurement time
      and state. Print no host, no port and no connection URL, and offer no flag that
      prints one (design.md § *The reader's surfaces show identity and credential, not
      address*). Verify no output path emits the pooler address or a `postgresql://`
      string, including with every flag combination the command accepts.
- [x] 4.4 Mask the password by default and say how to reveal it. Verify the default output
      contains the password nowhere, and that the mask is not mistakable for the value.
- [x] 4.5 Add `--show-password`, printing the password. Verify.
- [x] 4.6 State that the database is reachable from the running application and not from
      this machine, on stderr as a diagnostic. Verify it appears in the default output.
- [x] 4.7 Report read-only and suspended states with their consequence in the owner's
      terms, and say the size is not yet known rather than printing zero when it has never
      been measured. Verify all three.
- [x] 4.8 Report a product with no relational storage plainly, with a successful exit
      rather than an error. Verify the exit code.
- [x] 4.9 Honor the client's existing surface conventions: `--quiet` silences the
      diagnostics, and color is suppressed off a terminal. Verify alongside the other
      commands in `tests/test_surface.py`.

## 5. Verification and documentation

- [x] 5.1 Verify end to end on dev against a real `custom` deployment with relational
      storage: the owner sees the panel with the correct database and role names; the
      revealed password matches the value in the deployment's database Secret; and the
      quota figures match the record.
- [x] 5.2 Verify against a deployment whose product has no relational storage that no
      panel appears and the endpoint reports the feature unavailable.
- [x] 5.3 Confirm nothing was provisioned, rotated or mutated by any of the above: the
      `deployment_database` record is byte-identical before and after, and no reconcile
      was triggered.
- [x] 5.4 Update `api/README.md` with the endpoint, its response, its absence semantics,
      and the administrator withholding rule with its rationale.
- [x] 5.5 Update `ui/README.md` with the panel component and its states.
- [x] 5.6 Verify `freepod db status` end to end on dev against the same deployment as 5.1:
      the reported database, role and quota figures match the panel's, and
      `--show-password` matches the value in the deployment's database Secret.
- [x] 5.7 Update `cli/README.md`'s command table and `cli/DEVELOPMENT.md` with the `db`
      group, the masking rule, and why the command reports no address — so the omission
      reads as deliberate rather than as a field someone forgot. Keep internals out of the
      README as that file's own rule requires.
- [x] 5.8 Update the agent skill in `cli/src/freepod/assets/SKILL.md`: add `freepod db` to
      the command reference and tell § *The database* that an agent can read the
      credentials and the quota state from the client, while the environment remains the
      way the running app gets them.
