from __future__ import annotations

import re
import secrets

DNS_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
SUFFIX6_RE = re.compile(r"^[0-9a-z]{6}$")
SUFFIX9_RE = re.compile(r"^[0-9a-z]{9}$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_HYPHEN_RUN_RE = re.compile(r"-+")

MAX_DNS_LABEL_LEN = 63

# --- Name (Helm release name) constants ---
# Formula: "{slugify(product_name)[:20]}-{random6}"
# Max: 20 + 1 + 6 = 27 chars, leaving 36 chars headroom for chart suffixes
# and K8s controller-revision-hash labels within the 63-char DNS limit.
NAME_SUFFIX_LEN = 6
MAX_NAME_LEN = 27
NAME_BASE_MAX_LEN = MAX_NAME_LEN - (NAME_SUFFIX_LEN + 1)  # 20

# --- Namespace constants ---
# Formula: "{slugify(product)[:20]}-{slugify(email_local_part)[:10]}-{random9}"
# Max: 20 + 1 + 10 + 1 + 9 = 41 chars (well under the 63-char DNS label limit).
NS_SUFFIX_LEN = 9
NS_PRODUCT_MAX_LEN = 20
NS_EMAIL_MAX_LEN = 10
MAX_NAMESPACE_LEN = NS_PRODUCT_MAX_LEN + 1 + NS_EMAIL_MAX_LEN + 1 + NS_SUFFIX_LEN  # 41

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def slugify_token(value: str) -> str:
    lowered = value.lower()
    replaced = _NON_ALNUM_RE.sub("-", lowered)
    collapsed = _HYPHEN_RUN_RE.sub("-", replaced)
    return collapsed.strip("-")


def is_valid_dns_label(value: str) -> bool:
    return bool(DNS_LABEL_RE.fullmatch(value))


def generate_suffix6() -> str:
    return "".join(secrets.choice(_BASE36) for _ in range(NAME_SUFFIX_LEN))


def generate_suffix9() -> str:
    return "".join(secrets.choice(_BASE36) for _ in range(NS_SUFFIX_LEN))


def _trim_base(base: str, max_len: int) -> str:
    trimmed = base[:max_len].strip("-")
    if trimmed:
        return trimmed
    return "dep"


def _normalize_suffix6(suffix: str) -> str:
    if not SUFFIX6_RE.fullmatch(suffix):
        raise ValueError("suffix must match [0-9a-z]{6}")
    return suffix


def _normalize_suffix9(suffix: str) -> str:
    if not SUFFIX9_RE.fullmatch(suffix):
        raise ValueError("suffix must match [0-9a-z]{9}")
    return suffix


def generate_deployment_name(product_name: str, *, suffix: str | None = None) -> str:
    base = slugify_token(product_name)
    base = _trim_base(base, NAME_BASE_MAX_LEN)

    candidate_suffix = _normalize_suffix6(suffix) if suffix is not None else generate_suffix6()
    name = f"{base}-{candidate_suffix}"

    if len(name) > MAX_NAME_LEN or not is_valid_dns_label(name):
        raise ValueError("generated deployment name is not a valid DNS label")
    return name


def generate_deployment_namespace(
    product_name: str,
    user_email: str,
    *,
    suffix: str | None = None,
) -> str:
    product = _trim_base(slugify_token(product_name), NS_PRODUCT_MAX_LEN)
    local_part = _trim_base(
        slugify_token(user_email.split("@", 1)[0]), NS_EMAIL_MAX_LEN
    )

    candidate_suffix = _normalize_suffix9(suffix) if suffix is not None else generate_suffix9()
    namespace = f"{product}-{local_part}-{candidate_suffix}"

    if len(namespace) > MAX_NAMESPACE_LEN or not is_valid_dns_label(namespace):
        raise ValueError("generated deployment namespace is not a valid DNS label")
    return namespace
