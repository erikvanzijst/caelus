from app.util import amend_url


# ── amend_url tests ──────────────────────────────────────────────────


def test_amend_url_no_changes():
    url = "https://example.com/original?key=val#frag"
    assert amend_url(url) == "https://example.com/original?key=val#frag"


def test_amend_url_replace_path():
    assert amend_url("https://example.com/old", path="/new") == "https://example.com/new"
    assert amend_url("https://example.com", path="new") == "https://example.com/new"


def test_amend_url_append_path():
    assert amend_url("https://example.com/base", path="sub") == "https://example.com/base/sub"
    assert amend_url("https://example.com/base/", path="sub") == "https://example.com/base/sub"
    assert amend_url("https://example.com/base", path="/root") == "https://example.com/root"


def test_amend_url_replace_fragment():
    assert amend_url("https://example.com/p#old", fragment="new") == "https://example.com/p#new"


def test_amend_url_remove_fragment():
    assert amend_url("https://example.com/p#old", fragment="") == "https://example.com/p"


def test_amend_url_add_query_params():
    result = amend_url("https://example.com/p", query={"a": "1", "b": "2"})
    assert "a=1" in result
    assert "b=2" in result


def test_amend_url_merge_query_params():
    result = amend_url("https://example.com/p?existing=yes", query={"added": "true"})
    assert "existing=" in result
    assert "added=true" in result


def test_amend_url_override_query_param():
    assert amend_url("https://example.com/p?key=old", query={"key": "new"}) == "https://example.com/p?key=new"


def test_amend_url_preserves_scheme_and_host():
    result = amend_url("http://localhost:8080/path", path="/other")
    assert result.startswith("http://localhost:8080/")
    assert result.endswith("/other")


def test_amend_url_all_components():
    result = amend_url(
        "https://example.com/old?a=1#oldfrag",
        path="/new",
        query={"b": "2"},
        fragment="newfrag",
    )
    assert "/new" in result
    assert "b=2" in result
    assert result.endswith("#newfrag")


def test_amend_url_blank_query_value_preserved():
    result = amend_url("https://example.com/p?empty=", query={})
    assert "empty=" in result
