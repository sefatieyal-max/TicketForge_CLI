"""HTTP client for the TicketForge API .

This module is the only place that talks HTTP. It never prints and never
asks for input: it returns data or raises a TicketForgeError subclass.
"""

import math
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import quote

import requests

from exceptions import (
    AuthError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    TicketForgeError,
    ValidationError,
)
from validators import parse_iso_datetime

DEFAULT_BASE_URL = "https://integrations-assignment-ticketforge.vercel.app"
API_PREFIX = "/api/tforge"
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_PAGE_SIZE = 5

RATE_LIMIT_HEADER = "X-RateLimit-Limit"
RATE_REMAINING_HEADER = "X-RateLimit-Remaining"
RATE_RESET_HEADER = "X-RateLimit-Reset"
RETRY_AFTER_HEADER = "Retry-After"
NOT_FOUND_ERROR_CODE = "not_found"

DEEP_VIEW_PARAMS = {"view": "deep"}


class TicketForgeClient:
    """Thin wrapper around the TicketForge REST API using HTTP Basic auth."""

    def __init__(self, username=None, password=None,
                 base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.username = username
        self._auth = (username, password) if username and password else None
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.rate_limit = None
        self.rate_remaining = None
        self.rate_reset_at = None

    # ---------- account ----------

    def set_password(self, password):
        """Replace the password (e.g. after the user re-types a wrong one)."""
        self._auth = (self.username, password) if self.username and password else None

    def register(self, username, password):
        """Create a new account. Does not need credentials."""
        body = self._request("POST", "/user/register",
                             authenticated=False,
                             json={"username": username, "password": password})
        return self._unwrap(body, "user")

    def verify_credentials(self):
        """Raise AuthError if the credentials are wrong (the web app's 'login')."""
        self._request("GET", "/workitems/mine", params={"limit": 1})

    # ---------- tickets ----------

    def list_tickets_page(self, cursor=None, limit=DEFAULT_PAGE_SIZE):
        """Return one page: (tickets, next_cursor). next_cursor is None on the last page."""
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        body = self._request("GET", "/workitems/mine", params=params)
        tickets = self._unwrap(body, "workitems")
        pagination = body.get("pagination") or {}
        next_cursor = pagination.get("nextCursor") if pagination.get("hasMore") else None
        return tickets, next_cursor

    def get_ticket(self, ref):
        """Return one ticket with full details."""
        body = self._request("GET", f"/workitem/{self._segment(ref)}", params=DEEP_VIEW_PARAMS)
        return self._unwrap(body, "workitem")

    def create_ticket(self, title, description=None, depends_on=None, custom_fields=None):
        """Create a ticket. Optional fields are only sent when provided."""
        payload = {"title": title, "description": description, "dependsOn": depends_on or None}
        if custom_fields:
            payload["customFields"] = custom_fields
        body = self._request("POST", "/workitem/publish", json=payload)
        return self._unwrap(body, "workitem")

    def update_ticket(self, ref, title, description, stage, depends_on=None, custom_fields=None):
        """Replace a ticket (the API uses PUT, so every field must be sent)."""
        payload = {
            "title": title,
            "description": description or None,
            "stage": stage,
            "dependsOn": depends_on or None,
            "customFields": custom_fields or {},
        }
        body = self._request("PUT", f"/workitem/{self._segment(ref)}", json=payload)
        return self._unwrap(body, "workitem")

    # ---------- custom fields ----------

    def list_custom_fields(self):
        """Return all custom field definitions."""
        return self._unwrap(self._request("GET", "/custom-fields"), "customFields")

    def create_custom_field(self, name, label):
        """Define a new custom field."""
        body = self._request("POST", "/custom-fields", json={"name": name, "label": label})
        return self._unwrap(body, "customField")

    def update_custom_field_label(self, field_id, label):
        """Rename a custom field's label."""
        body = self._request("PUT", f"/custom-fields/{self._segment(field_id)}",
                             json={"label": label})
        return self._unwrap(body, "customField")

    def delete_custom_field(self, field_id):
        """Delete a custom field definition."""
        self._request("DELETE", f"/custom-fields/{self._segment(field_id)}")

    # ---------- internals ----------

    def _request(self, method, path, authenticated=True, **kwargs):
        """Send a request to an API path and return the parsed JSON body (or None)."""
        if authenticated:
            if self._auth is None:
                raise AuthError("Not configured. Run setup first.")
            kwargs["auth"] = self._auth
        url = f"{self.base_url}{API_PREFIX}{path}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except UnicodeEncodeError:
            raise AuthError("Username and password can only use Latin characters (HTTP Basic auth).") from None
        except requests.exceptions.Timeout:
            raise NetworkError("The request timed out.") from None
        except requests.exceptions.RequestException:
            raise NetworkError("Could not connect to TicketForge. Check your connection.") from None
        self._track_rate_limit(response)
        if not response.ok:
            self._raise_for_error(response)
        if response.status_code == HTTPStatus.NO_CONTENT or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise TicketForgeError("TicketForge returned a response that is not JSON.") from None

    def _raise_for_error(self, response):
        """Translate an HTTP error response into one of our exceptions."""
        message = self._error_message(response)
        if self._error_body(response).get("err") == NOT_FOUND_ERROR_CODE:
            raise NotFoundError(message)
        match response.status_code:
            case HTTPStatus.UNAUTHORIZED:
                raise AuthError("Invalid username or password.")
            case HTTPStatus.TOO_MANY_REQUESTS:
                raise RateLimitError("Rate limit exceeded.", wait_seconds=self._wait_seconds(response))
            case HTTPStatus.FORBIDDEN:
                raise PermissionDeniedError(f"Permission denied: {message}")
            case HTTPStatus.NOT_FOUND:
                raise NotFoundError(f"Not found: {message}")
            case HTTPStatus.BAD_REQUEST | HTTPStatus.CONFLICT | HTTPStatus.UNPROCESSABLE_ENTITY:
                raise ValidationError(f"TicketForge rejected the request: {message}")
            case _:
                raise TicketForgeError(f"TicketForge returned an error ({response.status_code}): {message}")

    def _track_rate_limit(self, response):
        """Remember the latest rate-limit headers so the CLI can show the budget."""
        headers = response.headers
        if RATE_REMAINING_HEADER not in headers:
            return
        self.rate_limit = self._to_int(headers.get(RATE_LIMIT_HEADER))
        self.rate_remaining = self._to_int(headers.get(RATE_REMAINING_HEADER))
        self.rate_reset_at = parse_iso_datetime(headers.get(RATE_RESET_HEADER))

    def _wait_seconds(self, response):
        """Seconds until we may retry: Retry-After, then the reset time in this response,
        then the last reset time we saw. None if none of them is known or it already passed."""
        retry_after = self._to_int(response.headers.get(RETRY_AFTER_HEADER))
        if retry_after is not None:
            return retry_after
        reset_at = parse_iso_datetime(response.headers.get(RATE_RESET_HEADER)) or self.rate_reset_at
        if reset_at is None:
            return None
        remaining = (reset_at - datetime.now(timezone.utc)).total_seconds()
        return math.ceil(remaining) if remaining > 0 else None

    @staticmethod
    def _error_body(response):
        """The JSON error body as a dict, or {} if it is missing or not JSON."""
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def _error_message(self, response):
        """Human-readable error text: `message`, falling back to the `err` code."""
        body = self._error_body(response)
        return body.get("message") or body.get("err") or "No details provided."

    @staticmethod
    def _unwrap(body, key):
        """Return body[key], raising a clear error if the response shape is unexpected."""
        try:
            return body[key]
        except (KeyError, TypeError):
            raise TicketForgeError(f"Unexpected response from TicketForge (missing '{key}').") from None

    @staticmethod
    def _segment(value):
        """Encode a value for safe use as one URL path segment."""
        return quote(str(value), safe="")

    @staticmethod
    def _to_int(text):
        try:
            return int(text)
        except (TypeError, ValueError):
            return None
