"""The builder container's entrypoint: archive handling and result reporting.

`products/custom/builder/build.py` is the one place in this codebase that
parses attacker-controlled input — a tenant's project archive — so its
extraction path is tested here rather than only exercised by a real build.
Everything in this file runs offline: no cluster, no registry, no object store.

The script lives outside `api/`, but `cd api && pytest` is the repo's only test
command, so this deliberately reaches across into `products/` (the same
intentional coupling as `test_tos_version_source.py`). A test that the standard
command does not run is a test that does not exist.
"""

from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import urllib.error
from pathlib import Path

import pytest

# api/tests/ -> api/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "products" / "custom" / "builder" / "build.py"


def _load_build_module():
    assert BUILD_SCRIPT.is_file(), f"builder entrypoint not found at {BUILD_SCRIPT}"
    spec = importlib.util.spec_from_file_location("builder_build", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load_build_module()


# ---------------------------------------------------------------------------
# Archive construction helpers
# ---------------------------------------------------------------------------


def _regular(name: str, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.REGTYPE
    info.size = size
    return info


def _link(name: str, target: str, *, symbolic: bool = True) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE if symbolic else tarfile.LNKTYPE
    info.linkname = target
    return info


def _tarball(entries: list[tuple[tarfile.TarInfo, bytes | None]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for info, payload in entries:
            tar.addfile(info, io.BytesIO(payload) if payload is not None else None)
    return buffer.getvalue()


class _Source:
    """A non-seekable byte source, like an HTTP response.

    `die_after` simulates a transfer that drops part-way through, which is the
    failure the streaming design has to keep distinguishable from a malformed
    archive.
    """

    def __init__(self, data: bytes, *, die_after: int | None = None) -> None:
        self._raw = io.BytesIO(data)
        self._die_after = die_after
        self._served = 0

    def read(self, size: int = -1) -> bytes:
        if self._die_after is not None and self._served >= self._die_after:
            raise OSError("connection reset by peer")
        chunk = self._raw.read(size)
        self._served += len(chunk)
        return chunk


def _extract(
    data: bytes,
    dest: Path,
    *,
    max_bytes: int = 1024 * 1024,
    max_entries: int = 1000,
    stream_limit: int = 10**9,
    die_after: int | None = None,
) -> None:
    """Extract through the same bounded-stream path production uses."""
    reader = build._BoundedReader(_Source(data, die_after=die_after), stream_limit)
    build.extract_stream(reader, dest, max_bytes=max_bytes, max_entries=max_entries)


# ---------------------------------------------------------------------------
# Hostile archives
#
# A sandbox is a containment boundary, not a reason to honor a traversal entry.
# Each case asserts both that extraction failed *and* that nothing was written
# outside the destination — the second is the property that actually matters.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,entries",
    [
        ("parent traversal", [(_regular("../escape.txt", 5), b"pwned")]),
        ("deep traversal", [(_regular("../../escape.txt", 5), b"pwned")]),
        ("traversal below a directory", [(_regular("app/../../escape.txt", 5), b"pwned")]),
        ("absolute path", [(_regular("/tmp/escape.txt", 5), b"pwned")]),
        ("symlink to an absolute path", [(_link("evil", "/etc/passwd"), None)]),
        ("symlink escaping via ..", [(_link("evil", "../../outside"), None)]),
        ("hardlink to an absolute path", [(_link("evil", "/etc/passwd", symbolic=False), None)]),
    ],
)
def test_escaping_entries_are_rejected_and_write_nothing_outside(tmp_path, label, entries):
    dest = tmp_path / "src"
    sentinel = tmp_path / "escape.txt"

    with pytest.raises(build.BuildFailure):
        _extract(_tarball(entries), dest)

    assert not sentinel.exists(), f"{label}: wrote outside the extraction directory"
    strays = [p for p in tmp_path.rglob("*") if p.is_file() and dest not in p.parents]
    assert strays == [], f"{label}: stray files {strays}"


def test_entry_count_bomb_is_rejected(tmp_path):
    entries = [(_regular(f"f{n}", 0), b"") for n in range(50)]

    with pytest.raises(build.BuildFailure, match="more than 10 entries"):
        _extract(_tarball(entries), tmp_path / "src", max_entries=10)


def test_a_single_oversized_member_is_rejected(tmp_path):
    entries = [(_regular("big", 500_000), b"\0" * 500_000)]

    with pytest.raises(build.BuildFailure, match="expands beyond"):
        _extract(_tarball(entries), tmp_path / "src", max_bytes=1024)


def test_expansion_spread_across_many_members_is_rejected(tmp_path):
    """The bound is cumulative; no single member need breach it."""
    entries = [(_regular(f"f{n}", 100_000), b"\0" * 100_000) for n in range(20)]

    with pytest.raises(build.BuildFailure, match="expands beyond"):
        _extract(_tarball(entries), tmp_path / "src", max_bytes=500_000)


def test_the_breaching_member_is_never_written(tmp_path):
    """Bounds are checked *before* each member, so the cap is not merely noticed."""
    dest = tmp_path / "src"
    entries = [
        (_regular("small.txt", 10), b"0123456789"),
        (_regular("huge.bin", 100_000), b"\0" * 100_000),
    ]

    with pytest.raises(build.BuildFailure, match="expands beyond"):
        _extract(_tarball(entries), dest, max_bytes=1000)

    assert (dest / "small.txt").is_file()
    assert not (dest / "huge.bin").exists()


def test_a_compressed_stream_far_smaller_than_its_expansion_is_still_bounded(tmp_path):
    """The compressed cap alone would not have caught this.

    Highly compressible input reaches enormous ratios, which is exactly why the
    extracted-size bound exists separately from the download bound.
    """
    entries = [(_regular(f"f{n}", 100_000), b"\0" * 100_000) for n in range(5)]
    data = _tarball(entries)
    assert len(data) < 5_000, "test archive should be tiny compared to its expansion"

    with pytest.raises(build.BuildFailure, match="expands beyond"):
        _extract(data, tmp_path / "src", max_bytes=100_000, stream_limit=10**9)


# ---------------------------------------------------------------------------
# Benign archives still work
# ---------------------------------------------------------------------------


def test_a_normal_source_tree_extracts(tmp_path):
    dest = tmp_path / "src"
    entries = [
        (_regular("app/index.js", 11), b"console.log"),
        (_regular("app/package.json", 2), b"{}"),
    ]

    _extract(_tarball(entries), dest)

    assert (dest / "app" / "index.js").read_bytes() == b"console.log"
    assert (dest / "app" / "package.json").read_bytes() == b"{}"


def test_a_relative_link_inside_the_tree_is_preserved(tmp_path):
    """The filter refuses links that *escape*, not links as such."""
    dest = tmp_path / "src"
    entries = [(_regular("app/real.txt", 2), b"hi"), (_link("app/alias.txt", "real.txt"), None)]

    _extract(_tarball(entries), dest)

    assert (dest / "app" / "alias.txt").is_symlink()


# ---------------------------------------------------------------------------
# Streaming: bounds and error attribution
#
# Extraction runs straight off the socket, so a transfer failure surfaces from
# inside tarfile. These pin that each cause keeps its own message — a user told
# "your archive is corrupt" when the download died would go looking in the
# wrong place.
# ---------------------------------------------------------------------------


def test_the_compressed_stream_is_bounded_independently(tmp_path):
    data = _tarball([(_regular("app/f", 10), b"0123456789")])

    with pytest.raises(build.BuildFailure, match="exceeds the 10 byte limit"):
        _extract(data, tmp_path / "src", stream_limit=10)


def _incompressible_tarball(members: int = 5, size: int = 20_000) -> bytes:
    """An archive large enough to span several reads of the stream.

    Random payload on purpose: a compressible one would arrive in a single
    read, and a transfer cannot die part-way through if there is only one part.
    """
    import os

    return _tarball([(_regular(f"f{n}", size), os.urandom(size)) for n in range(members)])


def test_a_dead_transfer_reads_as_a_retrieval_failure(tmp_path):
    data = _incompressible_tarball()
    assert len(data) > 32_768, "archive must be large enough to require several reads"

    with pytest.raises(build.BuildFailure, match="could not retrieve") as exc:
        _extract(data, tmp_path / "src", max_bytes=10**7, die_after=16_384)

    assert "could not extract" not in str(exc.value)


def test_a_truncated_archive_reads_as_an_extraction_failure(tmp_path):
    data = _incompressible_tarball()

    with pytest.raises(build.BuildFailure, match="could not extract") as exc:
        _extract(data[: len(data) // 2], tmp_path / "src", max_bytes=10**7)

    assert "could not retrieve" not in str(exc.value)


def test_an_empty_body_is_named_as_such(tmp_path):
    with pytest.raises(build.BuildFailure, match="empty"):
        _extract(b"", tmp_path / "src")


def test_bounded_reader_reports_what_it_has_served():
    payload = b"x" * 100
    reader = build._BoundedReader(_Source(payload), 10**9)

    assert reader.read(40) == payload[:40]
    assert reader.bytes_read == 40


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def test_an_http_error_names_the_status(monkeypatch):
    """An expired credential or a lifecycle-reaped artifact must say so."""

    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)

    monkeypatch.setattr(build.urllib.request, "urlopen", _raise)

    with pytest.raises(build.BuildFailure, match="HTTP 403"):
        with build.open_artifact("http://x", max_bytes=1024):
            pass


def test_an_unreachable_host_is_reported_as_a_retrieval_failure(monkeypatch):
    def _raise(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(build.urllib.request, "urlopen", _raise)

    with pytest.raises(build.BuildFailure, match="could not retrieve"):
        with build.open_artifact("http://x", max_bytes=1024):
            pass


# ---------------------------------------------------------------------------
# Reading the produced digest
# ---------------------------------------------------------------------------


def test_digest_is_read_from_the_metadata_file(tmp_path):
    digest = "sha256:" + "a" * 64
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"containerimage.digest": digest}))

    assert build.read_digest(path) == digest


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"containerimage.digest": ""},
        {"containerimage.digest": None},
        {"containerimage.digest": 12345},
        {"containerimage.digest": "notadigest"},
        {"containerimage.digest": "sha256:" + "a" * 63},
        {"containerimage.digest": "sha256:" + "a" * 65},
        {"containerimage.digest": "sha256:" + "A" * 64},
        {"containerimage.digest": "sha256:" + "z" * 64},
    ],
)
def test_a_missing_or_malformed_digest_fails_the_build(tmp_path, metadata):
    """A success reporting no usable image is a failed build, not a success."""
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(metadata))

    with pytest.raises(build.BuildFailure):
        build.read_digest(path)


def test_unreadable_metadata_fails_the_build(tmp_path):
    with pytest.raises(build.BuildFailure, match="could not read build metadata"):
        build.read_digest(tmp_path / "does-not-exist.json")


def test_unparseable_metadata_fails_the_build(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text("{not json")

    with pytest.raises(build.BuildFailure, match="could not read build metadata"):
        build.read_digest(path)


# ---------------------------------------------------------------------------
# Reporting the result
# ---------------------------------------------------------------------------


def test_success_payload_carries_the_flat_image_reference(tmp_path):
    path = tmp_path / "term"

    build.write_termination_message(path, {"image": "5@sha256:" + "b" * 64})

    assert json.loads(path.read_text()) == {"image": "5@sha256:" + "b" * 64}


def test_failure_payload_carries_no_image_key(tmp_path):
    """The worker requires `image` to call a build succeeded, so a failure
    report can never be mistaken for one."""
    path = tmp_path / "term"

    build.write_termination_message(path, {"error": "stack detection failed"})

    assert "image" not in json.loads(path.read_text())


def test_an_unwritable_termination_path_does_not_mask_the_outcome(tmp_path):
    """Failing to report must not turn a finished build into a crash."""
    build.write_termination_message(tmp_path / "no-such-dir" / "term", {"image": "x"})


# ---------------------------------------------------------------------------
# Environment contract
# ---------------------------------------------------------------------------


def test_a_missing_required_variable_is_named(monkeypatch):
    monkeypatch.delenv("CAELUS_ARTIFACT_URL", raising=False)

    with pytest.raises(build.BuildFailure, match="CAELUS_ARTIFACT_URL"):
        build._env("CAELUS_ARTIFACT_URL")


def test_an_empty_required_variable_counts_as_missing(monkeypatch):
    monkeypatch.setenv("CAELUS_REGISTRY", "")

    with pytest.raises(build.BuildFailure, match="CAELUS_REGISTRY"):
        build._env("CAELUS_REGISTRY")


def test_optional_integers_fall_back_and_validate(monkeypatch):
    monkeypatch.delenv("CAELUS_MAX_ENTRIES", raising=False)
    assert build._env_int("CAELUS_MAX_ENTRIES", 77) == 77

    monkeypatch.setenv("CAELUS_MAX_ENTRIES", "5")
    assert build._env_int("CAELUS_MAX_ENTRIES", 77) == 5

    monkeypatch.setenv("CAELUS_MAX_ENTRIES", "lots")
    with pytest.raises(build.BuildFailure, match="must be an integer"):
        build._env_int("CAELUS_MAX_ENTRIES", 77)


def test_main_exits_non_zero_without_an_artifact_url(monkeypatch, tmp_path):
    for name in ("CAELUS_ARTIFACT_URL", "CAELUS_USER_ID", "CAELUS_BUILD_ID", "CAELUS_REGISTRY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CAELUS_TERMINATION_LOG", str(tmp_path / "term"))

    assert build.main() == 1
    assert "image" not in json.loads((tmp_path / "term").read_text())


# ---------------------------------------------------------------------------
# The version-matched pair
# ---------------------------------------------------------------------------


def test_the_frontend_image_is_pinned_by_digest():
    """A tag here would silently decouple the frontend from the railpack binary
    whose plan format it has to understand."""
    assert "@sha256:" in build.FRONTEND_IMAGE
    _, digest = build.FRONTEND_IMAGE.split("@", 1)
    assert len(digest) == len("sha256:") + 64


def test_the_builder_image_setting_points_at_a_pinned_digest():
    """`builder_image` must not drift to a bare tag: a mutated tag would swap
    the builder out from under an in-flight build."""
    from app.config import CaelusSettings

    assert "@sha256:" in CaelusSettings(_env_file=None).builder_image
