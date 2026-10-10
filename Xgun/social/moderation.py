"""Basic, local-only content moderation helpers.

This is intentionally simple: a word filter for text, length limits, and an
automatic hide threshold for reported content. A future online service must
perform its own, server-side moderation — nothing here is trusted remotely.
"""
from __future__ import annotations

import re

from social.errors import SocialError

MAX_TITLE = 60
MAX_CAPTION = 300
MAX_COMMENT = 200
AUTO_HIDE_REPORTS = 3
REPORT_REASONS = ("Spam", "Harassment or bullying", "Hate speech", "Violence or dangerous acts",
                  "Sexual content", "Misinformation", "Other")

# Kept short on purpose; extend from a moderation service in online builds.
_BLOCKED = ["fuck", "shit", "bitch", "cunt", "nigger", "faggot", "retard", "kys", "kill yourself"]
_BLOCKED_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _BLOCKED) + r")\w*", re.IGNORECASE)
_HASHTAG_RE = re.compile(r"#(\w{1,30})")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class ModerationError(SocialError):
    pass


def clean_text(text: str, max_len: int, *, required: bool = False, field: str = "Text") -> str:
    text = _CONTROL_RE.sub("", text or "").strip()
    text = re.sub(r"\s{3,}", "  ", text)
    if required and not text:
        raise ModerationError(f"{field} can't be empty.")
    if len(text) > max_len:
        raise ModerationError(f"{field} is too long ({len(text)}/{max_len} characters).")
    return text


def contains_blocked_language(text: str) -> bool:
    return bool(_BLOCKED_RE.search(text or ""))


def mask_blocked_language(text: str) -> str:
    return _BLOCKED_RE.sub(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), text)


def extract_hashtags(text: str) -> list[str]:
    seen: list[str] = []
    for tag in _HASHTAG_RE.findall(text or ""):
        tag = tag.lower()
        if tag not in seen:
            seen.append(tag)
    return seen[:10]
