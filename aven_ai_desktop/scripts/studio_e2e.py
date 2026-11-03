"""Real Made With AVEN run on an on-device model (CI; needs internet for the model download).

Describes a game, runs the full pipeline (plan, code, checks, repairs) with the real
engine and model, and writes the result (plan, code, page, report) to an output folder.
Exits with 0 only when the final game passed every check.

    python scripts/studio_e2e.py aven-core out/
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.base_provider import ChatMessage, ChatRequest  # noqa: E402
from app.ai.local_provider import LocalProvider  # noqa: E402
from app.local.downloader import download_model  # noqa: E402
from app.local.engine import LocalEngine  # noqa: E402
from app.local.models import LOCAL_MODELS  # noqa: E402
from app.studio.page import build_page  # noqa: E402
from app.studio.pipeline import GamePipeline  # noqa: E402

DESCRIPTION = (
    "A top-down arcade game: the player is a small ship that moves with the arrow keys, collects glowing "
    "coins, and avoids red enemies that drift toward it. Show the score, and restart with R after a hit."
)


def main(model_id: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    local = LOCAL_MODELS[model_id]
    download_model(local.file, progress=lambda done, total: None)
    engine = LocalEngine()
    provider = LocalProvider(engine)
    started = time.monotonic()

    def complete(system, user, max_tokens, on_text):
        t = time.monotonic()
        request = ChatRequest(model=model_id, system_prompt=system, messages=[ChatMessage("user", user)],
                              max_tokens=max_tokens)  # fmt: skip
        text = "".join(e.text for e in provider.stream_chat(request) if e.kind == "text")
        print(f"   AI reply: {len(text):,} characters in {time.monotonic() - t:.0f}s", flush=True)
        return text

    try:
        pipeline = GamePipeline(complete, lambda message: print(f"-> {message}", flush=True))
        plan = pipeline.plan(DESCRIPTION)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        result = pipeline.build(plan)
    finally:
        engine.stop()
    for index, attempt in enumerate(result.attempts, start=1):
        state = "passed" if attempt.report.ok else "failed: " + " | ".join(attempt.report.errors)[:400]
        print(f"attempt {index}: {state}")
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "game.js").write_text(result.code, encoding="utf-8")
    (out / "index.html").write_text(build_page(str(plan.get("title", "game")), result.code), encoding="utf-8")
    summary = {"model": model_id, "validated": result.validated, "attempts": len(result.attempts),
               "errors": result.report.errors, "checks": result.report.checks,
               "minutes": round((time.monotonic() - started) / 60, 1)}  # fmt: skip
    (out / "report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("STUDIO " + json.dumps(summary))
    return 0 if result.validated else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], Path(sys.argv[2])))
