from __future__ import annotations

import pytest

from app.services.errors import IntegrityException
from app.services.template_values import (
    deep_merge,
    extract_user_subschema,
    merge_values_scoped,
    validate_merged_values,
    validate_user_values,
)


def test_extract_user_subschema_returns_user_schema_when_present() -> None:
    schema = {"type": "object", "properties": {"user": {"type": "object", "properties": {"a": {"type": "string"}}}}}
    assert extract_user_subschema(schema) == {"type": "object", "properties": {"a": {"type": "string"}}}


def test_validate_user_values_rejects_non_object_payload() -> None:
    with pytest.raises(IntegrityException):
        validate_user_values(["not", "object"], {"type": "object", "properties": {"user": {"type": "object"}}})


def test_validate_user_values_rejects_non_empty_when_user_scope_missing() -> None:
    with pytest.raises(IntegrityException):
        validate_user_values({"x": 1}, {"type": "object", "properties": {"system": {"type": "object"}}})


def test_validate_user_values_allows_empty_when_user_scope_missing() -> None:
    validate_user_values({}, {"type": "object", "properties": {"system": {"type": "object"}}})


def test_merge_values_scoped_user_only_and_system_wins() -> None:
    defaults = {"image": {"tag": "1.0"}, "user": {"message": "hello", "nested": {"a": 1}}, "replicas": 1}
    user_delta = {"message": "custom", "nested": {"b": 2}}
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


def test_validate_merged_values_rejects_unknown_keys() -> None:
    schema = {
        "type": "object",
        "properties": {"user": {"type": "object", "properties": {"message": {"type": "string"}}, "additionalProperties": False}},
        "additionalProperties": False,
    }
    with pytest.raises(IntegrityException):
        validate_merged_values({"user": {"message": "x", "unknown": True}}, schema)


def test_validate_merged_values_accepts_nested_and_arrays() -> None:
    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "integer"}},
                    "nested": {"type": "object", "properties": {"flag": {"type": "boolean"}}, "required": ["flag"]},
                },
                "required": ["items", "nested"],
                "additionalProperties": False,
            }
        },
        "required": ["user"],
        "additionalProperties": False,
    }
    validate_merged_values({"user": {"items": [1, 2], "nested": {"flag": True}}}, schema)
