"""The API client and the status-code contract.

Every row of design Appendix A gets a test, because the table inverts the
conventional reading of 401 and 403 and a plausible-looking "fix" to any one
row breaks a different one.
"""

from __future__ import annotations

import httpx
import pytest

from freepod import AuthenticationError, FreepodError, PermissionError_
from freepod.config import ENVIRONMENTS

from conftest import StubSession, json_response, sequence, text_response


# --------------------------------------------------------------------------
# Transport basics (task 4.1)
# --------------------------------------------------------------------------


def test_the_base_url_comes_from_the_environment(make_api):
    api, recorder, _ = make_api(sequence(json_response(200, {"id": 1})))
    api.get("/api/me")
    assert str(recorder.requests[0].url) == "https://freepod.eu/api/me"


def test_the_dev_environment_targets_the_dev_api(make_api, dev_env):
    api, recorder, _ = make_api(
        sequence(json_response(200, {"id": 1})), environment=dev_env
    )
    api.get("/api/me")
    assert str(recorder.requests[0].url) == "https://dev.freepod.eu/api/me"


def test_the_request_carries_the_bearer_token(make_api):
    api, recorder, _ = make_api(sequence(json_response(200, {"id": 1})))
    api.get("/api/me")
    assert recorder.requests[0].headers["authorization"] == "Bearer token-1"


def test_a_session_with_no_token_sends_no_authorization_header(make_api):
    session = StubSession(access_token=None)
    api, recorder, _ = make_api(sequence(json_response(200, {})), session=session)
    api.get("/api/products")
    assert "authorization" not in recorder.requests[0].headers


def test_me_rejects_a_response_without_an_id(make_api):
    api, _, _ = make_api(sequence(json_response(200, {"email": "e@example.com"})))
    with pytest.raises(FreepodError, match="unexpected /api/me response"):
        api.me()


# --------------------------------------------------------------------------
# Appendix A, row 1: 401 from the edge
# --------------------------------------------------------------------------


def test_a_401_stops_and_does_not_reauthenticate(make_api):
    api, recorder, session = make_api(sequence(text_response(401, "Unauthorized\n")))

    with pytest.raises(AuthenticationError):
        api.get("/api/me")

    assert session.refreshes == 0, "a 401 must never trigger a refresh"
    assert session.logins == 0, "re-authenticating succeeds and changes nothing"
    assert recorder.calls == 1


def test_the_401_message_names_the_group_requirement_on_dev(make_api, dev_env):
    api, _, _ = make_api(sequence(text_response(401)), environment=dev_env)

    with pytest.raises(AuthenticationError) as raised:
        api.get("/api/me")

    message = str(raised.value)
    assert "freepod-dev" in message
    assert "change nothing" in message


def test_the_401_message_on_prod_points_at_login(make_api):
    api, _, _ = make_api(sequence(text_response(401)))

    with pytest.raises(AuthenticationError) as raised:
        api.get("/api/me")

    message = str(raised.value)
    assert "freepod login" in message
    # Prod gates on no group, so naming one here would be a false lead.
    assert "freepod-dev" not in message


def test_a_401_exits_three(make_api):
    from freepod import EXIT_NOT_AUTHENTICATED

    api, _, _ = make_api(sequence(text_response(401)))
    with pytest.raises(AuthenticationError) as raised:
        api.get("/api/me")
    assert raised.value.exit_code == EXIT_NOT_AUTHENTICATED


# --------------------------------------------------------------------------
# Appendix A, row 2: 403 from the edge (non-JSON body)
# --------------------------------------------------------------------------


def test_an_expired_access_token_is_recovered_silently(make_api):
    api, recorder, session = make_api(
        sequence(text_response(403), json_response(200, {"id": 7, "email": "e@example.com"}))
    )

    assert api.me()["id"] == 7

    assert session.refreshes == 1
    assert session.logins == 0
    assert recorder.calls == 2
    # The retry must carry the *new* token, not the one that was just refused.
    assert recorder.auth_headers() == ["Bearer token-1", "Bearer token-2"]


def test_a_rejected_refresh_falls_back_to_a_full_login(make_api):
    session = StubSession(refresh_succeeds=False)
    api, recorder, _ = make_api(
        sequence(text_response(403), json_response(200, {"id": 7})), session=session
    )

    assert api.me()["id"] == 7

    assert session.refreshes == 1
    assert session.logins == 1
    assert recorder.auth_headers()[1] == "Bearer login-token-1"


def test_an_edge_403_without_a_content_type_still_refreshes(make_api):
    """oauth2-proxy's refusal is a bare `http.Error`; do not rely on headers."""
    api, _, session = make_api(
        sequence(
            httpx.Response(403, content=b"Forbidden\n"),
            json_response(200, {"id": 7}),
        )
    )
    assert api.me()["id"] == 7
    assert session.refreshes == 1


def test_a_403_whose_json_is_not_an_error_document_refreshes(make_api):
    """A JSON body without `detail` is not the API's refusal shape."""
    api, _, session = make_api(
        sequence(json_response(403, ["not", "a", "detail"]), json_response(200, {"id": 7}))
    )
    assert api.me()["id"] == 7
    assert session.refreshes == 1


# --------------------------------------------------------------------------
# Appendix A, row 3: 403 from the API (JSON `detail`)
# --------------------------------------------------------------------------


def test_an_api_403_stops_without_refreshing(make_api):
    api, recorder, session = make_api(
        sequence(json_response(403, {"detail": "Not permitted for this user"}))
    )

    with pytest.raises(PermissionError_, match="Not permitted for this user"):
        api.get("/api/users/2/deployments")

    assert session.refreshes == 0, "an API 403 is a permission error, not a stale token"
    assert session.logins == 0
    assert recorder.calls == 1


def test_an_api_403_is_not_an_authentication_error(make_api):
    """It must not be caught by anything that would trigger a login."""
    api, _, _ = make_api(sequence(json_response(403, {"detail": "Admin only"})))

    with pytest.raises(PermissionError_) as raised:
        api.get("/api/admin/things")

    assert not isinstance(raised.value, AuthenticationError)


# --------------------------------------------------------------------------
# Appendix A, row 4: 404 "Not authenticated"
# --------------------------------------------------------------------------


def test_a_404_not_authenticated_is_reported_as_a_platform_condition(make_api):
    api, recorder, session = make_api(sequence(json_response(404, {"detail": "Not authenticated"})))

    with pytest.raises(FreepodError) as raised:
        api.get("/api/me")

    message = str(raised.value)
    assert "unexpected platform condition" in message
    assert "report" in message
    assert session.logins == 0, "this is a bug report, not a login prompt"
    assert not isinstance(raised.value, AuthenticationError)
    assert recorder.calls == 1


def test_an_ordinary_404_is_returned_to_the_caller(make_api):
    api, _, _ = make_api(sequence(json_response(404, {"detail": "Deployment not found"})))
    response = api.get("/api/users/1/deployments/999")
    assert response.status_code == 404


# --------------------------------------------------------------------------
# The bounded-refresh rule (task 4.3)
# --------------------------------------------------------------------------


def test_an_endpoint_that_always_403s_refreshes_exactly_once(make_api):
    """The rule that keeps a permanent 403 from becoming a login loop."""
    api, recorder, session = make_api(sequence(text_response(403)))

    with pytest.raises(PermissionError_) as raised:
        api.get("/api/me")

    assert session.refreshes == 1
    assert recorder.calls == 2, "one original attempt, one retry, then stop"
    assert "even after refreshing" in str(raised.value)


def test_an_always_403_endpoint_does_not_loop_on_logins(make_api):
    session = StubSession(refresh_succeeds=False)
    api, recorder, _ = make_api(sequence(text_response(403)), session=session)

    with pytest.raises(PermissionError_):
        api.get("/api/me")

    assert session.logins == 1
    assert recorder.calls == 2


def test_a_refresh_replays_the_request_byte_for_byte(make_api):
    """The retry must be the *same* request, headers included.

    Section 9 streams the build log with `Range: bytes={offset}-`. If a refresh
    mid-stream dropped or reset that header, the retry would re-fetch from
    offset 0 and print the whole log twice. `_send` pops `headers` out of its
    own kwargs, so this pins down that the mutation cannot leak back into the
    retry loop.
    """
    api, recorder, session = make_api(
        sequence(text_response(403), httpx.Response(206, content=b"more log output"))
    )
    caller_headers = {"Range": "bytes=1024-"}

    response = api.get("/api/builds/42/log", headers=caller_headers)

    assert response.status_code == 206
    assert session.refreshes == 1
    assert recorder.calls == 2

    ranges = [request.headers.get("range") for request in recorder.requests]
    assert ranges == ["bytes=1024-", "bytes=1024-"], "the retry lost or reset the byte range"

    # The other half, and the one a Range-only assertion would miss: the replay
    # must carry the *refreshed* credential. A merge that injected auth into the
    # caller's dict and then deferred to it would keep Range identical while
    # replaying the token that was just refused — and the bounded-refresh rule
    # would report that second 403 as a permission error.
    assert recorder.auth_headers() == ["Bearer token-1", "Bearer token-2"]

    # Caller-supplied headers are read, never written.
    assert caller_headers == {"Range": "bytes=1024-"}


def test_caller_headers_do_not_leak_between_requests(make_api):
    """One request's headers must not accumulate onto the next.

    The realistic refactor that breaks this is hoisting `_headers()` into a
    base dict built once and dropping the defensive copy, at which point
    `update` writes into shared state and a `Range` outlives its request.
    """
    api, recorder, _ = make_api(sequence(json_response(200, {"id": 7})))

    api.get("/api/builds/42/log", headers={"Range": "bytes=1024-"})
    api.get("/api/me")

    assert recorder.requests[0].headers.get("range") == "bytes=1024-"
    assert recorder.requests[1].headers.get("range") is None


def test_a_refresh_replays_an_unsafe_body_unchanged(make_api):
    api, recorder, _ = make_api(
        sequence(text_response(403), json_response(201, {"id": "b1"}))
    )

    api.post("/api/builds", json={"artifact_id": "abc"})

    bodies = [request.content for request in recorder.requests]
    assert bodies[0] == bodies[1]


def test_the_refresh_budget_is_per_request_not_per_client(make_api):
    """A second request gets its own refresh; the bound is not a lifetime one."""
    api, _, session = make_api(
        sequence(
            text_response(403),
            json_response(200, {"id": 7}),
            text_response(403),
            json_response(200, {"id": 7}),
        )
    )

    api.me()
    api.me()

    assert session.refreshes == 2


# --------------------------------------------------------------------------
# Retries (task 4.5)
# --------------------------------------------------------------------------


def test_a_transient_server_error_on_a_read_is_retried(make_api):
    api, recorder, _ = make_api(
        sequence(text_response(503, "upstream down"), json_response(200, {"id": 7}))
    )

    assert api.me()["id"] == 7
    assert recorder.calls == 2


def test_read_retries_are_bounded(make_api):
    from freepod.api import MAX_ATTEMPTS

    api, recorder, _ = make_api(sequence(text_response(500, "boom")))

    response = api.get("/api/me")

    assert response.status_code == 500
    assert recorder.calls == MAX_ATTEMPTS


def test_an_unsafe_request_is_not_repeated(make_api):
    """A duplicate build or deployment is worse than a reported failure."""
    api, recorder, _ = make_api(sequence(text_response(500, "boom")))

    response = api.post("/api/builds", json={"artifact_id": "abc"})

    assert response.status_code == 500
    assert recorder.calls == 1


def test_an_unsafe_request_is_not_repeated_after_a_network_error(make_api):
    def handler(_request):
        raise httpx.ConnectError("connection refused")

    api, recorder, _ = make_api(handler)

    with pytest.raises(FreepodError, match="cannot reach"):
        api.post("/api/builds", json={"artifact_id": "abc"})

    assert recorder.calls == 1


def test_a_network_error_on_a_read_is_retried_then_reported(make_api):
    from freepod.api import MAX_ATTEMPTS

    def handler(_request):
        raise httpx.ConnectError("connection refused")

    api, recorder, _ = make_api(handler)

    with pytest.raises(FreepodError, match="cannot reach"):
        api.get("/api/me")

    assert recorder.calls == MAX_ATTEMPTS


def test_a_4xx_on_a_read_is_not_retried(make_api):
    api, recorder, _ = make_api(sequence(json_response(400, {"detail": "bad request"})))

    response = api.get("/api/me")

    assert response.status_code == 400
    assert recorder.calls == 1


# --------------------------------------------------------------------------
# Public routes: the asymmetry the contract exists to work around
# --------------------------------------------------------------------------


def test_a_skipped_route_answers_normally_whatever_the_token_is(make_api):
    """`/api/products` is on the edge's skip_auth_routes list.

    It is answered anonymously however good or bad the credential is, so no
    part of the status-code contract ever fires there. That asymmetry is
    exactly why design D15 requires `GET /api/me` before any public read.
    """
    session = StubSession(access_token="expired-and-malformed")
    api, recorder, _ = make_api(sequence(json_response(200, [{"slug": "custom"}])), session=session)

    assert api.get_json("/api/products") == [{"slug": "custom"}]
    assert session.refreshes == 0
    assert recorder.calls == 1


# --------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------


def test_get_json_raises_on_a_non_successful_status(make_api):
    api, _, _ = make_api(sequence(json_response(409, {"detail": "operation in progress"})))

    with pytest.raises(FreepodError, match="operation in progress"):
        api.get_json("/api/users/1/deployments/2")


def test_get_json_raises_on_an_unparseable_body(make_api):
    api, _, _ = make_api(sequence(httpx.Response(200, content=b"<html>nope</html>")))

    with pytest.raises(FreepodError, match="unparseable"):
        api.get_json("/api/me")


def test_environments_are_isolated_by_construction():
    """No client can be built that talks to one environment with the other's id."""
    assert ENVIRONMENTS["dev"].api_base != ENVIRONMENTS["prod"].api_base
    assert ENVIRONMENTS["dev"].client_id != ENVIRONMENTS["prod"].client_id
