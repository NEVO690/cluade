"""List candidate GGUF model files on Hugging Face with the data needed to pin them.

Prints, for each candidate repository, the current commit and every matching GGUF file
with its size and SHA-256 (from the Hub's LFS metadata). Also lists recent model
families so newer releases are not missed. Used by CI; needs internet access.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

API = "https://huggingface.co/api"
CANDIDATES = {
    "Qwen/Qwen3-14B-GGUF": ("Q4_K_M",),
    "ggml-org/Qwen3-14B-GGUF": ("Q4_K_M",),
    "Qwen/Qwen3-1.7B-GGUF": ("Q8_0",),
    "ggml-org/Qwen3-1.7B-GGUF": ("Q8_0", "Q4_K_M"),
    "ggml-org/Qwen3-4B-Instruct-2507-GGUF": ("Q4_K_M", "Q8_0"),
    "unsloth/Qwen3-4B-Instruct-2507-GGUF": ("Q4_K_M",),
    "lmstudio-community/Qwen3-4B-Instruct-2507-GGUF": ("Q4_K_M",),
    "Qwen/Qwen3-4B-Instruct-2507-GGUF": ("Q4_K_M",),
}


def get(path: str) -> object:
    with urllib.request.urlopen(f"{API}/{path}", timeout=60) as response:  # noqa: S310 - fixed https host
        return json.load(response)


def main() -> int:
    for repo, quants in CANDIDATES.items():
        try:
            info = get(f"models/{repo}")
            files = get(f"models/{repo}/tree/{info['sha']}")
        except Exception as exc:  # report and continue
            print(f"{repo}: not available ({type(exc).__name__}: {exc})")
            continue
        print(f"{repo} @ {info['sha']} license={info.get('cardData', {}).get('license')}")
        for entry in files:
            name = entry.get("path", "")
            if name.endswith(".gguf") and any(q.lower() in name.lower() for q in quants):
                lfs = entry.get("lfs") or {}
                print(f"  {name} size={lfs.get('size', entry.get('size'))} sha256={lfs.get('oid')}")
    for author in ("Qwen", "ggml-org"):
        query = urllib.parse.urlencode({"author": author, "sort": "lastModified", "direction": -1, "limit": 40})
        names = [m["id"] for m in get(f"models?{query}")]
        print(f"recent {author}: " + ", ".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
