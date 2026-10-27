import json
import base64
import pytest
import requests
import responses
from datetime import datetime, timedelta, timezone
from client import API_PREFIX, DEFAULT_BASE_URL, TicketForgeClient
from exceptions import (
    AuthError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    TicketForgeError,
    ValidationError,
)

API = f"{DEFAULT_BASE_URL}{API_PREFIX}"
TICKET_URL = f"{API}/workitem/TF-1"
LIST_URL = f"{API}/workitems/mine"

def reset_in(seconds):
    """An X-RateLimit-Reset value `seconds` from now, in the API's format (ISO with 'Z')."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

@pytest.fixture
def client():
    return TicketForgeClient("eyal", "secret")


@responses.activate
def test_get_ticket_unwraps_workitem(client):
    responses.get(TICKET_URL, json={"workitem": {"ref": "TF-1", "title": "x"}})
    assert client.get_ticket("TF-1")["title"] == "x"


@responses.activate
def test_sends_exact_basic_auth_header(client):
    responses.get(TICKET_URL, json={"workitem": {}})
    client.get_ticket("TF-1")
    expected = "Basic " + base64.b64encode(b"eyal:secret").decode()
    assert responses.calls[0].request.headers["Authorization"] == expected

@responses.activate
def test_not_found_code_with_400_raises_not_found(client):
    """API quirk: a missing ticket comes back as 400 with err=not_found."""
    responses.get(TICKET_URL, status=400,
                  json={"err": "not_found", "message": "workitem TF-1 does not exist"})
    with pytest.raises(NotFoundError, match="does not exist"):
        client.get_ticket("TF-1")


@responses.activate
def test_other_400_raises_validation_error(client):
    responses.get(TICKET_URL, status=400, json={"err": "bad_input", "message": "title required"})
    with pytest.raises(ValidationError, match="title required"):
        client.get_ticket("TF-1")


@responses.activate
def test_401_raises_auth_error(client):
    responses.get(TICKET_URL, status=401, json={"err": "unauthorized"})
    with pytest.raises(AuthError):
        client.get_ticket("TF-1")


@responses.activate
def test_429_raises_rate_limit_with_wait(client):
    responses.get(TICKET_URL, status=429, json={}, headers={"Retry-After": "12"})
    with pytest.raises(RateLimitError) as error_info:
        client.get_ticket("TF-1")
    assert error_info.value.wait_seconds == 12


@responses.activate
def test_html_body_raises_clear_error(client):
    responses.get(TICKET_URL, body="<html>maintenance</html>", status=200)
    with pytest.raises(TicketForgeError, match="not JSON"):
        client.get_ticket("TF-1")


@responses.activate
def test_timeout_raises_network_error(client):
    responses.get(TICKET_URL, body=requests.exceptions.Timeout())
    with pytest.raises(NetworkError):
        client.get_ticket("TF-1")


@responses.activate
def test_list_returns_next_cursor_only_when_has_more(client):
    responses.get(LIST_URL, json={"workitems": [{"ref": "TF-1"}],
                                  "pagination": {"hasMore": True, "nextCursor": "abc"}})
    responses.get(LIST_URL, json={"workitems": [{"ref": "TF-2"}],
                                  "pagination": {"hasMore": False}})
    first, cursor = client.list_tickets_page()
    second, last_cursor = client.list_tickets_page(cursor=cursor)
    assert cursor == "abc"
    assert last_cursor is None
    assert "cursor=abc" in responses.calls[1].request.url


@responses.activate
def test_rate_limit_headers_are_tracked(client):
    responses.get(TICKET_URL, json={"workitem": {}},
                  headers={"X-RateLimit-Limit": "50", "X-RateLimit-Remaining": "47",
                           "X-RateLimit-Reset": "2026-10-25T08:08:16.971Z"})
    client.get_ticket("TF-1")
    assert (client.rate_remaining, client.rate_limit) == (47, 50)


@responses.activate
def test_update_sends_every_field_because_put_replaces(client):
    responses.put(TICKET_URL, json={"workitem": {"ref": "TF-1"}})
    client.update_ticket("TF-1", "t", "d", "review", ["TF-2"], {})
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"title": "t", "description": "d", "stage": "review",
                    "dependsOn": ["TF-2"], "customFields": {}}


def test_ref_is_encoded_in_the_path(client):
    assert client._segment("../x") == "..%2Fx"

@responses.activate
def test_response_without_expected_key_raises_clear_error(client):
    responses.get(TICKET_URL, json={"something_else": {}})
    with pytest.raises(TicketForgeError, match="missing 'workitem'"):
        client.get_ticket("TF-1")


@responses.activate
def test_server_error_with_html_body_raises_base_error(client):
    responses.get(TICKET_URL, status=500, body="<html>oops</html>")
    with pytest.raises(TicketForgeError, match="500"):
        client.get_ticket("TF-1")


@responses.activate
def test_429_without_retry_after_has_unknown_wait(client):
    responses.get(TICKET_URL, status=429, json={})
    with pytest.raises(RateLimitError) as error_info:
        client.get_ticket("TF-1")
    assert error_info.value.wait_seconds is None


def test_unconfigured_client_fails_before_sending():
    """No credentials -> AuthError without any network call (responses is not active)."""
    with pytest.raises(AuthError):
        TicketForgeClient().get_ticket("TF-1")

@responses.activate
def test_non_latin_password_raises_auth_error_not_traceback():
    responses.get(TICKET_URL, json={"workitem": {}})
    with pytest.raises(AuthError, match="Latin"):
        TicketForgeClient("eyal", "סיסמה").get_ticket("TF-1")


@responses.activate
def test_429_wait_comes_from_iso_reset_header_with_z(client):
    reset = reset_in(30)
    responses.get(TICKET_URL, status=429, json={}, headers={"X-RateLimit-Reset": reset})
    with pytest.raises(RateLimitError) as error_info:
        client.get_ticket("TF-1")
    assert 28 <= error_info.value.wait_seconds <= 30

@responses.activate
def test_429_without_headers_uses_reset_from_earlier_response(client):
    responses.get(TICKET_URL, json={"workitem": {}},
                  headers={"X-RateLimit-Limit": "50", "X-RateLimit-Remaining": "1",
                           "X-RateLimit-Reset": reset_in(30)})
    responses.get(TICKET_URL, status=429, json={})
    client.get_ticket("TF-1")
    with pytest.raises(RateLimitError) as error_info:
        client.get_ticket("TF-1")
    assert 28 <= error_info.value.wait_seconds <= 30


@responses.activate
def test_429_with_reset_in_the_past_has_unknown_wait(client):
    responses.get(TICKET_URL, status=429, json={}, headers={"X-RateLimit-Reset": "2020-01-01T00:00:00.000Z"})
    with pytest.raises(RateLimitError) as error_info:
        client.get_ticket("TF-1")
    assert error_info.value.wait_seconds is None