#!/usr/bin/env python3
"""Seed end-user accounts into a Keycloak realm via the admin REST API.

Written for the `master` -> `freepod` realm migration (see the OpenSpec change
`migrate-keycloak-freepod-realm`, task 4.1). Reads a JSON array of users and
creates each one, enforcing the shape the migration requires:

  * emailVerified: true   - all six source accounts are verified, and with
                            verifyEmail=true on the realm, seeding them
                            unverified would add a VERIFY_EMAIL round trip
                            before anyone could even reset a password.
  * enabled: true
  * requiredActions: []   - deliberately NOT ["UPDATE_PASSWORD"]. Required
                            actions run *after* the credential is validated, so
                            a credential-less account could never reach one and
                            would simply be locked out.
  * no role mappings      - realmRoles/clientRoles/groups are stripped. Two
                            source accounts hold the `master` realm `admin`
                            role; an end-user account holding instance-wide
                            admin rights is the privilege concern this
                            migration exists to resolve.

Password-hash carry-over is optional and per user: include a `credentials`
array on a user and it is passed through untouched. Because the admin API
redacts secretData on read, a carried credential cannot be verified by
inspection - the account must actually be signed into. Carry over ONE account
first, confirm it, and only then do the rest (task 4.5).

Writes go through the admin API rather than direct SQL on purpose: Keycloak
runs a local Infinispan `users` cache, so rows written straight to Postgres are
not reliably visible to the running server.

Usage:
    export KEYCLOAK_ADMIN_PASSWORD=...
    scripts/seed-keycloak-users.py --users var/seed-users.json --dry-run
    scripts/seed-keycloak-users.py --users var/seed-users.json

Input file: a JSON array of objects. Only these keys are read; anything else is
ignored with a warning.

    [
      {
        "username": "fred",
        "email": "fred@example.com",
        "firstName": "Fred",
        "lastName": "Veiligheidspet",
        "createdTimestamp": 1782727594955,
        "credentials": [ { ... optional, passed through ... } ]
      }
    ]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Keys copied from the input file onto the created user. Everything else is
# dropped - notably id, realmRoles, clientRoles and groups.
CARRIED_KEYS = (
    "username",
    "email",
    "firstName",
    "lastName",
    "createdTimestamp",
)

# Keys we set ourselves regardless of the input. Recognized, so they are not
# reported as unknown, but the input's value is never trusted.
FORCED_KEYS = ("enabled", "emailVerified")

# Keys that must never reach Keycloak, called out individually so the warning
# explains itself rather than silently dropping something meaningful.
REFUSED_KEYS = {
    "id": "server-assigned; a new id is minted in the target realm",
    "realmRoles": "role mappings are deliberately not migrated",
    "clientRoles": "role mappings are deliberately not migrated",
    "groups": "group membership is assigned separately, after seeding",
    "requiredActions": "forced empty; see the module docstring",
    "federatedIdentities": "no source account has one",
}


class AdminApi:
    def __init__(self, url: str, realm: str, admin_user: str, admin_password: str):
        self.url = url.rstrip("/")
        self.realm = realm
        self._admin_user = admin_user
        self._admin_password = admin_password
        self._token: str | None = None

    def _mint_token(self) -> str:
        """Admin access tokens live ~60s, so mint one per call rather than cache."""
        body = urllib.parse.urlencode(
            {
                "client_id": "admin-cli",
                "username": self._admin_user,
                "password": self._admin_password,
                "grant_type": "password",
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.url}/realms/master/protocol/openid-connect/token", data=body
        )
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)["access_token"]

    def request(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self._mint_token()}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{self.url}/admin/realms/{self.realm}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        with urllib.request.urlopen(req) as resp:
            payload = resp.read().decode()
            return resp.status, resp.headers.get("Location"), payload

    def find_user(self, username: str):
        q = urllib.parse.urlencode({"username": username, "exact": "true"})
        _, _, payload = self.request("GET", f"/users?{q}")
        matches = json.loads(payload)
        return matches[0] if matches else None


def normalize(raw: dict) -> tuple[dict, list[str]]:
    """Reduce an input record to the exact payload we are willing to POST."""
    warnings = []
    user = {k: raw[k] for k in CARRIED_KEYS if raw.get(k) is not None}

    for key, why in REFUSED_KEYS.items():
        if raw.get(key):
            warnings.append(f"dropped {key!r} ({why})")

    known = set(CARRIED_KEYS) | set(REFUSED_KEYS) | set(FORCED_KEYS) | {"credentials"}
    for key in raw:
        if key not in known:
            warnings.append(f"ignored unrecognized key {key!r}")

        # An input that disagrees with what we force is worth surfacing: it
        # means the source account was disabled or unverified, which changes
        # what seeding it actually does.
    for key in FORCED_KEYS:
        if key in raw and raw[key] is not True:
            warnings.append(f"input had {key}={raw[key]!r}; forcing True")

    # Non-negotiable, regardless of what the input file says.
    user["enabled"] = True
    user["emailVerified"] = True
    user["requiredActions"] = []

    creds = raw.get("credentials")
    if creds:
        user["credentials"] = creds

    return user, warnings


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--users", required=True, help="JSON file: array of user objects")
    p.add_argument("--url", default="https://keycloak.freepod.eu", help="Keycloak base URL")
    p.add_argument("--realm", default="freepod", help="target realm (default: freepod)")
    p.add_argument("--admin-user", default="admin")
    p.add_argument(
        "--admin-password",
        default=os.environ.get("KEYCLOAK_ADMIN_PASSWORD"),
        help="defaults to $KEYCLOAK_ADMIN_PASSWORD",
    )
    p.add_argument("--dry-run", action="store_true", help="print payloads, change nothing")
    p.add_argument(
        "--only",
        action="append",
        metavar="USERNAME",
        help="seed only these usernames (repeatable). Use this for the one-account "
        "credential gate rather than hand-editing the input file.",
    )
    args = p.parse_args()

    if not args.admin_password and not args.dry_run:
        print("error: no admin password (--admin-password or $KEYCLOAK_ADMIN_PASSWORD)", file=sys.stderr)
        return 2

    with open(args.users) as fh:
        records = json.load(fh)
    if not isinstance(records, list):
        print(f"error: {args.users} must contain a JSON array", file=sys.stderr)
        return 2

    if args.only:
        wanted = set(args.only)
        records = [r for r in records if r.get("username") in wanted]
        missing = wanted - {r.get("username") for r in records}
        if missing:
            print(f"error: --only named unknown users: {sorted(missing)}", file=sys.stderr)
            return 2

    api = AdminApi(args.url, args.realm, args.admin_user, args.admin_password or "")
    failures = 0

    for raw in records:
        username = raw.get("username")
        if not username:
            print("skip: record has no username")
            failures += 1
            continue

        user, warnings = normalize(raw)
        has_creds = "credentials" in user
        label = "with credential" if has_creds else "credential-less"
        print(f"\n{username}  ({label})")
        for w in warnings:
            print(f"    warn: {w}")

        if args.dry_run:
            redacted = dict(user)
            if has_creds:
                redacted["credentials"] = f"<{len(user['credentials'])} credential(s), redacted>"
            print("    would POST:", json.dumps(redacted, sort_keys=True))
            continue

        if api.find_user(username):
            print(f"    skip: already exists in realm {args.realm!r}")
            continue

        try:
            status, location, _ = api.request("POST", "/users", user)
            uid = location.rstrip("/").split("/")[-1] if location else "?"
            print(f"    created ({status}) id={uid}")
            if has_creds:
                print("    NOTE: the admin API redacts secretData on read, so this")
                print("          credential can only be verified by signing in.")
        except urllib.error.HTTPError as e:
            print(f"    FAILED {e.code}: {e.read().decode()[:300]}")
            failures += 1

    print()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
