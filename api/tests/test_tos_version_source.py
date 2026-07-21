"""Guard: the API's current ToS version must match the ToS markdown.

`settings.current_tos_version` is a code-side release constant; the canonical ToS
text (and its `**Effective date:**`) is UI-owned. This test binds the two so the
constant cannot silently drift from the document it represents — bumping one
without the other fails the build.

It deliberately reaches across subprojects into `ui/` (an intentional, loud
coupling) and reads the canonical file, not the `legal/` symlink, to avoid
symlink-following surprises off Linux.
"""
import re
from pathlib import Path

from app.config import get_settings

# api/tests/ -> api/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
TOS_MARKDOWN = REPO_ROOT / "ui" / "src" / "content" / "legal" / "terms-of-service.md"

# Same shape the UI parser uses in ui/src/content/legal/index.ts.
_EFFECTIVE_DATE = re.compile(r"Effective date:\**\s*(\d{4}-\d{2}-\d{2})")


def test_current_tos_version_matches_markdown():
    assert TOS_MARKDOWN.is_file(), f"ToS markdown not found at {TOS_MARKDOWN}"
    match = _EFFECTIVE_DATE.search(TOS_MARKDOWN.read_text(encoding="utf-8"))
    assert match, f"no parseable '**Effective date:**' in {TOS_MARKDOWN}"
    assert get_settings().current_tos_version == match.group(1), (
        "settings.current_tos_version is out of sync with the ToS markdown's "
        "Effective date; bump both together when the terms change."
    )
