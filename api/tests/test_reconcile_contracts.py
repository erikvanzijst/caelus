from app.services import reconcile_constants as c
from app.services.reconcile_naming import (
    BASE_MAX_LEN,
    MAX_DNS_LABEL_LEN,
    generate_deployment_uid,
    is_valid_dns_label,
    namespace_name_for_deployment_uid,
    release_name_for_deployment_uid,
    slugify_token,
)


def test_deployment_statuses_are_complete_and_unique() -> None:
    expected = {
        "pending",
        "provisioning",
        "ready",
        "upgrading",
        "deleting",
        "deleted",
        "error",
    }
    assert set(c.DEPLOYMENT_STATUSES) == expected
    assert len(c.DEPLOYMENT_STATUSES) == len(set(c.DEPLOYMENT_STATUSES))


def test_job_statuses_and_reasons_are_complete_and_unique() -> None:
    assert set(c.JOB_STATUSES) == {"queued", "running", "done", "failed"}
    assert set(c.JOB_REASONS) == {"create", "update", "delete", "drift", "retry"}
    assert len(c.JOB_STATUSES) == len(set(c.JOB_STATUSES))
    assert len(c.JOB_REASONS) == len(set(c.JOB_REASONS))


def test_generate_deployment_uid_format_and_length() -> None:
    uid = generate_deployment_uid(
        "Hello Static Product",
        "Alice.Smith+dev@example.com",
        suffix="abc123",
    )
    assert uid.endswith("-abc123")
    assert len(uid) <= MAX_DNS_LABEL_LEN
    assert is_valid_dns_label(uid)


def test_generate_deployment_uid_truncates_base_safely() -> None:
    long_product = "p" * 200
    long_user = "user." + ("x" * 200) + "@example.com"
    uid = generate_deployment_uid(long_product, long_user, suffix="zzzzzz")
    base, suffix = uid.rsplit("-", 1)
    assert suffix == "zzzzzz"
    assert len(base) <= BASE_MAX_LEN
    assert len(uid) <= MAX_DNS_LABEL_LEN
    assert is_valid_dns_label(uid)


def test_slugify_and_fallback_behavior() -> None:
    assert slugify_token("A__B.C") == "a-b-c"
    uid = generate_deployment_uid("!!!", "%%%@@@", suffix="000000")
    assert uid == "dep-000000"
    assert is_valid_dns_label(uid)


def test_namespace_and_release_name_match_uid_contract() -> None:
    uid = "hello-static-user-example-com-1a2b3c"
    assert namespace_name_for_deployment_uid(uid) == uid
    assert release_name_for_deployment_uid(uid) == uid

