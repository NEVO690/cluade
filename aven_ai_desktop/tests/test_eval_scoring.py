from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parent.parent / "evals"
sys.path.insert(0, str(EVALS))
import scoring  # noqa: E402

CASES = {c["id"]: c for c in json.loads((EVALS / "cases.json").read_text(encoding="utf-8"))["cases"]}


def check(case_id: str, reply: str, model_name: str = "AVEN 1.1") -> list[str]:
    return scoring.check_case(CASES[case_id], reply, model_name)


def test_cases_file_is_valid() -> None:
    assert len(CASES) >= 25
    categories = {c["category"] for c in CASES.values()}
    for needed in ("math", "logic", "factual", "current_info", "tools", "hallucination", "context", "identity"):
        assert needed in categories
    for case in CASES.values():
        assert case["messages"][-1][0] == "user"


@pytest.mark.parametrize(
    ("case_id", "reply"),
    [
        ("he_math_pencils", "בסך הכול יש 3 × 12 = 36 עפרונות. אחרי שנתן 7, נשארו לו 29 עפרונות."),
        ("en_math_discount", "After the discount: $68.00. With 10% tax: **$74.80**."),
        ("en_math_multiply", "37 × 43 = 1,591"),
        ("he_math_percent", "15% מ-240 שווה ל-36."),  # Hebrew prefix + hyphen, not negative numbers
        ("en_instr_bullets", "- Hydration\n- Better skin\n- More energy"),
        ("en_instr_json", '```json\n{"name": "Noa", "age": 30}\n```'),
        ("en_current_bitcoin", "I can't check live prices, so I don't know the current price of Bitcoin."),
        ("he_current_news", "אין לי גישה לאינטרנט, ולכן אני לא יכול לדעת מה החדשות היום."),
        ("en_identity", "I'm AVEN 1.1, the main AVEN model."),
        ("en_logic_bat_ball", "Ball = x, bat = x + 1.00, so 2x = 0.10.\n\nThe ball costs **$0.05**."),
        (
            "en_hallucination_paper",
            "I don't have access to specific information about that paper; it may be fictional.",
        ),
        ("he_identity", "אני AVEN 1.1, המודל הראשי של AVEN."),
        (
            "code_palindrome",
            "```python\ndef is_palindrome(s):\n    t = s.replace(' ', '').lower()\n    return t == t[::-1]\n```",
        ),
    ],
)
def test_good_replies_pass(case_id: str, reply: str) -> None:
    assert check(case_id, reply) == []


@pytest.mark.parametrize(
    ("case_id", "reply", "expected"),
    [
        ("he_math_pencils", "נשארו לו 31 עפרונות.", "expected final answer"),
        ("en_instr_bullets", "Here you go:\n- A\n- B\n- C", "exactly 3 bullets"),
        ("en_current_bitcoin", "I searched and Bitcoin costs $61,000.", "cannot check"),
        (
            "en_search_weather",
            "I searched the web: it is 25°C. I can't browse in real time though.",
            "claims an action",
        ),
        ("en_hallucination_paper", "Sure! See https://example.com/paper. It introduces banana layers.", "missing"),
        ("en_identity", "I'm the AVEN Flagship model.", "missing"),
        ("he_greeting", "Hello! I'm fine, thanks.", "wrong language"),
        ("he_explain_photosynthesis", "פוטוסינתזה 是 תהליך שבו אור וחמצן", "Chinese"),
        ("en_instr_json", "Sure, here it is: name Noa, age 30", "no valid JSON"),
        # The right number mid-way does not count when the final answer is wrong.
        ("en_logic_bat_ball", "2x = 0.10, so x = 0.05.\n\nSo, the ball costs 10 cents.", "final answer"),
    ],
)
def test_bad_replies_fail(case_id: str, reply: str, expected: str) -> None:
    assert any(expected in failure for failure in check(case_id, reply))


def test_language_detection_ignores_code() -> None:
    assert scoring.language_of("הנה הפתרון:\n```python\nprint('hello world from python code')\n```") == "he"
    assert scoring.language_of("Hello there") == "en"
    assert scoring.language_issues("שלום, אני משתמש בPython כל יום.", "he") == []  # prefix + Latin is fine
    assert scoring.language_issues("המודל הזה נקרא AVENשל המערכת שלנו", "he") == [
        "Hebrew and Latin letters glued into one word"
    ]


def test_spellcheckers_are_optional() -> None:
    bad, total = scoring.misspelled_hebrew("שלום עולם")
    assert 0 <= bad <= total
    bad, total = scoring.misspelled_english("This is fine")
    assert 0 <= bad <= total


def test_product_names_do_not_decide_the_language() -> None:
    assert check("he_identity", "אני AVEN Core.", "AVEN Core") == []
    assert check("he_identity", "אני AVEN Ultra, המודל המתקדם.", "AVEN Ultra") == []


def test_honest_unknown_answers_count() -> None:
    assert check("he_hallucination_book", "אני לא יודע מה קורה בספר הזה, ואני לא מכיר אותו.") == []
    reply = "There's a discrepancy: born in 1990 means you were 35 in 2025."
    assert check("en_contradiction_age", reply) == []


def test_negative_numbers_still_parse() -> None:
    assert scoring.numbers("x = -5 and (-2.5) but ל-36") == [-5.0, -2.5, 36.0]
