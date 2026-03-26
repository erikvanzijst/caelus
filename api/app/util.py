from pathlib import Path
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
