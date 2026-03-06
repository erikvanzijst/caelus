from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache


@lru_cache
def get_static_path() -> Path:
    """Get the static files root path.

    Defaults to ./static in development, should be set to /var/static in production.
    """
    static_path = os.environ.get("STATIC_PATH")
    if static_path:
        return Path(static_path)
    return Path(__file__).parent.parent / "static"


def get_static_url_base() -> str:
    """Get the base URL for static file serving."""
    return "/api/static"
