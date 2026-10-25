"""Exception hierarchy for the TicketForge client.

The CLI catches these instead of raw `requests` errors, so it never needs
to know which HTTP library the client uses.
"""


class TicketForgeError(Exception):
    """Base class for every error raised by the client."""


class AuthError(TicketForgeError):
    """Credentials are missing, wrong, or expired (401)."""


class PermissionDeniedError(TicketForgeError):
    """Authenticated, but not allowed to do this (403)."""


class NotFoundError(TicketForgeError):
    """The requested resource does not exist (404)."""


class ValidationError(TicketForgeError):
    """The API rejected the request data (400 / 409 / 422)."""


class NetworkError(TicketForgeError):
    """Timeout, DNS failure, or connection refused."""


class RateLimitError(TicketForgeError):
    """Too many requests. `wait_seconds` is None when the wait is unknown."""

    def __init__(self, message, wait_seconds=None):
        super().__init__(message)
        self.wait_seconds = wait_seconds