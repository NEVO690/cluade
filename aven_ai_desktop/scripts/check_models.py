"""Real check of on-device models (used in CI; needs internet and disk for the downloads).

For each AVEN model given, downloads its file with the app's verified downloader, starts
the bundled llama-server and asks short questions, printing the replies, the speed, and
whether the chat template supports turning thinking off.

    python scripts/check_models.py aven-light aven-core aven-2
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.base_provider import ChatMessage, ChatRequest  # noqa: E402
from app.ai.local_provider import LocalProvider  # noqa: E402
from app.local.downloader import download_model  # noqa: E402
from app.local.engine import LocalEngine  # noqa: E402
from app.local.models import LOCAL_MODELS  # noqa: E402

QUESTIONS = (
    ("What is the capital of France? Answer in one word.", ("paris",)),
    ("כמה זה 15% מ-240? ענה במספר בלבד.", ("36",)),
    ("Write a one-line Python expression that reverses a string s.", ("[::-1]", "reversed(s)")),
)


def main(models: list[str]) -> int:
    failures = 0
    for model_id in models:
        local = LOCAL_MODELS[model_id]
        print(f"== {model_id}: {local.file.label} ({local.file.size_text})", flush=True)
        download_model(local.file, progress=lambda done, total: None)
        engine = LocalEngine()
        provider = LocalProvider(engine)
        try:
            for question, expected in QUESTIONS:
                request = ChatRequest(
                    model=model_id, system_prompt="You are AVEN, a helpful assistant.",
                    messages=[ChatMessage("user", question)], max_tokens=600,
                )  # fmt: skip
                started = time.monotonic()
                try:
                    reply = "".join(e.text for e in provider.stream_chat(request) if e.kind == "text")
                except Exception as exc:
                    print(f"  ERROR {type(exc).__name__}: {exc}")
                    failures += 1
                    continue
                ok = any(e in reply.lower() for e in expected) and "<think>" not in reply
                failures += not ok
                seconds = time.monotonic() - started
                print(f"  [{'OK' if ok else 'FAIL'}] {seconds:.1f}s {question}\n  {reply.strip()[:300]}")
            props = urllib.request.Request(
                f"http://127.0.0.1:{engine.port}/props", headers={"Authorization": f"Bearer {engine.token}"}
            )
            with urllib.request.urlopen(props, timeout=30) as response:  # noqa: S310 - loopback
                template = json.load(response).get("chat_template", "")
            print(f"  template mentions enable_thinking: {'enable_thinking' in template}")
        finally:
            engine.stop()
    print(f"{failures} failed checks")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or list(LOCAL_MODELS)))
