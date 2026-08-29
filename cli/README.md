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

| Command            | What it does                                                                         |
|--------------------|--------------------------------------------------------------------------------------|
| `freepod login`    | Sign in, and remember the credential.                                                |
| `freepod init`     | Set the current directory up as a project: choose a hostname, write `.freepod.json`. |
| `freepod deploy`   | Pack, build and release the current project.                                         |
| `freepod var`      | Read and change the environment your application runs with.                          |
| `freepod log`      | Stream your application's pod output.                                                |
| `freepod builds`   | List your builds, most recent first.                                                 |
| `freepod releases` | List this project's rollouts, most recent first; the live one is marked.             |
| `freepod delete`   | Delete this project's deployment.                                                    |
| `freepod whoami`   | Report who you are signed in as.                                                     |
| `freepod logout`   | Forget the stored credential.                                                        |
| `freepod key`      | Register the SSH public keys that identify you to the platform.                      |
| `freepod db`       | Report this deployment's database: name, role, password (masked), and quota state.   |
| `freepod skill`    | Install deployment instructions for your coding agents.                              |

`freepod --help` and `freepod <command> --help` cover the flags.

## Database

`freepod db status` reports this deployment's database: which database and
role it is, the password that owns it, and how much of the allowance is
used. The password is masked by default — pass `--show-password` to print
it.

The command prints **no address and no connection URL**, and offers no
flag that prints one. The database is reachable only from inside the
cluster, so a host or a `postgresql://` URL here would connect from
nowhere this machine can stand. The host, port and the one URL that will
actually work belong to `freepod db proxy`, which is the command that
establishes a tunnel and composes its own URL around its local address.

If the project records a deployment whose product offers no relational
storage, the command says so plainly and exits successfully — the
question was answered, not failed.

## SSH keys

`freepod key add` registers an SSH public key on your account. SSH is used as
transport for commands including `freepod db` and `freepod shell`.

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

Each deployment also gets its own PostgreSQL database. Nothing to set up:
`DATABASE_URL` and the usual `PG*` variables are already in the environment, so
any ORM or `psql` connects as-is.

`freepod db status` shows the database name, role, password, and quota usage.

## Environment variables

Inject environment variables in to your pod.

```bash
freepod var set LOG_LEVEL=debug        # sets it and rolls the deployment
freepod var set ADMIN_TOKEN --secret   # prompts without echo; write-only
freepod var list
freepod var rm LOG_LEVEL
```

Setting a var rolls the deployment, because that is what makes it take effect.
Several in one command produce one rollout. `--stage` records them for your
next deploy instead, and `freepod deploy --no-build` applies staged vars
without rebuilding your entire project.

A var marked `--secret` is **write-only**: the platform never returns it, so
`var list` shows its key with the value hidden and nothing can print it back.

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
