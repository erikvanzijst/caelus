# freepod

Take a local project directory to a running deployment on
[freepod.eu](https://freepod.eu).

```bash
pip install freepod || uv tool install freepod
```

```bash
cd myapp
freepod login      # sign in through the browser
freepod init       # choose a hostname for this project
freepod deploy     # https://myapp.freepod.eu
```

`deploy` packs the working tree, uploads it, builds a container image on the
platform and releases it. By the time the command returns, the app is live on
its own hostname over HTTPS. Ship a new version by running it again.

There is no Dockerfile to write and nothing to configure:
[Railpack](https://railpack.com) detects the stack — Node, Python, Go, Java,
PHP, Ruby, Rust and more — and builds an image from your source as it is.

## What you need

- **A Freepod account.** `freepod login` opens the sign-in page, which is also
  where you can register.
- **Python 3.9 or newer**, for the CLI itself. The project you deploy can be in
  any language Railpack supports.
- **An app that listens on `$PORT`.** The platform assigns the port and passes
  it in the environment, so bind `0.0.0.0:$PORT` (`process.env.PORT`,
  `os.environ["PORT"]`, …) rather than a fixed number. An app that picks its own
  port receives no traffic.

## Commands

| Command          | What it does                                                                          |
|------------------|---------------------------------------------------------------------------------------|
| `freepod login`  | Sign in, and remember the credential.                                                 |
| `freepod init`   | Set the current directory up as a project: choose a hostname, write `.freepod.json`.  |
| `freepod deploy` | Pack, build and release the current project.                                          |
| `freepod builds` | List your builds, most recent first.                                                  |
| `freepod delete` | Delete this project's deployment.                                                     |
| `freepod whoami` | Report who you are signed in as.                                                      |
| `freepod logout` | Forget the stored credential.                                                         |
| `freepod skill`  | Install deployment instructions for your coding agents.                               |

`freepod --help` and `freepod <command> --help` cover the flags.

## Hostnames

`init` asks for one. A bare name becomes a subdomain of the platform: `myapp` is
served at `myapp.freepod.eu`. To use a domain of your own, point a CNAME at
`freepod.eu` first, then give `init` the full name. Certificates are issued and
renewed for you either way.

## Persistence

Deployments have no persistent disks or volumes. Whatever the app writes to its
own filesystem is gone when it restarts, and at every release.

Instead, each pod has its own private S3-compatible bucket for object storage.
Use with any aws-s3 client. `S3_BUCKET`, `BUCKET_NAME` and `AWS_*` environment
variables and access keys are already set.

## .freepod.json

`init` writes it, and it is meant to be committed. It records the hostname you
chose and which deployment this directory belongs to, so the next `deploy` —
yours, a coworker's, or CI's — updates that same app instead of creating a
second one. To change a value, edit the file; the next deploy applies it.

## What gets uploaded

The working tree, minus `.git/`, anything your `.gitignore` excludes, and the
usual build output (`node_modules/`, `.venv/`, `__pycache__/`, `dist/`, …). A
`.freepodignore` file — same syntax as `.gitignore`, and applied last — keeps
out anything else the build does not need.

Re-including a file follows git's rules, with one wrinkle worth knowing: the
negation has to name the path (`!node_modules/patched.js`; a bare
`!patched.js` does nothing), and nothing beneath a directory you excluded
yourself can come back. Exclude `build/*` rather than `build/` if you need an
exception.

## Output

The address is the only thing `deploy` writes to stdout. The build log, the
progress bar and every status line go to stderr:

```bash
URL=$(freepod deploy)
```

## Deploying with a coding agent

Install the freepod skill:

```bash
freepod skill install
```

Then just prompt:

> Build a URL shortener for freepod and deploy it to links.freepod.eu

Supported: **Claude Code**, **Codex**, **OpenCode**, **Amp**, **Gemini CLI**

---

Deployments are listed and managed at [freepod.eu](https://freepod.eu). Source
and issues: [github.com/erikvanzijst/freepod](https://github.com/erikvanzijst/freepod).
