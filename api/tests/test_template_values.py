from __future__ import annotations

import pytest

from app.services.errors import IntegrityException
from app.services.template_values import (
    bytes_to_k8s_size,
    deep_merge,
    merge_values_scoped,
    validate_user_values,
)


def test_validate_user_values_rejects_non_object_payload() -> None:
    with pytest.raises(IntegrityException):
        validate_user_values(["not", "object"], {"type": "object", "properties": {"user": {"type": "object"}}})


def test_validate_user_values_allows_empty_when_user_scope_missing() -> None:
    validate_user_values({}, {"type": "object", "properties": {"system": {"type": "object"}}})


def test_merge_values_scoped_user_only_and_system_wins() -> None:
    defaults = {"image": {"tag": "1.0"}, "user": {"message": "hello", "nested": {"a": 1}}, "replicas": 1}
    user_delta = {"user": {"message": "custom", "nested": {"b": 2}}}
    system_overrides = {"replicas": 3, "user": {"message": "system"}}

    merged = merge_values_scoped(defaults, user_delta, system_overrides)
    assert merged == {
        "image": {"tag": "1.0"},
        "user": {"message": "system", "nested": {"a": 1, "b": 2}},
        "replicas": 3,
    }


def test_deep_merge_replaces_arrays_and_scalars() -> None:
    base = {"arr": [1, 2], "obj": {"x": 1}, "s": "a"}
    override = {"arr": [3], "obj": {"y": 2}, "s": "b"}
    assert deep_merge(base, override) == {"arr": [3], "obj": {"x": 1, "y": 2}, "s": "b"}


@pytest.mark.parametrize(
    "input_bytes,expected",
    [
        (0, "0"),
        (1024, "1Ki"),
        (1048576, "1Mi"),
        (536870912, "512Mi"),
        (1073741824, "1Gi"),
        (10737418240, "10Gi"),
        (1099511627776, "1Ti"),
        (500000000, "500000000"),
    ],
)
def test_bytes_to_k8s_size(input_bytes: int, expected: str) -> None:
    assert bytes_to_k8s_size(input_bytes) == expected
