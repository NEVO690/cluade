# AVEN model evaluation

A repeatable check of answer quality for AVEN 1.1, AVEN Ultra, AVEN Core and AVEN Light.

- **Real answers**: each case goes through the app's own pipeline (`ChatService.build_request` → `LocalProvider` → the bundled llama.cpp engine) with the real on-device model.
- **Deterministic scoring** (`scoring.py`), no AI judge: expected facts and final answers, reply language, leaked foreign characters, broken mixed-script words, claimed actions the app cannot perform (searching, browsing, running code), invented links, exact formats (bullet count, one word, valid JSON), and the official model names.
- **Spelling** is measured separately with `hspell` (Hebrew) and `aspell` (English), as misspellings per 100 words. These checkers also flag rare words and names, so compare the numbers between versions; don't read them as an absolute error rate.
- **Speed**: median reply time, time to the first visible text, and tokens per second. AVEN Local costs nothing per request; cost per request only applies to cloud providers and is not measured here.

## Cases

`cases.json` has 29 cases in Hebrew and English: friendliness, language quality, factual questions, math, logic, contradiction detection, instruction following, current information (which the app cannot look up), requests to search the web or open a file, hallucination traps (a paper and a book that do not exist), multi-turn context, model identity and code.

## Running

```bash
python scripts/fetch_engine.py --platform linux-x64     # once
sudo apt-get install hspell aspell aspell-en             # optional, for spelling numbers
python evals/run_eval.py --model aven-1-1 --out results/aven-1-1-current.json
python evals/run_eval.py --model aven-1-1 --app-root ../old-checkout/aven_ai_desktop --label baseline \
    --out results/aven-1-1-baseline.json
python evals/compare.py results
```

The first run downloads the model (1.3 to 5 GB). The CI workflow `.github/workflows/evaluate-aven-models.yml` runs all four models on the baseline release and on the current code in parallel, and prints the comparison in the run summary.

## Reading the results

Replies are sampled, so the same code can score a few cases differently from run to run: three runs of the unchanged 1.1.0 baseline gave AVEN 1.1 scores of 21, 24 and 20 out of 29. Compare against several baseline runs before calling a change an improvement.
