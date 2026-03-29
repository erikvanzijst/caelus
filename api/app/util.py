from pathlib import Path
from typing import Any
from urllib.parse import urlunsplit, urlencode, parse_qs, urlsplit


def amend_url(url: str, path: str = None, query: dict[str, str] | None = None, fragment: str = None) -> str:
    """
    Amends a URL with a new path, query parameters, or fragment.

    The original URL's query parameters are merged with the new ones provided.
    If a component (path, query, fragment) is not provided, the original value is kept.

    :param url: The original URL string.
    :param path: An optional replacement path.
    :param query: An optional dictionary of query parameters to add or update.
    :param fragment: An optional replacement fragment.
    :return: The amended URL string.
    """
    return str((lambda parts:
                urlunsplit(parts
                           ._replace(path=parts.path if path is None else str(Path(parts.path) / path))
                           ._replace(query=urlencode(parse_qs(parts.query, keep_blank_values=True) | (query or {}),
                                                     doseq=True))
                           ._replace(fragment=parts.fragment if fragment is None else fragment)
                           ))
               (urlsplit(url)))


def value_for_path(data: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    """Read a value from a nested dict/list structure at the given path.

    Path segments are dict keys, except ``"*"`` which descends into the
    first element of a list.
    """
    current: Any = data or {}
    for key in path:
        if key == "*":
            if isinstance(current, list) and current:
                current = current[0]
                continue
            return None
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def set_value_at_path(
    data: dict[str, Any] | None, path: tuple[str, ...], value: Any
) -> None:
    """Write *value* into a nested dict/list structure at the given path."""
    if not data or not path:
        return
    current: Any = data
    for key in path[:-1]:
        if key == "*":
            if isinstance(current, list) and current:
                current = current[0]
                continue
            return
        if not isinstance(current, dict) or key not in current:
            return
        current = current[key]
    last = path[-1]
    if last == "*":
        if isinstance(current, list) and current:
            current[0] = value
    elif isinstance(current, dict):
        current[last] = value
