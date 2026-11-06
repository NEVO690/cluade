"""Self-contained right-to-left text support (no external packages needed).

pygame renders strings glyph-by-glyph in logical order, so for Hebrew and Arabic
we must (1) shape Arabic letters into their contextual presentation forms and
(2) reorder the string into visual order. This module does both with a compact
implementation of the parts of the Unicode bidi algorithm a game UI needs:
RTL runs, embedded LTR runs (Latin, Cyrillic, numbers), neutral resolution and
bracket mirroring.
"""

# ---------------------------------------------------------------- Arabic shaping
# char -> (isolated, final, initial, medial); right-joining letters have only 2 forms
_DUAL = {
    0x0626: 0xFE89, 0x0628: 0xFE8F, 0x062A: 0xFE95, 0x062B: 0xFE99, 0x062C: 0xFE9D,
    0x062D: 0xFEA1, 0x062E: 0xFEA5, 0x0633: 0xFEB1, 0x0634: 0xFEB5, 0x0635: 0xFEB9,
    0x0636: 0xFEBD, 0x0637: 0xFEC1, 0x0638: 0xFEC5, 0x0639: 0xFEC9, 0x063A: 0xFECD,
    0x0641: 0xFED1, 0x0642: 0xFED5, 0x0643: 0xFED9, 0x0644: 0xFEDD, 0x0645: 0xFEE1,
    0x0646: 0xFEE5, 0x0647: 0xFEE9, 0x064A: 0xFEF1,
}
_RIGHT = {
    0x0622: 0xFE81, 0x0623: 0xFE83, 0x0624: 0xFE85, 0x0625: 0xFE87, 0x0627: 0xFE8D,
    0x0629: 0xFE93, 0x062F: 0xFEA9, 0x0630: 0xFEAB, 0x0631: 0xFEAD, 0x0632: 0xFEAF,
    0x0648: 0xFEED, 0x0649: 0xFEEF,
}
_NONJOIN = {0x0621: 0xFE80}
_TATWEEL = 0x0640
_LAM = 0x0644
_LAM_ALEF = {0x0622: 0xFEF5, 0x0623: 0xFEF7, 0x0625: 0xFEF9, 0x0627: 0xFEFB}


def _is_harakat(cp):
    return 0x064B <= cp <= 0x065F or cp == 0x0670


def _joins_next(cp):
    return cp in _DUAL or cp == _TATWEEL


def _joins_prev(cp):
    return cp in _DUAL or cp in _RIGHT or cp == _TATWEEL


def shape_arabic(text):
    if not any(0x0600 <= ord(c) <= 0x06FF for c in text):
        return text
    cps = [ord(c) for c in text if not _is_harakat(ord(c))]
    out = []
    i = 0
    n = len(cps)
    while i < n:
        cp = cps[i]
        prev_cp = cps[i - 1] if i > 0 else None
        connect_prev = prev_cp is not None and _joins_next(prev_cp) and _joins_prev(cp)
        if cp == _LAM and i + 1 < n and cps[i + 1] in _LAM_ALEF:
            base = _LAM_ALEF[cps[i + 1]]
            out.append(chr(base + 1 if connect_prev else base))
            i += 2
            continue
        nxt = cps[i + 1] if i + 1 < n else None
        connect_next = nxt is not None and _joins_next(cp) and _joins_prev(nxt)
        if cp in _DUAL:
            base = _DUAL[cp]
            if connect_prev and connect_next:
                out.append(chr(base + 3))
            elif connect_prev:
                out.append(chr(base + 1))
            elif connect_next:
                out.append(chr(base + 2))
            else:
                out.append(chr(base))
        elif cp in _RIGHT:
            base = _RIGHT[cp]
            out.append(chr(base + 1 if connect_prev else base))
        elif cp in _NONJOIN:
            out.append(chr(_NONJOIN[cp]))
        else:
            out.append(chr(cp))
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- bidi reorder
_MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<", "«": "»", "»": "«"}


def is_rtl_char(c):
    o = ord(c)
    return (0x0590 <= o <= 0x08FF) or (0xFB1D <= o <= 0xFDFF) or (0xFE70 <= o <= 0xFEFF)


def has_rtl(text):
    return any(is_rtl_char(c) for c in text)


def _classes(text):
    cls = []
    n = len(text)
    for i, c in enumerate(text):
        if is_rtl_char(c):
            cls.append("R")
        elif c.isalnum():
            cls.append("L")
        else:
            cls.append("N")
    # numeric glue: sign before a digit, separators between digits behave like the number
    for i, c in enumerate(text):
        if cls[i] != "N":
            continue
        nxt_digit = i + 1 < n and text[i + 1].isdigit()
        prv_digit = i > 0 and text[i - 1].isdigit()
        if c in "+-−" and nxt_digit and (i == 0 or not text[i - 1].isalnum()):
            cls[i] = "L"
        elif c in ".,:/%" and prv_digit and (nxt_digit or c == "%"):
            cls[i] = "L"
    return cls


def to_visual(text, rtl_base):
    """Convert a single logical line into visual (left-to-right glyph) order."""
    if not text:
        return text
    if not rtl_base and not has_rtl(text):
        return text
    text = shape_arabic(text)
    cls = _classes(text)
    base = "R" if rtl_base else "L"
    n = len(text)
    # resolve neutrals from surrounding strong types
    resolved = list(cls)
    i = 0
    while i < n:
        if cls[i] != "N":
            i += 1
            continue
        j = i
        while j < n and cls[j] == "N":
            j += 1
        before = cls[i - 1] if i > 0 else base
        after = cls[j] if j < n else base
        d = before if before == after else base
        for k in range(i, j):
            resolved[k] = d
        i = j
    # group runs
    runs = []
    start = 0
    for k in range(1, n + 1):
        if k == n or resolved[k] != resolved[start]:
            runs.append((resolved[start], text[start:k]))
            start = k
    parts = []
    for d, s in runs:
        if d == "R":
            parts.append("".join(_MIRROR.get(c, c) for c in reversed(s)))
        else:
            parts.append(s)
    if rtl_base:
        parts.reverse()
        return "".join(parts)
    return "".join(parts)
