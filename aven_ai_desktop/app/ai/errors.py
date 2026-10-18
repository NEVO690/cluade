"""Provider-independent error types shown to the user."""

from __future__ import annotations


class AIError(Exception):
    """Base class. ``user_message`` is safe to display; ``retryable`` hints the UI."""

    title = "Request failed"
    retryable = True
    opens_settings = False

    def __init__(self, user_message: str, *, detail: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


class MissingCredentialsError(AIError):
    title = "AI provider not configured"
    retryable = False
    opens_settings = True


class MissingModelError(AIError):
    title = "No model selected"
    retryable = False
    opens_settings = True


class AuthenticationFailedError(AIError):
    title = "Invalid API key"
    retryable = False
    opens_settings = True


class PermissionDeniedError(AIError):
    title = "Access denied"
    retryable = False
    opens_settings = True


class ModelNotFoundError(AIError):
    title = "Model not available"
    retryable = False
    opens_settings = True


class RateLimitedError(AIError):
    title = "Rate limit reached"


class ProviderTimeoutError(AIError):
    title = "Request timed out"


class NetworkError(AIError):
    title = "Connection problem"


class ProviderOverloadedError(AIError):
    title = "Provider unavailable"


class InvalidRequestError(AIError):
    title = "Request rejected"
    retryable = False


class ContentRefusedError(AIError):
    title = "Response declined"
    retryable = False


class ProviderError(AIError):
    title = "Provider error"
