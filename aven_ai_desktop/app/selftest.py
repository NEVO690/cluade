"""``AVEN AI.exe --self-test report.json``: proves a build contains everything 2.0 needs.

Used by CI on the packaged Windows build. Each check uses the real component (catalog
files, every code checker, the game sandbox and engine, entitlement signatures), and
for every checker a broken sample must fail while a correct one passes. No network is
used and nothing is written except the report.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

FENCE = "`" * 3
SAMPLES = {
    "python": ("def ok(a):\n    return a\n", "def broken(:\n    pass\n"),
    "csharp": (
        "using UnityEngine;\npublic class A : MonoBehaviour { void Start() { } }\n",
        "public class A { void B() { int x = 1 } }\n",
    ),
    "javascript": ("const a = [1, 2].map((x) => x * 2);\n", "const a = (1, ;\n"),
    "typescript": ("const n: number = 1;\n", "const n: number = ;\n"),
    "java": ("class A { void b() { int x = 1; } }\n", "class A { void b() { int x = 1 } }\n"),
    "cpp": ("int main() { return 0; }\n", "int main() { return 0 }\n"),
    "html": ("<div><p>Hi</p></div>\n", "<div <p>\n"),
    "css": ("body { color: red; }\n", "body { color: red; \n"),
}  # fmt: skip
GAME = """
const game = AVEN.createGame({ width: 320, height: 200 });
game.scene("play", {
  update(g, dt) { g.state.x = (g.state.x || 0) + dt; },
  draw(g) { g.clear(); g.rect(10, 10, 20, 20, "#fff"); },
});
game.start("play");
"""


def _check(name: str, func) -> dict:
    try:
        detail = func()
        return {"check": name, "ok": True, "detail": detail}
    except Exception as exc:
        return {"check": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()}


def _catalog() -> str:
    from app.config.catalog import catalog

    c = catalog()
    return f"{len(c.models)} models, {len(c.categories)} categories, {len(c.releases)} releases"


def _checker(language: str):
    def run() -> str:
        from app.code.validation import validate_reply

        good, bad = SAMPLES[language]
        ok = validate_reply(f"{FENCE}{language}\n{good}{FENCE}", (language,))
        broken = validate_reply(f"{FENCE}{language}\n{bad}{FENCE}", (language,))
        assert ok.checked and not ok.errors, f"correct {language} was rejected: {ok.findings}"
        assert broken.errors, f"broken {language} was not detected"
        return "detects syntax errors"

    return run


def _studio() -> str:
    from app.studio.page import build_page
    from app.studio.validate import validate_game

    report = validate_game(GAME)
    assert report.ok, report.errors
    assert not validate_game(GAME.replace("g.clear(); g.rect", "g.nope();")).ok
    assert "Content-Security-Policy" in build_page("t", GAME)
    return "; ".join(report.checks)


def _entitlements() -> str:
    import base64
    import datetime as dt

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.account.entitlements import has_entitlement

    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    now = dt.datetime.now(dt.UTC)
    payload = json.dumps(
        {"v": 1, "account": "acc_1", "entitlements": ["aven_code"], "issued": now.isoformat(),
         "expires": (now + dt.timedelta(hours=1)).isoformat()}
    ).encode()  # fmt: skip
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    token = f"{b64(payload)}.{b64(key.sign(payload))}"
    assert has_entitlement("aven_code", token, public, "acc_1")
    assert not has_entitlement("aven_code", token, public, "acc_2")
    return "Ed25519 verification works"


def main(argv: list[str]) -> int:
    target = Path(argv[argv.index("--self-test") + 1]) if len(argv) > argv.index("--self-test") + 1 else None
    results = [_check("catalog", _catalog)]
    results += [_check(f"checker:{language}", _checker(language)) for language in SAMPLES]
    results += [_check("studio sandbox and engine", _studio), _check("entitlements", _entitlements)]
    from app.version import __version__

    report = {"version": __version__, "ok": all(r["ok"] for r in results), "results": results}
    text = json.dumps(report, indent=2)
    if target is not None:
        target.write_text(text, encoding="utf-8")
    elif sys.stdout is not None:
        print(text)
    return 0 if report["ok"] else 1
