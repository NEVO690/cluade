"""Builds the playable page for a game: one self-contained, locked-down index.html.

The engine and the game code are inlined, and a Content-Security-Policy allows only
those two scripts (by SHA-256 hash) and blocks every network request, so a generated
game cannot load anything or send anything anywhere, even when opened from disk.
"""

from __future__ import annotations

import base64
import hashlib
import html

from app.studio.sandbox import engine_source


def _script(code: str) -> tuple[str, str]:
    """(safe inline script text, its CSP hash source)."""
    text = "\n" + code.replace("</script", "<\\/script").replace("<!--", "<\\!--") + "\n"
    digest = base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")
    return text, f"'sha256-{digest}'"


def build_page(title: str, game_code: str) -> str:
    engine, engine_hash = _script(engine_source())
    game, game_hash = _script(game_code)
    policy = (
        "default-src 'none'; "
        f"script-src {engine_hash} {game_hash}; "
        "style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; "
        "connect-src 'none'; form-action 'none'; base-uri 'none'"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{policy}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title or "AVEN game")}</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #05070d; }}
  body {{ display: flex; align-items: center; justify-content: center; }}
  canvas {{ max-width: 100vw; max-height: 100vh; box-shadow: 0 0 40px rgba(123, 108, 255, 0.25); }}
  footer {{ position: fixed; bottom: 6px; right: 10px; font: 12px sans-serif; color: #5d6577; }}
</style>
</head>
<body>
<canvas id="game" tabindex="0"></canvas>
<footer>Made With AVEN</footer>
<script>{engine}</script>
<script>{game}</script>
</body>
</html>
"""
