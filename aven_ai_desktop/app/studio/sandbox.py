"""Smoke-tests a generated game inside QuickJS, a sandboxed JavaScript interpreter.

The game runs against a stub browser (see ``runtime/sandbox_prelude.js``) for a few
seconds of game time while the checker presses keys. It catches crashes, games that
never start, and games that draw nothing. QuickJS has no file, network or process
access, and the run has memory and time limits, so generated code cannot harm the
computer. Passing this check does not prove the game is fun or bug-free.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

RUNTIME = Path(__file__).resolve().parent / "runtime"
MEMORY_LIMIT = 128 * 1024 * 1024
TIME_LIMIT_SECONDS = 8
FRAMES = 300  # five seconds of game time

# Key presses during the run: (frame, event, code). Start/confirm keys, movement and action.
SCRIPT: list[tuple[int, str, str]] = [
    (5, "keydown", "Enter"), (7, "keyup", "Enter"),
    (10, "keydown", "Space"), (12, "keyup", "Space"),
    (20, "keydown", "ArrowRight"), (80, "keyup", "ArrowRight"),
    (85, "keydown", "ArrowUp"), (110, "keyup", "ArrowUp"),
    (115, "keydown", "ArrowLeft"), (160, "keyup", "ArrowLeft"),
    (165, "keydown", "ArrowDown"), (190, "keyup", "ArrowDown"),
    (195, "keydown", "Space"), (200, "keyup", "Space"),
    (205, "keydown", "KeyD"), (240, "keyup", "KeyD"),
    (250, "keydown", "KeyE"), (252, "keyup", "KeyE"),
    (260, "keydown", "KeyR"), (262, "keyup", "KeyR"),
]  # fmt: skip


@dataclass
class SmokeResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    draws: int = 0
    frames: int = 0
    scene: str = ""
    logs: list[str] = field(default_factory=list)


def engine_source() -> str:
    return (RUNTIME / "aven_game.js").read_text(encoding="utf-8")


def _clean(message: str) -> str:
    message = str(message).strip()
    if not message or message == "null":
        return "the game used too much memory"
    if "interrupted" in message:
        return "the game took too long (an endless loop?)"
    lines = message.replace("<input>", "game.js").splitlines()
    # Keep the error and the game's own frames, not the engine's or the checker's internals.
    noise = ("(native)", " tick ", "__runFrames", "<eval>", "<anonymous> (game.js)")
    kept = [lines[0], *[line for line in lines[1:] if not any(n in f" {line} " for n in noise)][:3]]
    return "\n".join(kept)[:600]


def smoke_test(game_code: str, frames: int = FRAMES) -> SmokeResult:
    import quickjs

    context = quickjs.Context()
    context.set_memory_limit(MEMORY_LIMIT)
    context.set_time_limit(TIME_LIMIT_SECONDS)
    try:
        context.eval((RUNTIME / "sandbox_prelude.js").read_text(encoding="utf-8"))
        context.eval(engine_source())
    except Exception as exc:  # the checker itself is broken: report, don't blame the game
        log.error("Sandbox setup failed: %s", exc)
        return SmokeResult(False, [f"The game checker could not start: {_clean(str(exc))}"])
    try:
        context.eval(game_code)
    except Exception as exc:
        return SmokeResult(False, [f"The game crashed while loading: {_clean(str(exc))}"])

    presses: dict[int, list[list[str]]] = {}
    for frame, kind, code in SCRIPT:
        if frame < frames:
            presses.setdefault(frame, []).append([kind, code])
    try:
        raw = context.eval(f"__runFrames({int(frames)}, {json.dumps(presses)})")
        data = json.loads(raw)
    except Exception as exc:
        return SmokeResult(False, [f"The game crashed while running: {_clean(str(exc))}"])

    result = SmokeResult(True, draws=data["draws"], frames=data["frames"], scene=data["scene"], logs=data["logs"])
    if data["games"] == 0:
        result.errors.append("The game never called AVEN.createGame(...).")
    elif data["error"]:
        result.errors.append(f"The game crashed while running: {_clean(data['error'])}")
    elif data["frames"] == 0:
        result.errors.append('The game never started: call game.start("sceneName") at the end of game.js.')
    elif data["draws"] == 0:
        result.errors.append("The game ran but drew nothing on the screen.")
    result.ok = not result.errors
    return result
