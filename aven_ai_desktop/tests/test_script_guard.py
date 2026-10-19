from __future__ import annotations

import re

from app.local.script_guard import blocked_ranges, reply_grammar


def blocked(text: str, ranges) -> bool:
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in ranges)


def test_hebrew_conversation_blocks_foreign_scripts_and_accented_latin() -> None:
    ranges = blocked_ranges(["שלום, מה שלומך?"], "שלום, מה שלומך?")
    for leaked in ("听", "책", "мир", "اسم", "ß", "é", "カ"):
        assert blocked(leaked, ranges), leaked
    # Hebrew, English, digits, math symbols and emoji stay allowed.
    for allowed in ("שלום", "Python 3.12", "3 × 4 ÷ 2 = 6", "🙂🚀⚠️", "“quotes” — dash", "π ≈ 3.14"):
        assert not blocked(allowed, ranges), allowed


def test_english_conversation_keeps_accented_names() -> None:
    ranges = blocked_ranges(["Tell me about José and the café"], "Tell me about José and the café")
    assert not blocked("José café naïve", ranges)
    assert blocked("听", ranges)


def test_scripts_used_in_the_conversation_stay_allowed() -> None:
    ranges = blocked_ranges(["Translate 你好 and Привет to Hebrew"], "Translate 你好 and Привет to Hebrew")
    assert not blocked("你好 Привет", ranges)
    assert blocked("안녕", ranges)


def test_grammar_is_valid_gbnf_shape() -> None:
    grammar = reply_grammar(["שלום"], "שלום")
    assert re.fullmatch(r"root ::= \[\^(\\u[0-9A-F]{4}-\\u[0-9A-F]{4})+\]\*\n", grammar)
