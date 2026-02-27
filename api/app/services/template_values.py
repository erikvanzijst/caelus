from __future__ import annotations

from copy import deepcopy
from typing import Any

from jsonschema import ValidationError
from jsonschema import validate as jsonschema_validate

from app.services.errors import IntegrityException


def deep_merge(base: Any, override: Any) -> Any:
    """Deep-merge two JSON-like values, recursively merging object keys."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged: dict[str, Any] = {k: deepcopy(v) for k, v in base.items()}
        for key, value in override.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(override)


def validate_user_values(
    user_values_json: dict[str, Any],
    values_schema_json: dict[str, Any] | None,
) -> None:
    """Validate user-scoped values against `properties.user` schema."""
    if not values_schema_json and not user_values_json:
        return
    elif user_values_json and not values_schema_json:
        raise IntegrityException("user_values_json not supported on this product template")

    try:
        jsonschema_validate(instance=user_values_json, schema=values_schema_json)
    except ValidationError as exc:
        raise IntegrityException(f"user_values_json is invalid: {exc.message}") from exc


def merge_values_scoped(
    defaults: dict[str, Any] | None,
    user_scope_delta: dict[str, Any] | None,
    system_overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge defaults + user scope + system overrides with deterministic precedence."""
    if defaults is not None and not isinstance(defaults, dict):
        raise IntegrityException("defaults must be an object")
    if user_scope_delta is not None and not isinstance(user_scope_delta, dict):
        raise IntegrityException("user_scope_delta must be an object")
    if system_overrides is not None and not isinstance(system_overrides, dict):
        raise IntegrityException("system_overrides must be an object")

    merged = deepcopy(defaults) if defaults is not None else {}
    if user_scope_delta is not None:
        merged = deep_merge(merged, deepcopy(user_scope_delta))
    if system_overrides is not None:
        merged = deep_merge(merged, deepcopy(system_overrides))
    return merged


def validate_merged_values(
    merged_values: dict[str, Any],
    values_schema_json: dict[str, Any] | None,
) -> None:
    """Validate final merged values against full template schema."""
    if not isinstance(merged_values, dict):
        raise IntegrityException("merged_values must be an object")
    if values_schema_json is None:
        return
    if not isinstance(values_schema_json, dict):
        raise IntegrityException("values_schema_json must be an object")
    try:
        jsonschema_validate(instance=merged_values, schema=values_schema_json)
    except ValidationError as exc:
        raise IntegrityException(f"merged values are invalid: {exc.message}") from exc
