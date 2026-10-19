"""Keeps on-device replies in the writing systems of the conversation, with well-formed words.

Small multilingual models sometimes drift into other scripts in the middle of a
reply: Chinese characters, Korean, Cyrillic or Arabic letters appearing inside a
Hebrew sentence (measured in the AVEN evaluation suite, see ``evals/``). The
engine supports grammar-constrained sampling, so AVEN Local passes a grammar
that makes the characters of scripts that are *not* in the conversation
impossible to generate. Scripts the user writes in are always allowed, and
everything else (Latin, digits, punctuation, math symbols, emoji) is untouched.

The grammar also never lets a Hebrew letter touch a Latin letter, which removes
broken mixed words ("שינהAdapter"); correct Hebrew writes a hyphen there anyway
("ב-Python"). When the user asks about another language or a translation, no
limits apply, so "translate this to Chinese" still works.
"""

from __future__ import annotations

import re

# (name, character ranges). A script is blocked unless the conversation uses it.
FOREIGN_SCRIPTS: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("hebrew", ((0x0590, 0x05FF), (0xFB1D, 0xFB4F))),
    ("cjk", ((0x2E80, 0x2FDF), (0x3000, 0x303F), (0x3040, 0x30FF), (0x3100, 0x31FF), (0x3400, 0x4DBF),
             (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0xFF00, 0xFF0F), (0xFF1A, 0xFF20), (0xFF5B, 0xFFEF))),
    ("hangul", ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF))),
    ("cyrillic", ((0x0400, 0x052F),)),
    ("arabic", ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    ("thai", ((0x0E00, 0x0E7F),)),
    ("devanagari", ((0x0900, 0x097F),)),
    ("armenian", ((0x0530, 0x058F),)),
    ("georgian", ((0x10A0, 0x10FF),)),
    # Greek words; the letters common in math and science stay allowed (see MATH_GREEK).
    ("greek", ((0x0370, 0x03FF), (0x1F00, 0x1FFF))),
)  # fmt: skip
MATH_GREEK = "αβγδεθλμπρσφωΔΣΠΦΩ"

# Accented Latin letters ("é", "ß"). Blocked only when the user writes Hebrew, where they
# only appear as broken words; × and ÷ stay allowed.
ACCENTED_LATIN = ((0x00C0, 0x00D6), (0x00D8, 0x00F6), (0x00F8, 0x024F))
HEBREW = re.compile("[\u05d0-\u05ea]")
LATIN = re.compile("[A-Za-z]")
# Questions about languages or translations may need any script.
_LANGUAGE_WORDS = (
    "translat", "language", "hebrew", "chinese", "mandarin", "japanese", "korean", "russian", "arabic", "thai",
    "hindi", "armenian", "georgian",
    "תרגם", "תרגום", "שפה", "שפות", "עברית", "סינית", "יפנית", "קוריאנית", "רוסית", "ערבית",
)  # fmt: skip
ABOUT_LANGUAGES = re.compile("|".join(_LANGUAGE_WORDS), re.I)


def _uses(text: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in ranges)


def _allow(ranges: list[tuple[int, int]], chars: str) -> list[tuple[int, int]]:
    """Split ``ranges`` so that ``chars`` are not blocked."""
    out = []
    for lo, hi in ranges:
        start = lo
        for code in sorted(ord(c) for c in chars if lo <= ord(c) <= hi):
            if start <= code - 1:
                out.append((start, code - 1))
            start = code + 1
        if start <= hi:
            out.append((start, hi))
    return out


def blocked_ranges(conversation: list[str], latest_user_message: str) -> list[tuple[int, int]]:
    """Character ranges the reply may not contain."""
    text = "\n".join(conversation)
    blocked = [r for _name, ranges in FOREIGN_SCRIPTS if not _uses(text, ranges) for r in ranges]
    blocked = _allow(blocked, MATH_GREEK)
    hebrew = len(HEBREW.findall(latest_user_message)) > len(LATIN.findall(latest_user_message))
    if hebrew and not _uses(text, ACCENTED_LATIN):
        blocked.extend(ACCENTED_LATIN)
    return blocked


def _char_class(ranges: list[tuple[int, int]]) -> str:
    return "".join(f"\\u{lo:04X}-\\u{hi:04X}" for lo, hi in sorted(ranges))


def reply_grammar(conversation: list[str], latest_user_message: str) -> str | None:
    """A llama.cpp GBNF grammar for the reply (None: no limits).

    Any text is allowed except blocked characters, and a run of Hebrew letters and a
    run of Latin letters are always separated by some other character.
    """
    if ABOUT_LANGUAGES.search(latest_user_message):
        return None
    ranges = blocked_ranges(conversation, latest_user_message)
    hebrew_letters, latin_letters = (0x05D0, 0x05EA), [(0x41, 0x5A), (0x61, 0x7A)]
    hebrew_allowed = not any(lo <= 0x05D0 <= hi for lo, hi in ranges)
    other = _char_class([*ranges, hebrew_letters, *latin_letters])
    runs = "hebrew+ | latin+" if hebrew_allowed else "latin+"
    return (
        "root ::= other* (run other+)* run?\n"
        f"run ::= {runs}\n"
        f"hebrew ::= [{_char_class([hebrew_letters])}]\n"
        "latin ::= [A-Za-z]\n"
        f"other ::= [^{other}]\n"
    )
