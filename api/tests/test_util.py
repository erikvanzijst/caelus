import pytest

from app.util import amend_url, set_value_at_path, value_for_path


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


# ── value_for_path tests ────────────────────────────────────────────


class TestValueForPath:
    def test_shallow_key(self):
        assert value_for_path({"a": 1}, ("a",)) == 1

    def test_nested_keys(self):
        assert value_for_path({"a": {"b": {"c": 42}}}, ("a", "b", "c")) == 42

    def test_missing_key_returns_none(self):
        assert value_for_path({"a": 1}, ("b",)) is None

    def test_missing_nested_key_returns_none(self):
        assert value_for_path({"a": {"b": 1}}, ("a", "x")) is None

    def test_none_data_returns_none(self):
        assert value_for_path(None, ("a",)) is None

    def test_empty_dict_returns_none(self):
        assert value_for_path({}, ("a",)) is None

    def test_empty_path_returns_root(self):
        data = {"a": 1}
        assert value_for_path(data, ()) == data

    def test_wildcard_descends_into_first_list_element(self):
        assert value_for_path({"items": [{"name": "first"}, {"name": "second"}]}, ("items", "*", "name")) == "first"

    def test_wildcard_on_empty_list_returns_none(self):
        assert value_for_path({"items": []}, ("items", "*", "name")) is None

    def test_wildcard_on_non_list_returns_none(self):
        assert value_for_path({"items": "not-a-list"}, ("items", "*")) is None

    def test_intermediate_non_dict_returns_none(self):
        assert value_for_path({"a": 42}, ("a", "b")) is None

    def test_value_can_be_any_type(self):
        assert value_for_path({"a": [1, 2, 3]}, ("a",)) == [1, 2, 3]
        assert value_for_path({"a": False}, ("a",)) is False
        assert value_for_path({"a": None}, ("a",)) is None

    def test_deeply_nested_with_wildcards(self):
        data = {"level1": {"items": [{"level3": {"val": "deep"}}]}}
        assert value_for_path(data, ("level1", "items", "*", "level3", "val")) == "deep"


# ── set_value_at_path tests ─────────────────────────────────────────


class TestSetValueAtPath:
    def test_shallow_key(self):
        data = {"a": 1}
        set_value_at_path(data, ("a",), 2)
        assert data == {"a": 2}

    def test_nested_keys(self):
        data = {"a": {"b": {"c": 1}}}
        set_value_at_path(data, ("a", "b", "c"), 99)
        assert data["a"]["b"]["c"] == 99

    def test_none_data_is_noop(self):
        set_value_at_path(None, ("a",), 1)  # should not raise

    def test_empty_dict_is_noop(self):
        data = {}
        set_value_at_path(data, ("a",), 1)
        # missing key — does not create it
        assert data == {}

    def test_empty_path_is_noop(self):
        data = {"a": 1}
        set_value_at_path(data, (), "new")
        assert data == {"a": 1}

    def test_missing_intermediate_key_is_noop(self):
        data = {"a": {"b": 1}}
        set_value_at_path(data, ("a", "x", "y"), 99)
        assert data == {"a": {"b": 1}}

    def test_intermediate_non_dict_is_noop(self):
        data = {"a": 42}
        set_value_at_path(data, ("a", "b"), 99)
        assert data == {"a": 42}

    def test_wildcard_sets_first_list_element(self):
        data = {"items": ["old", "keep"]}
        set_value_at_path(data, ("items", "*"), "new")
        assert data == {"items": ["new", "keep"]}

    def test_wildcard_on_empty_list_is_noop(self):
        data = {"items": []}
        set_value_at_path(data, ("items", "*"), "new")
        assert data == {"items": []}

    def test_wildcard_on_non_list_is_noop(self):
        data = {"items": "not-a-list"}
        set_value_at_path(data, ("items", "*"), "new")
        assert data == {"items": "not-a-list"}

    def test_nested_wildcard_then_key(self):
        data = {"items": [{"name": "old", "other": "keep"}]}
        set_value_at_path(data, ("items", "*", "name"), "new")
        assert data["items"][0]["name"] == "new"
        assert data["items"][0]["other"] == "keep"

    def test_wildcard_in_middle_of_path(self):
        data = {"a": {"items": [{"b": {"c": "old"}}]}}
        set_value_at_path(data, ("a", "items", "*", "b", "c"), "new")
        assert data["a"]["items"][0]["b"]["c"] == "new"

    def test_creates_final_key_if_parent_exists(self):
        data = {"a": {}}
        set_value_at_path(data, ("a", "b"), "val")
        assert data == {"a": {"b": "val"}}

    def test_overwrites_with_different_type(self):
        data = {"a": "string"}
        set_value_at_path(data, ("a",), 42)
        assert data == {"a": 42}


# ── round-trip tests ────────────────────────────────────────────────


class TestValuePathRoundTrip:
    """Verify that value_for_path and set_value_at_path are consistent."""

    @pytest.mark.parametrize("path,expected", [
        (("host",), "example.com"),
        (("nested", "host",), "deep.example.com"),
        (("items", "*", "host"), "list.example.com"),
    ])
    def test_read_then_write_then_read(self, path, expected):
        data = {
            "host": "example.com",
            "nested": {"host": "deep.example.com"},
            "items": [{"host": "list.example.com"}],
        }
        original = value_for_path(data, path)
        assert original == expected
        lowered = original.upper()
        set_value_at_path(data, path, lowered)
        assert value_for_path(data, path) == lowered
