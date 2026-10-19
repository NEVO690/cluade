"""Print a before/after table from run_eval.py result files.

python evals/compare.py results/   # reads every *.json in the folder
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ORDER = ["aven-1-1", "aven-ultra", "aven-core", "aven-light"]
METRICS = [
    ("Cases passed", lambda s: f"{s['passed']}/{s['total']}"),
    ("Replies with language problems", lambda s: s["language_problem_replies"]),
    ("Hebrew misspellings / 100 words", lambda s: s["hebrew_misspelled_per_100"]),
    ("English misspellings / 100 words", lambda s: s["english_misspelled_per_100"]),
    ("Median reply time (s)", lambda s: s["median_seconds"]),
    ("Median time to first text (s)", lambda s: s["median_first_text_seconds"]),
    ("Tokens per second", lambda s: s["tokens_per_second"]),
    ("System prompt tokens", lambda s: s["system_prompt_tokens"]),
]


def main(folder: str) -> int:
    reports: dict[tuple[str, str], dict] = {}
    for path in Path(folder).rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        reports[(data["model"], data["label"])] = data
    lines = ["## AVEN model evaluation: baseline vs current\n"]
    for model in [m for m in ORDER if any(k[0] == m for k in reports)]:
        base, cur = reports.get((model, "baseline")), reports.get((model, "current"))
        name = (cur or base)["model_name"]
        lines += [f"### {name}\n", "| Metric | Baseline | Current |", "|---|---|---|"]
        for label, get in METRICS:
            lines.append(
                f"| {label} | {get(base['summary']) if base else '–'} | {get(cur['summary']) if cur else '–'} |"
            )
        categories = sorted(
            set((base or {}).get("summary", {}).get("categories", {}))
            | set((cur or {}).get("summary", {}).get("categories", {}))
        )
        for category in categories:
            b = base["summary"]["categories"].get(category, "–") if base else "–"
            c = cur["summary"]["categories"].get(category, "–") if cur else "–"
            lines.append(f"| · {category} | {b} | {c} |")
        if base and cur:
            before = {r["id"]: r["passed"] for r in base["results"]}
            fixed = [r["id"] for r in cur["results"] if r["passed"] and before.get(r["id"]) is False]
            broke = [r["id"] for r in cur["results"] if not r["passed"] and before.get(r["id"]) is True]
            lines.append(
                f"\nNewly passing: {', '.join(fixed) or 'none'}  \nNewly failing: {', '.join(broke) or 'none'}\n"
            )
        lines.append("")
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "results"))
