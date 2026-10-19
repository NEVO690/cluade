"""Real end-to-end check of AVEN Local (used in CI; needs internet and ~1.3 GB of disk).

Downloads AVEN Light's model with the app's verified downloader, starts the real
llama-server from ./engine and asks real questions, with and without thinking.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.base_provider import ChatMessage, ChatRequest  # noqa: E402
from app.ai.local_provider import LocalProvider  # noqa: E402
from app.ai.prompts import system_prompt_for  # noqa: E402
from app.local.downloader import download_model  # noqa: E402
from app.local.engine import LocalEngine  # noqa: E402
from app.local.models import LOCAL_MODELS  # noqa: E402


def ask(provider: LocalProvider, aven_model: str, question: str, mode: str = "aven") -> str:
    request = ChatRequest(
        model=aven_model,
        system_prompt=system_prompt_for(mode),
        messages=[ChatMessage("user", question)],
        max_tokens=1500,
    )
    started = time.monotonic()
    text = "".join(e.text for e in provider.stream_chat(request) if e.kind == "text")
    print(f"--- {aven_model} ({time.monotonic() - started:.1f}s): {question}\n{text}\n", flush=True)
    return text


def main() -> int:
    light = LOCAL_MODELS["aven-light"].file
    last = [0.0]

    def progress(done: int, total: int) -> None:
        if time.monotonic() - last[0] > 5 or done == total:
            last[0] = time.monotonic()
            print(f"download {done / 1e9:.2f}/{total / 1e9:.2f} GB", flush=True)

    download_model(light, progress=progress)
    engine = LocalEngine()
    if not engine.available():
        print(f"Engine binary missing: {engine.binary}")
        return 1
    provider = LocalProvider(engine)
    try:
        answer = ask(provider, "aven-light", "What is the capital of France? Answer in one word.")
        assert answer.strip(), "empty reply"
        assert "<think>" not in answer, "reasoning leaked into the reply"
        assert "paris" in answer.lower(), "unexpected answer"

        code = ask(provider, "aven-light", "Write a one-line Python expression that reverses a string s.", "code")
        assert "[::-1]" in code, "unexpected code answer"

        # Same model file with thinking mode on (as AVEN Ultra uses it): only the answer is shown.
        thinking = LocalProvider(engine)
        original = LOCAL_MODELS["aven-light"]
        LOCAL_MODELS["aven-light"] = type(original)(original.file, thinking=True)
        try:
            reasoned = ask(thinking, "aven-light", "What is 17 + 25? Reply with just the number.")
        finally:
            LOCAL_MODELS["aven-light"] = original
        assert "<think>" not in reasoned and "</think>" not in reasoned, "reasoning leaked into the reply"
        assert "42" in reasoned, "unexpected thinking-mode answer"
    finally:
        engine.stop()
    print("AVEN Local end-to-end check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
