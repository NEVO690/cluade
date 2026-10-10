"""Exception base shared by the social modules (kept separate to avoid import cycles)."""


class SocialError(ValueError):
    """A user-facing error from the social network; the message is shown as-is."""
