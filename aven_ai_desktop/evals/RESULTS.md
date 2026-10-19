# Evaluation results: AVEN 1.2.0 vs 1.1.0

Measured with this suite (29 cases) in GitHub Actions on `ubuntu-latest` (4 CPU cores), real on-device models,
19 October 2026. Each number is the cases passed in one run. Replies are sampled, so the same code varies between
runs; the baseline was run several times to show that spread.

| Model | 1.1.0 baseline runs | 1.2.0 runs | Replies with language problems (baseline → 1.2.0) |
|---|---|---|---|
| **AVEN 1.1** | 21, 24, 20, 20, 22 | 26, 26 | 2–3 per run → 0, 0 |
| **AVEN Core** | 21, 21, 21, 21, 19 | 26, 26 | 0–5 per run → 1, 0 |
| **AVEN Light** | 18, 20, 19, 17 | 20, 16, 21 | 4–7 per run → 1–4 |
| **AVEN Ultra** | 24, 24 | 25 (round 1) | 3 → 2 |

"Language problems" are replies with characters from another writing system (Chinese, Korean, Cyrillic, Arabic,
Greek), Hebrew and Latin letters glued into one word, or the wrong reply language. The 1.2.0 runs for AVEN 1.1 and
Core are from the final code (rounds 2 and 3); Light's are rounds 2, 3 and the final run.

## What changed per category

- **Identity** (does the model know which AVEN model it is): 0/2 in every baseline run for every model; 2/2 for 1.1,
  Core and Light in 1.2.0. The baseline prompt never told the model its name.
- **Current information** (news, prices): 1.2.0 says it cannot check current information more consistently.
  AVEN Light still sometimes invents news.
- **Logic**: 1.1 and Core improved most (bat-and-ball, prime check): calculations are now worked out before the answer.
- **Hallucination traps** (a paper and a book that do not exist): 1.1 and Ultra admit they don't know; Core is mixed;
  **Light still invents content** in most runs.

## Speed and cost

- The 1.2.0 system prompt is about 790 tokens instead of 307. The engine caches it, so it is processed once per
  conversation; time to first text rose by about 0.3 s for Light and Core, and was unchanged for 1.1.
- Median reply time on the 4-core runner: Light about 2.5 s, Core 7 to 9 s, AVEN 1.1 about 12 s, Ultra about 40 to 60 s.
- AVEN Local has no per-request cost.

## Still failing in 1.2.0 (known weaknesses)

- **Arithmetic slips** in the direct-answer models: AVEN 1.1 computed $68 + $6.80 = $81.60 in several runs. Core once
  answered 37 × 43 with a wrong number. A calculator tool would fix this; the app has none yet.
- **Contradiction detection**: no direct-answer model noticed that "born in 1990" and "50 in 2025" disagree; Ultra did.
- **AVEN Light**: wrong facts in Hebrew (capital of Japan, author of Harry Potter), invented papers, books and news,
  and some English words inside Hebrew replies. These come from the 1.7B model's size, not from the app.
- **Hebrew spelling** varies a lot between runs (hspell, 1.6 to 6.4 misspellings per 100 words across all runs) and
  shows no clear trend.
