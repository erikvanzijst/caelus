---
name: deploy-to-freepod
description: Deploy a web app to freepod.eu using the `freepod` CLI — it builds a container from source with no Dockerfile and serves it on its own HTTPS hostname. Use when asked to deploy, ship, host, or put a web app online; when adapting an existing codebase to run on Freepod; or when the user mentions freepod, `freepod deploy`, or `.freepod.json`. Also read it *before* designing a new app that will be deployed there, because the platform's constraints (bind `$PORT`, no disk, no env vars, S3 for all state) decide whether an app can run at all.
---

# Deploying to Freepod

Freepod takes a source directory, builds it into a container image with
[Railpack](https://railpack.com), and serves it at a hostname over HTTPS. There
is no Dockerfile to write and no build configuration. The whole workflow is:

```bash
freepod login      # once, interactive — a human has to do this
freepod init       # choose a hostname, writes .freepod.json
freepod deploy     # pack, upload, build, release
```

Deployment is not the hard part. **Fitting the platform's constraints is**, and
they are strict enough to rule some applications out entirely. Read the next
section before you write or port any code.

## Does the app fit? Check before writing code

Five constraints. Each one silently produces a deployment that builds fine and
then does not work.

**1. The app must bind `0.0.0.0:$PORT`.** The platform assigns the port and
passes it in the environment. An app that hardcodes a port receives no traffic.
Read it as `process.env.PORT`, `os.environ["PORT"]`, `os.Getenv("PORT")` —
whatever your language spells it — and bind `0.0.0.0`, never `127.0.0.1`.

**2. There is no persistent disk.** Anything the app writes to its own
filesystem is gone at the next restart and at every release. This rules out
SQLite, local file uploads, on-disk session stores, and any cache whose loss
matters.

**3. There is no database.** No Postgres, no MySQL, no Redis. A deployment gets
an S3 bucket (below) and nothing else. Porting an app with a relational schema
means either rewriting its persistence onto object storage or pointing it at a
database you host somewhere else and reaching it over the network.

**4. There is no mechanism for supplying environment variables or secrets.**
The only variables injected into the container are `PORT` and the S3
credentials. You cannot set an API key through the CLI or the project file.
The only way to get configuration in is to put it in the source tree, which
means it is baked into the image — acceptable for non-secret configuration,
and a real disclosure risk for anything else. Note that `.env` is deliberately
**not** excluded from the upload (`.env.local` and `.env.*.local` are), so an
`.env` committed to the tree will ship.

**5. One HTTP service per deployment.** No sidecars, no worker processes, no
scheduled jobs. If the app is a stack of cooperating services, only one of them
can live here.

If the app fails any of these and cannot be adapted, say so before building
anything. That is a more useful answer than a deployment that comes up broken.

## Object storage: the one place state can live

Every deployment is automatically given its own **private S3 bucket** on the
platform's Garage instance. There is nothing to enable, provision, or
configure — the credentials are in the container's environment under the names
an S3 SDK already looks for:

```
AWS_ACCESS_KEY_ID          AWS_ENDPOINT_URL_S3     S3_BUCKET
AWS_SECRET_ACCESS_KEY      AWS_ENDPOINT_URL        BUCKET_NAME
AWS_REGION / AWS_DEFAULT_REGION
```

> **The bucket name is in `S3_BUCKET` (or its alias `BUCKET_NAME`), which is
> not an `AWS_*` variable and has no AWS convention behind it.** This is the
> single most guessable-wrong fact on this page. Everything else an SDK picks
> up on its own; the bucket name it cannot.

In Python that is the whole of it:

```python
import boto3, os
s3 = boto3.client("s3")                    # reads AWS_* from the environment
s3.put_object(Bucket=os.environ["S3_BUCKET"], Key="hello.txt", Body=b"hi")
```

Three things worth knowing:

- **Path-style addressing.** The endpoint serves `…/bucket/key`, not
  `bucket.host/key`. boto3 selects this automatically for a custom endpoint.
  The JavaScript v3 client does not: pass `forcePathStyle: true`.
- **Presigned URLs work in a browser.** The endpoint is publicly reachable, so
  a URL the app signs can go straight to an end user for download or upload,
  and the bytes never pass through the container. CORS is preconfigured,
  including the `ETag` exposure that multipart uploads need.
- **User metadata does not survive.** Garage does not return `Metadata` on
  `GetObject`. Use the object's `LastModified`, or store what you need in the
  object body or the key.

## Make the start command explicit

Railpack infers a start command from the source tree. The inference is good but
it is a guess, and a wrong guess costs a build cycle you cannot debug from
logs. Remove the guess with a `Procfile` at the project root — it takes
precedence, and it works whatever the language:

```procfile
web: <the command that starts your server, binding 0.0.0.0:$PORT>
```

```procfile
web: uvicorn main:app --host 0.0.0.0 --port $PORT      # Python / ASGI
web: gunicorn -b 0.0.0.0:$PORT app:app                 # Python / WSGI
web: node server.js                                    # Node
web: ./server                                          # compiled binary
```

Railpack still handles dependency installation from whatever manifest it finds
(`requirements.txt`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`,
…). The `Procfile` only pins the last step.

## The procedure

### 1. Confirm authentication before anything else

```bash
freepod whoami
```

Exit code 3 means not authenticated. **Do not try to log in on the user's
behalf.** `freepod login` needs a human at a browser: in a container or over
SSH it falls back to the device flow, which prints a URL and a code that
someone has to approve on another device, and it blocks for up to 300 seconds
waiting. Stop and ask the user to run `freepod login` themselves.

### 2. Initialize the project

`freepod init` **prompts interactively** for a hostname. To run it
non-interactively, pipe the answer:

```bash
printf 'myapp\n' | freepod init
```

A bare label becomes a subdomain of the platform (`myapp` → `myapp.freepod.eu`).
A value containing a dot is taken as already qualified, for a custom domain
pointed at the platform with a CNAME. Certificates are issued either way.

This writes `.freepod.json`, which records the hostname and — after the first
deploy — the deployment this directory belongs to. It is meant to be committed.
To change a value, edit the file. Do not re-run `init --force` or
`deploy --recreate` on an initialized project unless the user asks: both
discard the deployment pointer and orphan the running deployment.

### 3. Verify locally — this step is not optional

**The platform offers no runtime logs.** There is no `freepod logs`. Once the
container is running, the only thing you can observe from outside is its HTTP
responses. Every bug you do not catch locally becomes a bug you diagnose by
redeploying.

So run the app the way the platform will, and exercise it:

```bash
PORT=8080 <your start command>
curl -sS localhost:8080/           # and every other route that matters
```

If the app talks to S3, stub the client locally rather than skipping the path
entirely — a fake in-memory S3 in a test is enough to prove routing,
serialization and error handling before a build is spent on it.

### 4. Deploy

```bash
freepod deploy
```

Preflight, pack, upload, build, release. **Allow several minutes** — builds
typically run one to three minutes and the client waits up to 1800s for the
build and 600s for the rollout, so set a generous timeout on whatever runs it.
The build log streams to stderr. Stdout carries exactly one line, the live
address:

```bash
URL=$(freepod deploy)
```

Ship a new version by running it again.

### 5. Verify the deployed app

Do not report success because `deploy` returned. Exercise the live URL the way
you exercised localhost — at minimum a health endpoint and the primary write
path, since the S3 wiring is the part that could not be fully tested locally.

## What gets uploaded

The working tree, minus `.git/`, minus your `.gitignore`, minus built-in
defaults that already cover the usual noise: `node_modules/`, `.venv/`,
`venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `target/`, `dist/`,
`build/`, `.DS_Store`, `*.swp`, `.env.local`, `.env.*.local`. You do not need
to re-exclude any of those.

Add a `.freepodignore` (same syntax as `.gitignore`, applied last) only for
things those rules miss. Two wrinkles:

- `dist/` and `build/` are excluded by default. If the project depends on a
  *committed* build output rather than building on the platform, re-include it
  explicitly or the image will be missing it.
- A negation must name the path: `!node_modules/patched.js` works, a bare
  `!patched.js` does nothing, and nothing under a directory you excluded
  yourself can come back — exclude `build/*` rather than `build/` if you need
  an exception.

## When it goes wrong

| Symptom | What it means | What to do |
|---|---|---|
| Exit 3 | Not authenticated | Ask the user to run `freepod login` |
| Exit 4, build log ends in an error | Build failed | The streamed log is the whole story; `freepod builds` lists status and duration |
| Exit 5 | Image built, rollout failed or timed out | Usually the container exits at startup — check the start command and that it binds `0.0.0.0:$PORT` |
| Deploy succeeds, requests hang or 502 | App is not listening where the platform expects | Bind `0.0.0.0:$PORT`, not a hardcoded port and not `127.0.0.1` |
| Deploy succeeds, one endpoint 500s | A runtime fault you cannot see | See below |

**Diagnosing a runtime fault without logs.** Reproduce it locally first; that
resolves most cases. When something fails *only* when deployed, the fastest
path is to make the container answer the question over HTTP: add a temporary
endpoint that reports what you need — which environment variables are present,
whether the S3 client can list the bucket, what a failing call actually raised —
deploy, read it, then remove it. Building a diagnostic into the app is not
elegant, but it is the only channel available, and it is faster than guessing.

**That endpoint is on the public internet.** Report variable *names*, never
values — dumping the environment publishes the bucket credentials — and take it
out in the next deploy rather than leaving it behind.

Give every app a `/healthz` from the start. It costs three lines and it
separates "the container is not running" from "the container is running and the
app is wrong."

## Command reference

| Command | Purpose |
|---|---|
| `freepod login` | Sign in. Interactive — a human must do it. |
| `freepod whoami` | Report the authenticated account. Never starts a login. |
| `freepod init` | Set up the directory; prompts for a hostname. |
| `freepod deploy` | Pack, build, release. Prints the URL on stdout. |
| `freepod builds` | List this account's builds, most recent first. |
| `freepod delete` | Delete the deployment **and everything it stores**. Destructive; confirm with the user first, and note it prompts unless given `-y`. |
| `freepod logout` | Forget the cached credential. |

Exit codes: `0` ok, `2` usage, `3` not authenticated, `4` build failed,
`5` rollout failed, `1` anything else.
