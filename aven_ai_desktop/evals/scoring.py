"""Deterministic scoring for the AVEN model evaluation (no AI judge).

Each case lists checks; a case passes only when every check passes. Every reply
is also checked for language problems (wrong language, Chinese/Japanese/Korean
characters leaking into the reply, broken characters, leaked reasoning tags).
"""

from __future__ import annotations

import ast
import contextlib
import json
import re
import shutil
import subprocess

HEBREW = re.compile(r"[\u05d0-\u05ea]")
LATIN = re.compile(r"[A-Za-z]")
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff66-\uff9f]")
EMOJI = re.compile(r"[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\u2b55]")
CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)(?:```|$)", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+", re.I)
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

LIMITATION = re.compile(
    r"(can't|cannot|can not|don't|do not|unable to|not able to|no) "
    r"(access|browse|check|look up|search|provide (live|real-time|current)|get (live|real-time|current))"
    r"|real[- ]time|up[- ]to[- ]date|live (data|prices|information)|internet access|browse the (web|internet)"
    r"|knowledge cutoff|training data|my knowledge|as of my"
    r"|אין לי גישה|לא יכול(ה)? (לגשת|לבדוק|לחפש|לגלוש)|אינני יכול|אין באפשרותי|אין ביכולתי|לא מחובר|לאינטרנט|באינטרנט"
    r"|בזמן אמת|מידע עדכני|עדכונים|הידע שלי|נכון ל",
    re.I,
)
FAKE_ACTION = re.compile(
    r"\bI (just )?(searched|looked it up|looked up|checked online|browsed|googled|ran the code|executed)\b"
    r"|according to my (search|browsing)|I found (online|on the web)|my search (shows|found)"
    r"|חיפשתי|בדקתי באינטרנט|גלשתי|הרצתי את הקוד|בדקתי ברשת|לפי החיפוש שלי",
    re.I,
)


def prose(text: str) -> str:
    """The reply without code blocks and inline code."""
    return INLINE_CODE.sub(" ", CODE_BLOCK.sub(" ", text))


AVEN_NAME = re.compile(r"\bAVEN(?: (?:1\.1|Ultra|Core|Light|CODE|AI))?\b")


def language_of(text: str) -> str:
    plain = AVEN_NAME.sub(" ", prose(text))  # product names do not decide the language
    he, la = len(HEBREW.findall(plain)), len(LATIN.findall(plain))
    if he + la < 8:
        return "none"  # too little text to tell (e.g. just a number)
    return "he" if he / (he + la) >= 0.6 else "en" if la / (he + la) >= 0.85 else "mixed"


def words(text: str) -> list[str]:
    return re.findall(r"[\w֐-׿'’-]+", prose(text))


def numbers(text: str) -> list[float]:
    out = []
    for raw in NUMBER.findall(text.replace("−", "-")):
        with contextlib.suppress(ValueError):
            out.append(float(raw.replace(",", "")))
    return out


def final_lines(text: str) -> str:
    """Where the final answer is: the last line, and the last line that contains a number."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    with_number = [line for line in lines if re.search(r"\d", line)]
    return "\n".join({lines[-1], with_number[-1]} if with_number else {lines[-1]})


def json_payload(text: str) -> object:
    match = CODE_BLOCK.search(text)
    candidate = match.group(1) if match else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object")
    return json.loads(candidate[start : end + 1])


def language_issues(text: str, lang: str) -> list[str]:
    """Problems that are wrong in every reply, whatever the question."""
    issues = []
    if not text.strip():
        return ["empty reply"]
    if CJK.search(text):
        issues.append("Chinese/Japanese/Korean characters in the reply")
    if "\ufffd" in text:
        issues.append("broken (replacement) characters")
    if "<think>" in text or "</think>" in text:
        issues.append("reasoning tags leaked")
    detected = language_of(text)
    if lang in ("he", "en") and detected not in (lang, "none"):
        issues.append(f"wrong language: expected {lang}, got {detected}")
    # A one-letter Hebrew prefix before a Latin word ("\u05d1Python") is normal; other mixes are broken words.
    if re.search(r"[A-Za-z][\u05d0-\u05ea]|[\u05d0-\u05ea]{2}[A-Za-z]", prose(text)):
        issues.append("Hebrew and Latin letters glued into one word")
    return issues


def check_case(case: dict, reply: str, model_name: str) -> list[str]:
    """Failed checks for one reply (empty list = pass)."""
    failures = list(language_issues(reply, case.get("lang", "any")))
    checks = case.get("checks", {})
    lowered = reply.lower()
    for pattern in checks.get("contains_all", []):
        pattern = pattern.replace("{model_name}", re.escape(model_name.lower()))
        if not re.search(pattern, lowered, re.M):
            failures.append(f"missing: {pattern}")
    if "final_contains" in checks and not re.search(checks["final_contains"], final_lines(lowered)):
        failures.append(f"final answer should match: {checks['final_contains']}")
    for pattern in checks.get("not_contains", []):
        if re.search(pattern, lowered):
            failures.append(f"should not contain: {pattern}")
    if "max_words" in checks and len(words(reply)) > checks["max_words"]:
        failures.append(f"too long: {len(words(reply))} words > {checks['max_words']}")
    if "emoji_max" in checks and len(EMOJI.findall(reply)) > checks["emoji_max"]:
        failures.append("too many emojis")
    if "final_number" in checks:
        expected = float(checks["final_number"])
        found = numbers(reply)
        if not any(abs(n - expected) < 1e-6 for n in found[-3:]):
            failures.append(f"expected final answer {checks['final_number']}, last numbers {found[-3:]}")
    if "bullet_count" in checks:
        bullets = [line for line in reply.splitlines() if re.match(r"\s*([-*•]|\d+[.)])\s+\S", line)]
        others = [line for line in reply.splitlines() if line.strip() and line not in bullets]
        if len(bullets) != checks["bullet_count"] or others:
            failures.append(f"expected exactly {checks['bullet_count']} bullets and nothing else")
    if "json_equals" in checks:
        try:
            if json_payload(reply) != checks["json_equals"]:
                failures.append("JSON has the wrong content")
        except ValueError:
            failures.append("no valid JSON")
    if checks.get("limitation") and not LIMITATION.search(reply):
        failures.append("does not say it cannot check current information")
    if checks.get("no_fake_action") and FAKE_ACTION.search(reply):
        failures.append("claims an action it cannot perform (search, browsing, running code)")
    if checks.get("no_urls") and URL.search(reply):
        failures.append("invented a link")
    if "python_defines" in checks:
        code = "\n".join(m.group(1) for m in CODE_BLOCK.finditer(reply)) or reply
        try:
            tree = ast.parse(code)  # parsed only, never executed
            names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
            if checks["python_defines"] not in names:
                failures.append(f"no function {checks['python_defines']}")
        except SyntaxError:
            failures.append("Python code does not parse")
    if checks.get("no_emoji_in_code") and any(EMOJI.search(m.group(1)) for m in CODE_BLOCK.finditer(reply)):
        failures.append("emoji inside code")
    return failures


# --- spelling (uses hspell / aspell when installed; reported separately from pass/fail) ---


def misspelled_hebrew(text: str) -> tuple[int, int]:
    """(misspelled, total) Hebrew words according to hspell; (0, 0) when hspell is missing."""
    hebrew_words = re.findall(r"[\u05d0-\u05ea\"'״׳]+", prose(text))
    hebrew_words = [w.strip("\"'״׳") for w in hebrew_words if HEBREW.search(w)]
    if not hebrew_words or not shutil.which("hspell"):
        return 0, 0
    data = "\n".join(hebrew_words).encode("iso-8859-8", errors="ignore")
    out = subprocess.run(["hspell"], input=data, capture_output=True, check=False).stdout  # noqa: S607
    bad = [w for w in out.decode("iso-8859-8", errors="ignore").split() if HEBREW.search(w)]
    bad = [w for w in bad if w not in ("שגיאות", "כתיב", "שנמצאו:")]
    return len(bad), len(hebrew_words)


def misspelled_english(text: str) -> tuple[int, int]:
    """(misspelled, total) English words according to aspell; (0, 0) when aspell is missing."""
    english = re.findall(r"\b[A-Za-z][a-z]{2,}\b", prose(text))  # skips names in capitals and short tokens
    if not english or not shutil.which("aspell"):
        return 0, 0
    out = subprocess.run(
        ["aspell", "list", "-l", "en"],  # noqa: S607 - spellchecker found on PATH
        input="\n".join(english),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return len(out.split()), len(english)
