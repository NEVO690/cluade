"""Made With AVEN's generation pipeline: plan → build → check → repair, and changes.

The pipeline talks to the AI through a ``complete`` function (system, user, max_tokens,
on_text) -> reply, so it works with every AVEN provider and is easy to test. It never
marks a game as working unless every check in :mod:`app.studio.validate` passed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.code.blocks import extract_blocks
from app.studio import prompts
from app.studio.validate import GameReport, validate_game

Complete = Callable[[str, str, int, Callable[[str], None] | None], str]
Progress = Callable[[str], None]

PLAN_TOKENS = 1500
CODE_TOKENS = 8192
MAX_REPAIRS = 3
PLAN_KEYS = ("title", "genre", "summary", "controls", "systems", "entities", "scenes", "goal", "scope_notes")


class PipelineError(Exception):
    """A user-facing problem in the pipeline (for example, the AI returned no plan)."""


@dataclass
class Attempt:
    code: str
    report: GameReport


@dataclass
class BuildResult:
    code: str
    report: GameReport
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def validated(self) -> bool:
        return self.report.ok


def parse_plan(text: str) -> dict:
    """The JSON plan from a reply (tolerates code fences and text around it)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise PipelineError("The AI did not return a design plan.")
    try:
        data = json.loads(text[start : end + 1])
    except ValueError as exc:
        raise PipelineError("The AI's design plan was not valid JSON.") from exc
    if not isinstance(data, dict) or not str(data.get("title", "")).strip():
        raise PipelineError("The AI's design plan has no title.")
    plan = {key: data.get(key, [] if key in ("controls", "systems", "entities", "scenes") else "") for key in PLAN_KEYS}
    for key in ("controls", "scenes"):
        plan[key] = [str(v) for v in plan[key]] if isinstance(plan[key], list) else [str(plan[key])]
    for key in ("systems", "entities"):
        items = plan[key] if isinstance(plan[key], list) else []
        plan[key] = [
            {"name": str(i.get("name", "")), "description": str(i.get("description", ""))}
            if isinstance(i, dict) else {"name": str(i), "description": ""}
            for i in items
        ]  # fmt: skip
    return plan


def extract_code(text: str) -> str:
    """The game.js code from a reply: the largest JavaScript code block."""
    blocks = [b for b in extract_blocks(text) if b.language in ("javascript", "js", "")]
    if not blocks:
        # A reply that is only code, without fences.
        return text.strip() if re.search(r"AVEN\.createGame", text) and "```" not in text else ""
    return max(blocks, key=lambda b: len(b.code)).code.strip() + "\n"


class GamePipeline:
    def __init__(self, complete: Complete, progress: Progress | None = None, max_repairs: int = MAX_REPAIRS) -> None:
        self.complete = complete
        self.progress = progress or (lambda _message: None)
        self.max_repairs = max_repairs

    def plan(self, description: str, on_text: Callable[[str], None] | None = None) -> dict:
        self.progress("Designing the game…")
        reply = self.complete(prompts.PLAN_SYSTEM, prompts.plan_request(description), PLAN_TOKENS, on_text)
        try:
            return parse_plan(reply)
        except PipelineError:
            self.progress("The plan was not valid JSON; asking again…")
            retry = (
                prompts.plan_request(description) + "\nReturn ONLY the JSON object, starting with { and ending with }."
            )
            return parse_plan(self.complete(prompts.PLAN_SYSTEM, retry, PLAN_TOKENS, on_text))

    def _check_and_repair(self, code: str, on_text: Callable[[str], None] | None) -> BuildResult:
        attempts: list[Attempt] = []
        while True:
            self.progress("Checking the game…")
            report = validate_game(code)
            attempts.append(Attempt(code, report))
            if report.ok:
                self.progress("All checks passed.")
                return BuildResult(code, report, attempts)
            if len(attempts) > self.max_repairs:
                self.progress("Some problems remain after the repair attempts.")
                return BuildResult(code, report, attempts)
            self.progress(
                f"Found {len(report.errors)} problem(s); repairing (attempt {len(attempts)} of {self.max_repairs})…"
            )
            reply = self.complete(
                prompts.REPAIR_SYSTEM, prompts.repair_request(code, report.errors), CODE_TOKENS, on_text
            )
            fixed = extract_code(reply)
            if fixed:
                code = fixed

    def build(self, plan: dict, on_text: Callable[[str], None] | None = None) -> BuildResult:
        self.progress("Writing the game code…")
        code = extract_code(self.complete(prompts.CODE_SYSTEM, prompts.code_request(plan), CODE_TOKENS, on_text))
        return self._check_and_repair(code, on_text)

    def change(self, plan: dict, code: str, request: str, on_text: Callable[[str], None] | None = None) -> BuildResult:
        if not request.strip():
            raise PipelineError("Describe the change first.")
        self.progress("Applying your change…")
        reply = self.complete(prompts.CODE_SYSTEM, prompts.change_request(plan, code, request), CODE_TOKENS, on_text)
        new_code = extract_code(reply) or code
        return self._check_and_repair(new_code, on_text)
