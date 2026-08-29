## Purpose

One SSH server has to serve three different intentions: a developer wanting a shell in
their own application, a client running the platform's database tooling, and a plain port
forward that carries no session at all. This capability defines the dispatcher that
decides which of those a connection gets, how it identifies the application container to
enter, what it does when that container cannot host a shell, and how it tells the
developer which release they landed on without corrupting the sessions that carry data.

## ADDED Requirements

### Requirement: A session with no command opens a shell in the application container
When a session requests no command, the dispatcher MUST place the user in the application container: its filesystem, its executables, and its environment, as seen from the process running there.

This is the purpose of the profile. A shell in the sidecar's own filesystem, holding none of the user's code, does not serve it.

#### Scenario: Shell sees the application's filesystem
- **WHEN** a user opens a session with no command against a pod whose application container is running
- **THEN** the resulting shell reads the application container's filesystem, not the sidecar's

#### Scenario: Shell sees the application's environment
- **WHEN** that shell inspects its environment
- **THEN** it carries the environment variables the application process was started with

### Requirement: The application process is identified by a documented, deterministic rule
The dispatcher MUST identify which process belongs to the application container by an explicit rule, not by a guess that happens to work. The rule MUST distinguish the application's processes both from the sidecar's own and from the pod's infrastructure process, and MUST be documented alongside the implementation.

When the rule cannot identify exactly one candidate, the dispatcher MUST say so and MUST NOT pick arbitrarily. Entering the wrong container silently is worse than refusing: a developer would debug something that is not their application and draw conclusions from it.

#### Scenario: Single application container is identified
- **WHEN** the pod has one application container beside the sidecar
- **THEN** the dispatcher identifies that container's process

#### Scenario: Sidecar's own processes are excluded
- **WHEN** the dispatcher enumerates candidates
- **THEN** processes belonging to the sidecar itself and to the pod's infrastructure container are not among them

#### Scenario: Ambiguity is refused, not guessed
- **WHEN** the rule identifies more than one candidate
- **THEN** the dispatcher reports the ambiguity and does not enter any of them

#### Scenario: No candidate
- **WHEN** no application process can be identified, because it is not running or the process namespace is not shared
- **THEN** the dispatcher reports that plainly, naming the likely cause

### Requirement: A recognized platform command runs in the sidecar
A session requesting one of the platform's own tools — the PostgreSQL client and dump/restore tooling — MUST run it in the sidecar, where those tools live and where their connection details are.

The set of commands treated this way MUST be an explicit allowlist. Membership MUST be decided on the requested command itself and MUST NOT be inferrable from arguments a client controls.

#### Scenario: Database client runs in the sidecar
- **WHEN** a session requests the PostgreSQL client
- **THEN** it runs in the sidecar and connects to the deployment's database

#### Scenario: Dump runs in the sidecar and streams
- **WHEN** a session requests a dump
- **THEN** the dump runs in the sidecar and its output is delivered to the client unmodified

#### Scenario: Allowlist is not argument-driven
- **WHEN** a session requests a command whose arguments resemble an allowlisted tool but whose command is not one
- **THEN** it is not treated as a platform command

### Requirement: Any other command runs in the application container
A session requesting a command that is not on the platform allowlist MUST run it in the application container, so that ordinary remote-command behavior holds and file transfer works without additional configuration.

File transfer tools operate by running a helper command on the remote side; routing arbitrary commands to the application container is what makes copying files into and out of the application work with no further support.

#### Scenario: Arbitrary command runs where the application is
- **WHEN** a session requests a command that is not on the platform allowlist
- **THEN** the command runs in the application container

#### Scenario: File copy reaches the application's filesystem
- **WHEN** a user copies a file to the deployment using a standard file transfer tool over this session
- **THEN** the file appears in the application container's filesystem

### Requirement: The command is never re-interpreted by a shell
The requested command MUST be passed to the target without being re-evaluated by a shell in a way that would let its text expand into further commands. The dispatcher MUST treat the requested command as data.

The requested command is attacker-influenced input arriving over the network at an authenticated but unprivileged boundary; re-evaluating it is a command injection.

#### Scenario: Shell metacharacters are not expanded by the dispatcher
- **WHEN** a session requests a command whose text contains shell metacharacters, substitutions, or separators
- **THEN** the dispatcher does not evaluate them as additional commands

### Requirement: Port forwarding never reaches the dispatcher
A connection that requests only port forwarding opens no session, so the dispatcher MUST NOT be involved in it and MUST NOT be able to prevent it. Forwarding is constrained by the server's own configuration, not by this dispatcher.

#### Scenario: Forwarding works with no session
- **WHEN** a client opens a connection requesting only a permitted port forward and no session
- **THEN** the forward is established without the dispatcher running

#### Scenario: A broken dispatcher does not break forwarding
- **WHEN** the dispatcher would fail for a session on this pod
- **THEN** a forwarding-only connection is unaffected

### Requirement: An application container that cannot host the session fails plainly
The application container may be a minimal image containing no shell, or may not contain the requested executable. The dispatcher MUST report that plainly and exit non-zero, naming the cause and the container it applies to. It MUST NOT place the session anywhere else.

This matches `docker exec` and `kubectl exec`, which fail the same way for the same reason, and it is what a developer expects: the contents of the application image are theirs, and adding a shell to it is a change they can make. Silently landing them in a different container would be worse than the failure — they would inspect something that is not their application and conclude from it.

The message MUST name the cause rather than surfacing a raw execution failure, which reads as a platform fault rather than as a property of the user's own image.

#### Scenario: Minimal application image
- **WHEN** a user opens a session with no command against a deployment whose application image contains no shell
- **THEN** the dispatcher reports that the application image provides no shell, exits non-zero, and opens no session elsewhere

#### Scenario: Requested command is absent from the application container
- **WHEN** a session requests a command the application container does not contain
- **THEN** the dispatcher reports that, exits non-zero, and does not run the command in the sidecar

#### Scenario: Failure is explained, not raw
- **WHEN** either failure occurs
- **THEN** the message names the cause rather than surfacing an executable-not-found error

### Requirement: Every session reports which release it landed on
The dispatcher MUST report the identity of the release whose pod the session reached, taking it from configuration supplied to the container rather than deriving it by observation.

During a rollout, two releases' pods can both be serving and the connection lands on one of them unpredictably. Without this, a developer investigating a broken release can be shown a working one and conclude nothing is wrong.

#### Scenario: Session states its release
- **WHEN** a user opens an interactive session
- **THEN** the session reports the release identity it reached

#### Scenario: Identity comes from configuration
- **WHEN** the release identity is reported
- **THEN** it is the value supplied to the container, not one inferred from the pod's name or from timing

### Requirement: The banner never corrupts a session that carries data
The banner MUST NOT be written to the session's standard output, and MUST NOT appear in non-interactive sessions.

File transfer and dump streams use standard output as a protocol channel: text written there corrupts a transfer, and the resulting failure appears as a mysterious data error far from its cause.

#### Scenario: File transfer is unaffected
- **WHEN** a user copies a file over a session
- **THEN** no banner text appears in the transferred data and the transfer succeeds

#### Scenario: Dump output is unaffected
- **WHEN** a session streams a database dump
- **THEN** the dump output contains no banner text and restores cleanly

#### Scenario: Interactive session still sees it
- **WHEN** a user opens an interactive session
- **THEN** the banner is visible to them
