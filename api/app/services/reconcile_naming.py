from __future__ import annotations

import re
import secrets

DNS_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
SUFFIX_RE = re.compile(r"^[0-9a-z]{6}$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_HYPHEN_RUN_RE = re.compile(r"-+")

MAX_DNS_LABEL_LEN = 63
RANDOM_SUFFIX_LEN = 6
BASE_MAX_LEN = MAX_DNS_LABEL_LEN - (RANDOM_SUFFIX_LEN + 1)

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def slugify_token(value: str) -> str:
    lowered = value.lower()
    replaced = _NON_ALNUM_RE.sub("-", lowered)
    collapsed = _HYPHEN_RUN_RE.sub("-", replaced)
    return collapsed.strip("-")


def is_valid_dns_label(value: str) -> bool:
    return bool(DNS_LABEL_RE.fullmatch(value))


def generate_suffix6() -> str:
    return "".join(secrets.choice(_BASE36) for _ in range(RANDOM_SUFFIX_LEN))


def _trim_base_for_suffix(base: str) -> str:
    trimmed = base[:BASE_MAX_LEN].strip("-")
    if trimmed:
        return trimmed
    return "dep"


def _normalize_suffix(suffix: str) -> str:
    if not SUFFIX_RE.fullmatch(suffix):
        raise ValueError("suffix must match [0-9a-z]{6}")
    return suffix


def generate_deployment_uid(product_name: str, user_email: str, *, suffix: str | None = None) -> str:
    product_slug = slugify_token(product_name)
    user_slug = slugify_token(user_email)
    parts = [part for part in (product_slug, user_slug) if part]
    base = "-".join(parts) if parts else "dep"
    base = _trim_base_for_suffix(base)

    candidate_suffix = _normalize_suffix(suffix) if suffix is not None else generate_suffix6()
    deployment_uid = f"{base}-{candidate_suffix}"

    if len(deployment_uid) > MAX_DNS_LABEL_LEN or not is_valid_dns_label(deployment_uid):
        raise ValueError("generated deployment_uid is not a valid DNS label")
    return deployment_uid


def namespace_name_for_deployment_uid(deployment_uid: str) -> str:
    if not is_valid_dns_label(deployment_uid):
        raise ValueError("deployment_uid is not a valid DNS label")
    return deployment_uid


def release_name_for_deployment_uid(deployment_uid: str) -> str:
    if not is_valid_dns_label(deployment_uid):
        raise ValueError("deployment_uid is not a valid DNS label")
    return deployment_uid

