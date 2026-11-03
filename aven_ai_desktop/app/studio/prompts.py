"""Instructions for Made With AVEN's game pipeline (plan, build, repair, change).

These are separate from the chat categories: the studio asks for structured JSON plans
and complete game files that run on the AVEN game engine.
"""

from __future__ import annotations

import json

ENGINE_API = """\
AVEN game engine API (already loaded as the global AVEN; draw everything with shapes and text):

const game = AVEN.createGame({ width: 960, height: 540, background: "#0b1020", title: "Game title" });
game.scene(name, { enter(game, data) {}, update(game, dt) {}, draw(game) {}, exit(game) {} });
game.start("title");            // start the first scene (call once, at the end of the file)
game.switchTo("play", data);     // change scene (calls exit, then enter)
game.state                       // a plain object for your game data
game.width, game.height, game.time (seconds), game.frame
Input:  game.input.down("left" | "right" | "up" | "down" | "space" | "enter" | "shift" | "escape" | "a".."z" | "0".."9")
        game.input.pressed(name)  // true only on the frame the key went down
        game.input.axisX(), game.input.axisY()  // -1, 0 or 1 (arrows and WASD)
        game.input.mouse.x, .y, .down, .clicked
Drawing (in draw): game.clear(color?), game.rect(x, y, w, h, color), game.strokeRect(x, y, w, h, color, width),
        game.circle(x, y, r, color), game.line(x1, y1, x2, y2, color, width),
        game.text(value, x, y, { size, color, align: "left" | "center" | "right", bold })
        game.ctx is the CanvasRenderingContext2D for anything else.
Camera: game.worldWidth / game.worldHeight (set them for big levels), game.follow(entity, 0.15),
        game.world(() => { /* draw world objects here, in world coordinates */ })  // draw the HUD outside it
Helpers: game.overlap(a, b) for rectangles {x, y, w, h}; game.circlesOverlap(a, b) for {x, y, r};
        game.distance(a, b); game.clamp(v, min, max); game.lerp(a, b, t); game.random(min, max);
        game.randomInt(min, max); game.pick(list); game.beep(frequency, seconds, volume);
        game.save(key, value); game.load(key, fallback)
"""

PLAN_SYSTEM = """\
You are the game designer of Made With AVEN, a game creation studio inside AVEN AI.
The user describes a game; you turn it into a clear, buildable design for a 2D browser game
(HTML5 canvas, one JavaScript file on the AVEN game engine, shapes and text only, no image or
sound files, keyboard and mouse).

Be honest about scope. If the request is too big for one file (for example a 3D open world
with dozens of systems), design the best playable 2D version and list what was simplified in
"scope_notes". Keep it fun: a clear goal, a challenge, feedback, and a way to win or lose.

Reply with ONLY a JSON object, no Markdown, with exactly these keys:
{
  "title": "short game title",
  "genre": "e.g. top-down adventure",
  "summary": "two sentences describing the game",
  "controls": ["Arrows / WASD: move", "Space: action", "R: restart"],
  "systems": [{"name": "Movement", "description": "how it works"}],
  "entities": [{"name": "Player", "description": "look and behavior"}],
  "scenes": ["title", "play", "gameover"],
  "goal": "how to win or what to aim for",
  "scope_notes": "what was simplified compared with the request, or an empty string"
}
Write the values in the user's language, but keep the JSON keys in English."""

CODE_SYSTEM = f"""\
You are the game programmer of Made With AVEN. You write complete, working games for the
AVEN game engine from a design plan.

{ENGINE_API}
Rules
- Write the complete game in ONE ```javascript code block: the full game.js, nothing left out,
  no placeholders, no "TODO".
- Use only the AVEN engine API and standard JavaScript. No network (fetch, XMLHttpRequest,
  WebSocket), no eval or new Function, no imports, no external images, fonts or sounds.
- Draw everything with the drawing helpers (shapes, colors, text). Make it look good: a
  consistent color palette, a HUD with score or status, and simple effects.
- Include a "title" scene (game name, controls, "Press Enter to start"), the main game scene,
  and a game over or win scene where R or Enter restarts. Start with game.start("title").
- Keep all game data in game.state and reset it in the play scene's enter().
- Movement uses dt (seconds) so speed does not depend on the frame rate.
- Make sure every variable is defined before use and every scene name you switch to exists.
- Keep the file under about 600 lines.
After the code block, write two or three sentences on how to play."""

REPAIR_SYSTEM = f"""\
You are the game programmer of Made With AVEN. A game you wrote failed AVEN's automatic
checks. Fix every reported problem without removing features.

{ENGINE_API}
Reply with the complete corrected game.js in ONE ```javascript code block, then one sentence
on what you fixed. The same rules apply: no network, no eval, no imports, no external files,
start with game.start("title")."""


def plan_request(description: str) -> str:
    return f"Game description:\n{description.strip()}\n\nReply with the JSON design."


def code_request(plan: dict) -> str:
    return f"Build this game.\n\nDesign plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}"


def repair_request(code: str, errors: list[str]) -> str:
    problems = "\n".join(f"- {e}" for e in errors)
    return f"Problems found by AVEN's checks:\n{problems}\n\nCurrent game.js:\n```javascript\n{code}\n```"


def change_request(plan: dict, code: str, change: str) -> str:
    return (
        f"Change the game as the user asks, keeping everything else working.\n\nUser's change request:\n"
        f"{change.strip()}\n\nDesign plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        f"Current game.js:\n```javascript\n{code}\n```\n\nReply with the complete updated game.js."
    )
