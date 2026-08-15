## Purpose

The shape of the shipped command-line client: how it is installed and invoked, what it
is allowed to depend on, and the conventions every one of its commands obeys so that
scripts, pipelines, and humans can all rely on its behavior.

## ADDED Requirements

### Requirement: The client is a standalone installable package

The client SHALL be distributed as a self-contained package that installs a single
executable named `freepod`. It SHALL NOT import, vendor, or otherwise depend on the
Freepod API server's source code, and SHALL interact with the platform exclusively
through the public REST API.

The client SHALL run on Python 3.9 and later. Every runtime dependency SHALL be pure
Python, so that installation requires no compiler and every published wheel is usable
on every supported platform.

#### Scenario: The executable is installed and runnable

- **WHEN** the package is installed into an isolated environment
- **THEN** a `freepod` executable is available on the path
- **AND** `freepod --help` lists the available commands and exits 0

#### Scenario: No dependency on server code

- **WHEN** the client is installed with no Freepod API source present on the machine
- **THEN** every command runs without import errors

#### Scenario: Installation requires no build toolchain

- **WHEN** the package and its dependencies are installed on a machine with no C
  compiler
- **THEN** installation succeeds

### Requirement: Results and diagnostics use separate streams

The client SHALL write command results to standard output and SHALL write progress,
prompts, and diagnostics to standard error, so that a redirected or piped stdout
carries only the result.

Build output streamed from the platform SHALL be treated as a result and written to
standard output.

#### Scenario: Piped output carries only results

- **WHEN** a command's standard output is redirected to a file
- **THEN** the file contains only result content
- **AND** progress and diagnostic messages still appear on the terminal

### Requirement: Exit codes distinguish failure classes

The client SHALL exit with a stable, documented code that identifies the class of
outcome:

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected error |
| 2 | usage error |
| 3 | not authenticated |
| 4 | build failed or was canceled |
| 5 | rollout failed, or waiting for it timed out |

#### Scenario: A failed build is distinguishable from a failed rollout

- **WHEN** a deploy ends because the build reached a `failed` status
- **THEN** the process exits 4

- **WHEN** a deploy ends because the deployment reached an `error` status
- **THEN** the process exits 5

#### Scenario: A missing credential is distinguishable from a generic error

- **WHEN** a command requiring authentication runs with no usable credential
- **THEN** the process exits 3

### Requirement: Waiting is bounded and a timeout is reported as a timeout

Every operation in which the client waits on the platform SHALL be bounded by a
configurable timeout. When that bound is reached, the client SHALL report that it
stopped waiting and SHALL state that the underlying operation may still be in progress,
rather than reporting the operation as failed.

#### Scenario: A slow build stops the wait, not the build

- **WHEN** the configured build timeout elapses while the build is still running
- **THEN** the client reports that it has stopped waiting
- **AND** the message states that the build continues on the platform

### Requirement: Automatic retries are limited to requests that are safe to repeat

The client SHALL retry only requests whose repetition cannot create or duplicate state,
using bounded backoff. Requests that are not safe to repeat SHALL fail to the caller
instead of being retried automatically.

#### Scenario: A transient server error on a read is retried

- **WHEN** a read request fails with a 5xx status or a network error
- **THEN** the client retries it with backoff up to a bounded number of attempts

#### Scenario: An unsafe request is not retried

- **WHEN** a request that would create or mutate state fails
- **THEN** the client does not silently repeat it

### Requirement: Color output can be suppressed

The client SHALL emit no color escape sequences when standard output is not a terminal,
or when the environment requests no color.

#### Scenario: Redirected output is plain

- **WHEN** output is redirected to a file, or `NO_COLOR` is set in the environment
- **THEN** the emitted text contains no color escape sequences
