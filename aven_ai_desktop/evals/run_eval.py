"""Evaluate an AVEN Local model with real answers from the real engine.

Runs every case in ``evals/cases.json`` through the app's own pipeline
(ChatService.build_request -> LocalProvider -> llama-server) and scores the
replies with the deterministic checks in ``evals/scoring.py``.

    python evals/run_eval.py --model aven-light --out results.json
    python evals/run_eval.py --model aven-core --app-root ../baseline --label baseline

``--app-root`` points at another checkout of the app (e.g. the previous release)
so the same cases can be compared before and after a change. Needs internet for
the one-time model download, and the engine (``scripts/fetch_engine.py``).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scoring  # noqa: E402


def tokenize_count(engine, text: str) -> int:
    if not text or engine.process is None:
        return 0
    request = urllib.request.Request(
        f"http://127.0.0.1:{engine.port}/tokenize",
        data=json.dumps({"content": text}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {engine.token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - local engine
            return len(json.load(response)["tokens"])
    except (OSError, ValueError, KeyError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="AVEN model id, e.g. aven-light")
    parser.add_argument("--app-root", default=str(HERE.parent), help="checkout of the app to evaluate")
    parser.add_argument("--label", default="current")
    parser.add_argument("--out", default="eval-results.json")
    parser.add_argument("--cases", default=str(HERE / "cases.json"))
    parser.add_argument("--only", default="", help="comma-separated case ids")
    args = parser.parse_args()

    app_root = Path(args.app_root).resolve()
    sys.path.insert(0, str(app_root))
    os.environ.setdefault("AVEN_LLAMA_SERVER", str(HERE.parent / "engine" / "llama-server"))

    from app.ai.base_provider import ChatMessage
    from app.ai.chat_service import ChatService
    from app.ai.local_provider import LocalProvider
    from app.config.aven_models import aven_model_name
    from app.config.settings import AppSettings
    from app.local.downloader import download_model
    from app.local.engine import LocalEngine
    from app.local.models import LOCAL_MODELS

    model_name = aven_model_name(args.model)
    local = LOCAL_MODELS[args.model]
    print(f"== {model_name} ({args.label}) from {app_root}", flush=True)
    download_model(local.file, progress=lambda done, total: None)

    engine = LocalEngine()
    provider = LocalProvider(engine)
    service = ChatService(AppSettings(provider="aven_local", model=args.model), credentials=None)
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    results = []
    try:
        for case in cases:
            history = [ChatMessage(role, text) for role, text in case["messages"]]
            request = service.build_request(case.get("mode", "aven"), history)
            started = time.monotonic()
            first = None
            parts: list[str] = []
            truncated = False
            error = ""
            try:
                for event in provider.stream_chat(request):
                    if event.kind == "text":
                        first = first or time.monotonic()
                        parts.append(event.text)
                    elif event.kind == "truncated":
                        truncated = True
            except Exception as exc:  # report and continue with the next case
                error = f"{type(exc).__name__}: {exc}"
            total = time.monotonic() - started
            reply = "".join(parts)
            failures = [f"error: {error}"] if error else scoring.check_case(case, reply, model_name)
            if truncated:
                failures.append("reply was cut off (length limit)")
            out_tokens = tokenize_count(engine, reply)
            he_bad, he_total = scoring.misspelled_hebrew(reply)
            en_bad, en_total = scoring.misspelled_english(reply)
            prompt_tokens = tokenize_count(engine, request.system_prompt)
            result = {
                "id": case["id"],
                "category": case["category"],
                "passed": not failures,
                "failures": failures,
                "reply": reply,
                "seconds": round(total, 2),
                "first_text_seconds": round(first - started, 2) if first else None,
                "output_tokens": out_tokens,
                "system_prompt_tokens": prompt_tokens,
                "hebrew_misspelled": he_bad,
                "hebrew_words": he_total,
                "english_misspelled": en_bad,
                "english_words": en_total,
            }
            results.append(result)
            mark = "PASS" if result["passed"] else "FAIL"
            print(f"[{mark}] {case['id']} ({total:.1f}s) {'; '.join(failures)}\n{reply.strip()}\n", flush=True)
    finally:
        engine.stop()

    summary = summarize(results)
    report = {
        "model": args.model,
        "model_name": model_name,
        "label": args.label,
        "summary": summary,
        "results": results,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY " + json.dumps({"model": args.model, "label": args.label, **summary}, ensure_ascii=False))
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(markdown_summary(model_name, args.label, summary))
    return 0


def summarize(results: list[dict]) -> dict:
    by_category: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r["passed"])
    he_bad = sum(r["hebrew_misspelled"] for r in results)
    he_words = sum(r["hebrew_words"] for r in results)
    en_bad = sum(r["english_misspelled"] for r in results)
    en_words = sum(r["english_words"] for r in results)
    seconds = [r["seconds"] for r in results]
    firsts = [r["first_text_seconds"] for r in results if r["first_text_seconds"] is not None]
    tokens = sum(r["output_tokens"] for r in results)
    language_problems = sum(
        1
        for r in results
        if any(f.startswith(("wrong language", "Chinese", "broken", "Hebrew and Latin")) for f in r["failures"])
    )
    return {
        "passed": sum(r["passed"] for r in results),
        "total": len(results),
        "categories": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_category.items())},
        "language_problem_replies": language_problems,
        "hebrew_misspelled_per_100": round(100 * he_bad / he_words, 2) if he_words else None,
        "english_misspelled_per_100": round(100 * en_bad / en_words, 2) if en_words else None,
        "median_seconds": round(statistics.median(seconds), 1) if seconds else None,
        "median_first_text_seconds": round(statistics.median(firsts), 1) if firsts else None,
        "tokens_per_second": round(tokens / sum(seconds), 1) if seconds and sum(seconds) else None,
        "system_prompt_tokens": results[0]["system_prompt_tokens"] if results else None,
    }


def markdown_summary(model_name: str, label: str, s: dict) -> str:
    rows = "\n".join(f"| {k} | {v} |" for k, v in s["categories"].items())
    return (
        f"### {model_name} — {label}: {s['passed']}/{s['total']} passed\n\n| Category | Passed |\n|---|---|\n{rows}\n\n"
        f"- Replies with language problems: {s['language_problem_replies']}\n"
        f"- Hebrew misspellings per 100 words (hspell): {s['hebrew_misspelled_per_100']}\n"
        f"- English misspellings per 100 words (aspell): {s['english_misspelled_per_100']}\n"
        f"- Median reply time: {s['median_seconds']} s (first text after {s['median_first_text_seconds']} s), "
        f"{s['tokens_per_second']} tokens/s\n- System prompt: {s['system_prompt_tokens']} tokens\n\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
