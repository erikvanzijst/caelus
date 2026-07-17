"""SPIKE — Google Photos → Immich migration feasibility probe.

Throwaway code. It exists to answer two questions before we design the real
migration flow:

  1. Can freepod's *server* download Takeout files from a user's Drive using
     only an offline refresh token (no live browser session)?
  2. When the user picks the ``/Takeout/`` *folder* in the Google Picker under
     the non-restricted ``drive.file`` scope, does that grant recursive access
     to the folder's *children* (so we can list + download each chunk), or only
     to the folder object itself?

The ``/probe`` endpoint answers both at once: it mints a fresh access token from
the stored refresh token and uses *only* that to read the picked folder.

NOT production code: the refresh token lives in a single in-memory slot, so this
supports exactly one connected account at a time and forgets it on restart. The
real implementation persists per-user refresh tokens (encrypted) in the DB.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["gphotos-spike"], prefix="/spike/google")

TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"

# SPIKE ONLY: single-slot, in-memory refresh-token store. See module docstring.
_STORE: dict[str, str] = {}


class OAuthExchange(BaseModel):
    code: str
    # For the GIS popup code flow the exchange uses the literal "postmessage".
    redirect_uri: str = "postmessage"


class ExchangeResult(BaseModel):
    access_token: str
    expires_in: int
    # False means Google withheld a refresh token (usually because the user
    # previously consented and we didn't force prompt=consent + access_type
    # offline). The probe step needs this to be True.
    has_refresh_token: bool


class Probe(BaseModel):
    folder_id: str


@router.post("/oauth", response_model=ExchangeResult)
async def exchange_code(body: OAuthExchange) -> ExchangeResult:
    """Exchange the browser's auth code for tokens; stash the refresh token."""
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        raise HTTPException(500, "CAELUS_GOOGLE_CLIENT_ID / _SECRET not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "code": body.code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": body.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(400, f"token exchange failed: {resp.text}")
    tok = resp.json()
    refresh = tok.get("refresh_token")
    if refresh:
        _STORE["refresh_token"] = refresh
    return ExchangeResult(
        access_token=tok["access_token"],
        expires_in=tok.get("expires_in", 0),
        has_refresh_token=bool(refresh),
    )


async def _access_token_from_refresh() -> str:
    """Mint a fresh access token from the stored refresh token — the exact
    mechanism freepod's poller would use days after the user closed the tab."""
    s = get_settings()
    refresh = _STORE.get("refresh_token")
    if not refresh:
        raise HTTPException(400, "no refresh token stored — run the /oauth step first")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "refresh_token": refresh,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(400, f"refresh failed: {resp.text}")
    return resp.json()["access_token"]


@router.post("/probe")
async def probe(body: Probe) -> dict:
    """Using ONLY a refresh-token-minted access token, try to (a) read the
    picked folder, (b) list its children, (c) download the first child's bytes.
    The JSON result tells us whether the whole server-side design is viable."""
    token = await _access_token_from_refresh()
    headers = {"Authorization": f"Bearer {token}"}
    out: dict = {"note": "all calls below used a server-side refresh token, not the browser token"}

    async with httpx.AsyncClient(timeout=60) as client:
        # (a) Direct access to the folder object.
        f = await client.get(
            f"{DRIVE_FILES}/{body.folder_id}",
            params={"fields": "id,name,mimeType"},
            headers=headers,
        )
        out["folder_get_status"] = f.status_code
        out["folder"] = f.json() if f.status_code == 200 else f.text

        # (b) Recursive access: can we enumerate the folder's children?
        listing = await client.get(
            DRIVE_FILES,
            params={
                "q": f"'{body.folder_id}' in parents and trashed=false",
                "fields": "files(id,name,size,mimeType)",
                "pageSize": 50,
            },
            headers=headers,
        )
        out["list_status"] = listing.status_code
        children = listing.json().get("files", []) if listing.status_code == 200 else []
        out["children_count"] = len(children)
        out["children"] = children
        out["list_error"] = None if listing.status_code == 200 else listing.text

        # (c) Can we actually pull bytes of a child (first 1 KiB is enough)?
        if children:
            cid = children[0]["id"]
            d = await client.get(
                f"{DRIVE_FILES}/{cid}",
                params={"alt": "media"},
                headers={**headers, "Range": "bytes=0-1023"},
            )
            out["download_status"] = d.status_code
            out["download_bytes"] = len(d.content) if d.status_code in (200, 206) else 0
            out["download_error"] = None if d.status_code in (200, 206) else d.text

    # The verdict the spike exists to produce.
    out["VERDICT_recursive_folder_access"] = bool(
        out.get("children_count") and out.get("download_status") in (200, 206)
    )
    return out
