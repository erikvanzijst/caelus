#!/usr/bin/env python3
"""freepod-cli — a demo OAuth2 client for the Freepod API.

Obtains a Keycloak access token (loopback + PKCE, or the device authorization
grant when no browser is reachable), then calls two API endpoints:

    GET /api/me                        → the authenticated user
    GET /api/users/{id}/deployments    → that user's deployments

Python 3 standard library only — no third-party packages, no venv, no pip.
Run it directly:

    ./freepod_cli.py --env dev

See README.md for the full story, and api/README.md § "External API clients
(OAuth2 tokens)" for the authoritative protocol reference.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

ISSUER = "https://keycloak.freepod.eu/realms/freepod"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/protocol/openid-connect/auth"
DEVICE_ENDPOINT = f"{ISSUER}/protocol/openid-connect/auth/device"
TOKEN_ENDPOINT = f"{ISSUER}/protocol/openid-connect/token"

# The registered redirect URIs are the port-less forms http://127.0.0.1/callback
# and http://localhost/callback. Keycloak relaxes *port* matching for loopback
# hosts (RFC 8252 section 7.3), so any ephemeral port matches — but the path is
# matched exactly and the two host strings are distinct. Do not change this.
CALLBACK_PATH = "/callback"
CALLBACK_HOST = "127.0.0.1"

SCOPES = "openid email profile offline_access"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

# Both clients are public: PKCE proves client identity and no secret exists.
ENVIRONMENTS = {
    "dev": {"client_id": "freepod-cli-dev", "api_base": "https://dev.freepod.eu"},
    "prod": {"client_id": "freepod-cli-prod", "api_base": "https://freepod.eu"},
}

USER_AGENT = "freepod-cli/1.0 (+https://freepod.eu)"
HTTP_TIMEOUT = 30


# --------------------------------------------------------------------------
# Errors and diagnostics
# --------------------------------------------------------------------------


class FreepodError(Exception):
    """Anything that should end the run with a readable message."""


class OAuthError(FreepodError):
    """An OAuth2 error response, carrying the machine-readable `error` code."""

    def __init__(self, message: str, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def log(message: str) -> None:
    """Diagnostics go to stderr so stdout stays clean for --json."""
    print(message, file=sys.stderr)


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------


def post_form(url: str, fields: dict) -> dict:
    """POST an application/x-www-form-urlencoded body and parse the JSON reply."""
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise OAuthError(f"HTTP {exc.code} from {url}: {raw.strip()[:300]}",
                             status=exc.code) from None
        code = payload.get("error")
        description = payload.get("error_description") or code or raw.strip()[:300]
        raise OAuthError(description, code=code, status=exc.code) from None
    except urllib.error.URLError as exc:
        raise FreepodError(f"cannot reach {url}: {exc.reason}") from None


def api_get(url: str, access_token: str) -> tuple[int, object]:
    """GET a Freepod API endpoint. Returns (status, parsed body-or-text)."""
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw.strip()
    except urllib.error.URLError as exc:
        raise FreepodError(f"cannot reach {url}: {exc.reason}") from None


# --------------------------------------------------------------------------
# PKCE and token inspection
# --------------------------------------------------------------------------


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for the S256 method."""
    verifier = b64url(secrets.token_bytes(64))  # 86 chars, within RFC 7636's 43-128
    challenge = b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def decode_claims(jwt: str) -> dict:
    """Decode a JWT payload *without verifying it* — for display only.

    The edge is what verifies tokens; this client never makes a trust decision
    on the strength of these claims.
    """
    try:
        payload = jwt.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception:
        return {}


# --------------------------------------------------------------------------
# Token cache
# --------------------------------------------------------------------------


def cache_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "freepod", "tokens.json")


def load_cache() -> dict:
    try:
        with open(cache_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(data: dict) -> None:
    """Write the cache atomically at mode 0600, in a 0700 directory."""
    path = cache_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    temporary = f"{path}.{os.getpid()}.tmp"
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def load_refresh_token(env: str) -> str | None:
    entry = load_cache().get("environments", {}).get(env) or {}
    token = entry.get("refresh_token")
    return token if isinstance(token, str) and token else None


def store_refresh_token(env: str, client_id: str, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    data = load_cache()
    environments = data.setdefault("environments", {})
    environments[env] = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "stored_at": int(time.time()),
    }
    data["version"] = 1
    save_cache(data)


def forget_environment(env: str) -> bool:
    data = load_cache()
    environments = data.get("environments", {})
    if env not in environments:
        return False
    del environments[env]
    save_cache(data)
    return True


# --------------------------------------------------------------------------
# Flow selection
# --------------------------------------------------------------------------


def detect_browser() -> tuple[bool, str]:
    """Decide whether a browser on *this* machine can serve a loopback redirect.

    A container is disqualifying even if a browser binary exists: the redirect
    lands on the container's own 127.0.0.1, which the user's browser cannot
    reach.
    """
    if os.path.exists("/.dockerenv"):
        return False, "running in a container (/.dockerenv present)"

    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as handle:
            cgroup = handle.read()
        if any(marker in cgroup for marker in ("docker", "containerd", "kubepods", "libpod")):
            return False, "running in a container (container runtime in /proc/1/cgroup)"
    except OSError:
        pass

    if sys.platform.startswith("linux") and not any(
        os.environ.get(name) for name in ("DISPLAY", "WAYLAND_DISPLAY", "BROWSER")
    ):
        return False, "no DISPLAY, WAYLAND_DISPLAY or BROWSER set on Linux"

    try:
        browser = webbrowser.get()
    except webbrowser.Error:
        return False, "webbrowser found no usable browser"

    return True, f"browser available ({getattr(browser, 'name', None) or type(browser).__name__})"


# --------------------------------------------------------------------------
# Flow (a): authorization code + PKCE over a loopback listener
# --------------------------------------------------------------------------


class _CallbackHandler(BaseHTTPRequestHandler):
    """Serves the single redirect Keycloak sends the browser to."""

    server_version = "freepod-cli"
    sys_version = ""

    def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler's naming
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            # Browsers speculatively fetch /favicon.ico; ignore anything that
            # is not the redirect rather than treating it as the one request.
            self.send_error(404, "Not the callback")
            return

        params = {key: values[0] for key, values in
                  urllib.parse.parse_qs(parsed.query).items()}
        self.server.oauth_result = params

        if "error" in params:
            title, detail = "Authorization failed", params.get(
                "error_description", params["error"])
        else:
            title, detail = "Signed in to Freepod", "You can close this tab and return to your terminal."

        page = (
            "<!doctype html><meta charset='utf-8'>"
            "<title>Freepod CLI</title>"
            "<body style=\"font-family:system-ui,sans-serif;margin:4rem auto;max-width:32rem\">"
            f"<h1 style='font-size:1.25rem'>{title}</h1><p>{detail}</p></body>"
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, fmt, *args):
        """Silence the default stderr access log."""


def loopback_flow(client_id: str, timeout: int, verbose: bool) -> dict:
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)

    # Bind first: the ephemeral port is part of the redirect_uri we register in
    # the authorization request.
    server = HTTPServer((CALLBACK_HOST, 0), _CallbackHandler)
    server.oauth_result = None
    server.timeout = 1
    port = server.server_address[1]
    redirect_uri = f"http://{CALLBACK_HOST}:{port}{CALLBACK_PATH}"

    authorization_url = AUTHORIZATION_ENDPOINT + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    log(f"Listening on {redirect_uri} for the authorization redirect.")
    if verbose:
        log(f"Authorization URL: {authorization_url}")

    try:
        if webbrowser.open(authorization_url):
            log("Opened your browser to sign in.")
        else:
            log("Could not open a browser automatically. Visit this URL:\n"
                f"  {authorization_url}")

        deadline = time.monotonic() + timeout
        while server.oauth_result is None:
            if time.monotonic() >= deadline:
                raise FreepodError(
                    f"timed out after {timeout}s waiting for the authorization "
                    "redirect (use --device for a browser-less flow)")
            server.handle_request()
        params = server.oauth_result
    finally:
        server.server_close()

    if "error" in params:
        raise OAuthError(params.get("error_description", params["error"]),
                         code=params["error"])
    if params.get("state") != state:
        raise FreepodError("state mismatch on the authorization redirect — "
                           "possible CSRF, refusing the response")
    if "code" not in params:
        raise FreepodError("authorization redirect carried no code")

    log("Received the authorization code; exchanging it for tokens.")
    return post_form(TOKEN_ENDPOINT, {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": params["code"],
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    })


# --------------------------------------------------------------------------
# Flow (b): device authorization grant
# --------------------------------------------------------------------------


def device_flow(client_id: str, verbose: bool) -> dict:
    verifier, challenge = pkce_pair()

    # RFC 8628 has no redirect and therefore no PKCE, but these clients mandate
    # PKCE and Keycloak enforces it on the device endpoint too. Omitting the
    # challenge here fails with "Missing parameter: code_challenge_method".
    authorization = post_form(DEVICE_ENDPOINT, {
        "client_id": client_id,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    device_code = authorization["device_code"]
    user_code = authorization["user_code"]
    interval = int(authorization.get("interval", 5))
    expires_in = int(authorization.get("expires_in", 600))
    complete_uri = authorization.get("verification_uri_complete")

    print("\nTo sign in, open this URL in any browser — on this machine or another:\n",
          file=sys.stderr)
    if complete_uri:
        print(f"    {complete_uri}\n", file=sys.stderr)
        print(f"  and confirm the code:  {user_code}\n", file=sys.stderr)
    else:
        print(f"    {authorization['verification_uri']}\n", file=sys.stderr)
        print(f"  and enter the code:    {user_code}\n", file=sys.stderr)
    log(f"Waiting up to {expires_in}s for approval (polling every {interval}s)...")

    deadline = time.monotonic() + expires_in
    while True:
        time.sleep(interval)
        if time.monotonic() >= deadline:
            raise FreepodError(f"device code expired after {expires_in}s without approval")

        try:
            tokens = post_form(TOKEN_ENDPOINT, {
                "grant_type": DEVICE_GRANT,
                "client_id": client_id,
                "device_code": device_code,
                "code_verifier": verifier,
            })
        except OAuthError as exc:
            if exc.code == "authorization_pending":
                if verbose:
                    log("  ...still pending")
                continue
            if exc.code == "slow_down":
                interval += 5
                log(f"  ...server asked us to slow down; polling every {interval}s")
                continue
            if exc.code == "expired_token":
                raise FreepodError(
                    "the device code expired before it was approved — rerun to get a new one"
                ) from None
            if exc.code == "access_denied":
                raise FreepodError("authorization was denied in the browser") from None
            raise

        log("Approved.")
        return tokens


# --------------------------------------------------------------------------
# Session: token acquisition, refresh, and authenticated calls
# --------------------------------------------------------------------------


class Session:
    """Holds the tokens for one environment and knows how to renew them."""

    def __init__(self, env: str, args):
        self.env = env
        self.client_id = ENVIRONMENTS[env]["client_id"]
        self.api_base = ENVIRONMENTS[env]["api_base"]
        self.args = args
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.credential_source = "none"
        self.flow_used: str | None = None

    # -- acquisition ------------------------------------------------------

    def authenticate(self) -> None:
        """Reuse a cached refresh token when possible, else run a full login."""
        if not self.args.login:
            cached = load_refresh_token(self.env)
            if cached:
                log(f"Found a cached refresh token for '{self.env}'; refreshing.")
                self.refresh_token = cached
                if self.refresh():
                    self.credential_source = "cached refresh token"
                    return
                log("Refresh failed; falling back to a full login.")
            else:
                log(f"No cached credential for '{self.env}'.")

        self.login()
        self.credential_source = "fresh login"

    def login(self) -> None:
        flow, reason = self.choose_flow()
        log(f"Using the {flow} flow — {reason}.")
        self.flow_used = flow

        tokens = (loopback_flow(self.client_id, self.args.timeout, self.args.verbose)
                  if flow == "loopback"
                  else device_flow(self.client_id, self.args.verbose))
        self.apply(tokens)

    def choose_flow(self) -> tuple[str, str]:
        if self.args.loopback:
            return "loopback", "forced with --loopback"
        if self.args.device:
            return "device", "forced with --device"
        usable, reason = detect_browser()
        return ("loopback", reason) if usable else ("device", reason)

    def refresh(self) -> bool:
        """Exchange the refresh token for a new access token. False on failure."""
        try:
            tokens = post_form(TOKEN_ENDPOINT, {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "refresh_token": self.refresh_token,
            })
        except OAuthError as exc:
            log(f"Refresh rejected: {exc}")
            return False
        self.apply(tokens)
        return True

    def apply(self, tokens: dict) -> None:
        self.access_token = tokens["access_token"]
        # revokeRefreshToken is false on this realm, so a refresh response may
        # omit a new refresh token; keep the one we already hold in that case.
        self.refresh_token = tokens.get("refresh_token") or self.refresh_token
        store_refresh_token(self.env, self.client_id, self.refresh_token)

    # -- authenticated requests -------------------------------------------

    def get(self, path: str) -> object:
        """GET an API path, handling the 401/403 split described in the README.

        403 means the token is expired, malformed or unverifiable — refresh and
        retry once. 401 means no credential *or* an authenticated user who
        lacks access, and re-authenticating cannot fix the second case, so we
        never loop on it.
        """
        url = f"{self.api_base}{path}"
        status, body = api_get(url, self.access_token)

        if status == 403:
            log("403 — token expired or unverifiable; refreshing and retrying once.")
            if not self.refresh():
                log("Refresh failed; running a full login.")
                self.login()
                self.credential_source = "fresh login (after failed refresh)"
            else:
                self.credential_source = "refreshed token"
            status, body = api_get(url, self.access_token)

        if status == 401:
            raise FreepodError(
                f"401 from {url} — no credential, or your account lacks access to "
                f"this environment.\n"
                f"  On dev this is most often group membership: dev.freepod.eu "
                f"requires membership of the 'freepod-dev' Keycloak group.\n"
                f"  Re-authenticating will succeed and change nothing — check the "
                f"group first.")
        if status == 403:
            raise FreepodError(
                f"403 from {url} even after refreshing — the token is still not "
                f"verifiable. Try --login to re-authenticate from scratch.")
        if status != 200:
            raise FreepodError(f"HTTP {status} from {url}: {body!r}")

        return body


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def print_table(rows: list[dict], columns: list[tuple[str, str]]) -> None:
    """Render `rows` as an aligned table. `columns` is [(key, heading), ...]."""
    cells = [[str(row.get(key, "") if row.get(key) is not None else "")
              for key, _ in columns] for row in rows]
    widths = [len(heading) for _, heading in columns]
    for line in cells:
        widths = [max(width, len(value)) for width, value in zip(widths, line)]

    header = "  ".join(heading.upper().ljust(width)
                       for (_, heading), width in zip(columns, widths))
    print(header.rstrip())
    print("  ".join("-" * width for width in widths))
    for line in cells:
        print("  ".join(value.ljust(width)
                        for value, width in zip(line, widths)).rstrip())


def print_claims(access_token: str) -> None:
    claims = decode_claims(access_token)
    if not claims:
        log("  (could not decode the access token payload)")
        return
    log("  Access token claims (unverified, for display only):")
    for name in ("iss", "azp", "aud", "sub", "email", "preferred_username",
                 "groups", "scope"):
        if name in claims:
            log(f"    {name:20} {claims[name]}")
    for name in ("iat", "exp"):
        if name in claims:
            when = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(claims[name]))
            log(f"    {name:20} {claims[name]} ({when})")
    if "exp" in claims:
        log(f"    {'expires in':20} {int(claims['exp'] - time.time())}s")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freepod_cli.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Authenticate against Freepod with OAuth2 and list your deployments.",
        epilog=(
            "Flows:\n"
            "  loopback  authorization code + PKCE via a listener on 127.0.0.1;\n"
            "            needs a browser on this machine.\n"
            "  device    device authorization grant; approve on any other device.\n"
            "The flow is auto-detected unless --loopback or --device is given.\n\n"
            "A token carries full account authority — there is no scope narrowing.\n"
            "Revoke sessions in the Keycloak account console (Applications ->\n"
            "offline sessions)."
        ),
    )
    parser.add_argument("--env", choices=sorted(ENVIRONMENTS), default="dev",
                        help="target environment (default: dev)")
    flow = parser.add_mutually_exclusive_group()
    flow.add_argument("--loopback", action="store_true",
                      help="force the loopback + PKCE browser flow")
    flow.add_argument("--device", action="store_true",
                      help="force the device authorization grant")
    parser.add_argument("--login", action="store_true",
                        help="ignore any cached token and re-authenticate")
    parser.add_argument("--logout", action="store_true",
                        help="discard the cached token for --env and exit")
    parser.add_argument("--json", action="store_true",
                        help="print raw JSON instead of a table")
    parser.add_argument("--verbose", action="store_true",
                        help="show token claims and extra progress detail")
    parser.add_argument("--timeout", type=int, default=300, metavar="SECONDS",
                        help="how long the loopback listener waits (default: 300)")
    return parser


def run(args) -> int:
    if args.logout:
        if forget_environment(args.env):
            log(f"Discarded the cached token for '{args.env}' from {cache_path()}.")
        else:
            log(f"No cached token for '{args.env}' in {cache_path()}.")
        log("Note: this only forgets the local copy. To revoke the session "
            "server-side, use the Keycloak account console "
            "(Applications -> offline sessions).")
        return 0

    session = Session(args.env, args)
    log(f"Environment '{args.env}': client_id={session.client_id} "
        f"api={session.api_base}")
    session.authenticate()

    me = session.get("/api/me")
    if not isinstance(me, dict) or "id" not in me:
        raise FreepodError(f"unexpected /api/me response: {me!r}")

    log("")
    log(f"Authenticated as {me.get('email')} "
        f"(user id {me.get('id')}"
        f"{', admin' if me.get('is_admin') else ''})")
    log(f"  flow       : {session.flow_used or 'none — reused a cached token'}")
    log(f"  credential : {session.credential_source}")
    if args.verbose:
        print_claims(session.access_token)
    log("")

    deployments = session.get(f"/api/users/{me['id']}/deployments")
    if not isinstance(deployments, list):
        raise FreepodError(f"unexpected deployments response: {deployments!r}")

    if args.json:
        print(json.dumps({"me": me, "deployments": deployments}, indent=2))
        return 0

    if not deployments:
        print("No deployments.")
        return 0

    print_table(deployments, [("name", "name"), ("hostname", "hostname"),
                              ("status", "status"), ("id", "id")])
    count = len(deployments)
    print(f"\n{count} deployment{'' if count == 1 else 's'}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except FreepodError as exc:
        log(f"\nerror: {exc}")
        return 1
    except KeyboardInterrupt:
        log("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
