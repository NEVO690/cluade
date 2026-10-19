"""Keeps on-device replies in the writing systems of the conversation.

Small multilingual models sometimes drift into other scripts in the middle of a
reply: Chinese characters, Korean, Cyrillic or Arabic letters appearing inside a
Hebrew sentence (measured in the AVEN evaluation suite, see ``evals/``). The
engine supports grammar-constrained sampling, so AVEN Local passes a grammar
that makes the characters of scripts that are *not* in the conversation
impossible to generate. Scripts the user writes in are always allowed, and
everything else (Latin, Hebrew, digits, punctuation, math symbols, emoji) is
untouched.
"""

from __future__ import annotations

import re

# (name, character ranges). A script is blocked unless the conversation uses it.
FOREIGN_SCRIPTS: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("cjk", ((0x2E80, 0x2FDF), (0x3000, 0x303F), (0x3040, 0x30FF), (0x3100, 0x31FF), (0x3400, 0x4DBF),
             (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0xFF00, 0xFF0F), (0xFF1A, 0xFF20), (0xFF5B, 0xFFEF))),
    ("hangul", ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF))),
    ("cyrillic", ((0x0400, 0x052F),)),
    ("arabic", ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    ("thai", ((0x0E00, 0x0E7F),)),
    ("devanagari", ((0x0900, 0x097F),)),
    ("armenian", ((0x0530, 0x058F),)),
    ("georgian", ((0x10A0, 0x10FF),)),
)  # fmt: skip

# Accented Latin letters ("é", "ß"). Blocked only when the user writes Hebrew, where they
# only appear as broken words; × and ÷ stay allowed.
ACCENTED_LATIN = ((0x00C0, 0x00D6), (0x00D8, 0x00F6), (0x00F8, 0x024F))
HEBREW = re.compile("[\u05d0-\u05ea]")
LATIN = re.compile("[A-Za-z]")


def _uses(text: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in ranges)


def blocked_ranges(conversation: list[str], latest_user_message: str) -> list[tuple[int, int]]:
    """Character ranges the reply may not contain."""
    text = "\n".join(conversation)
    blocked = [r for _name, ranges in FOREIGN_SCRIPTS if not _uses(text, ranges) for r in ranges]
    hebrew = len(HEBREW.findall(latest_user_message)) > len(LATIN.findall(latest_user_message))
    if hebrew and not _uses(text, ACCENTED_LATIN):
        blocked.extend(ACCENTED_LATIN)
    return blocked


def reply_grammar(conversation: list[str], latest_user_message: str) -> str | None:
    """A llama.cpp GBNF grammar allowing any text without the blocked characters (None: no limits)."""
    ranges = blocked_ranges(conversation, latest_user_message)
    if not ranges:
        return None
    char_class = "".join(f"\\u{lo:04X}-\\u{hi:04X}" for lo, hi in sorted(ranges))
    return f"root ::= [^{char_class}]*\n"
