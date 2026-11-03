"""Checks for generated games: syntax, safety rules and a sandboxed smoke test.

A game is "validated" only when every check passes. Nothing here executes the game
outside the QuickJS sandbox (see :mod:`app.studio.sandbox`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.code.blocks import CodeBlock
from app.code.validation import check_tree_sitter
from app.studio.sandbox import smoke_test

MAX_CODE_CHARS = 200_000

# Things a game must never do: reach the network, load code, or escape the page.
FORBIDDEN = [
    (re.compile(r"\bfetch\s*\("), "uses fetch() (network access is not allowed)"),
    (re.compile(r"\bXMLHttpRequest\b"), "uses XMLHttpRequest (network access is not allowed)"),
    (re.compile(r"\bWebSocket\b|\bEventSource\b"), "opens a network connection (not allowed)"),
    (re.compile(r"\bnavigator\.sendBeacon\b"), "sends data over the network (not allowed)"),
    (re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(|\bFunction\s*\(\s*['\"]"), "builds code from text (eval/Function)"),
    (
        re.compile(r"\bimport\s*\(|^\s*import\s.+from\s", re.M),
        "imports modules (games must be one self-contained file)",
    ),
    (re.compile(r"\bdocument\.cookie\b"), "reads cookies (not allowed)"),
    (re.compile(r"\bwindow\.open\s*\(|\blocation\.(href|assign|replace)\b"), "opens or changes pages (not allowed)"),
    (re.compile(r"""\b(src|href)\s*=\s*['"]https?://"""), "loads external files (draw with shapes instead)"),
]


@dataclass
class GameReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)  # human-readable list of what passed

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_game(code: str, run: bool = True) -> GameReport:
    report = GameReport()
    if not code.strip():
        report.errors.append("No game code was produced.")
        return report
    if len(code) > MAX_CODE_CHARS:
        report.errors.append(f"game.js is too large ({len(code):,} characters; the limit is {MAX_CODE_CHARS:,}).")
        return report

    syntax = check_tree_sitter(CodeBlock(0, "javascript", code, "game.js"))
    syntax_errors = [f"game.js line {f.line}: {f.message}" for f in syntax if f.severity == "error"]
    if syntax_errors:
        report.errors += syntax_errors
        return report
    report.checks.append("JavaScript syntax is valid")

    for pattern, message in FORBIDDEN:
        match = pattern.search(code)
        if match:
            line = code[: match.start()].count("\n") + 1
            report.errors.append(f"game.js line {line}: {message}")
    if "AVEN.createGame" not in code:
        report.errors.append("game.js must create the game with AVEN.createGame(...).")
    if not re.search(r"\.start\s*\(", code):
        report.errors.append('game.js must start the game with game.start("sceneName").')
    if report.errors:
        return report
    report.checks.append("Safety rules: no network access, no eval, no external files")

    if run:
        result = smoke_test(code)
        if not result.ok:
            report.errors += result.errors
            return report
        report.checks.append(
            f"Sandbox test: ran {result.frames} frames with simulated keys and drew to the screen "
            f"({result.draws} draw calls)"
        )
        if result.scene and result.scene.lower() in ("title", "menu", "start", "intro"):
            report.warnings.append("The test never left the title screen: make Enter or Space start the game.")
    return report
