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
SEARCHES = ("Qwen3.5", "Qwen3.6", "gemma-4", "Qwen3.8")
CANDIDATES = {
    "ggml-org/Qwen3.5-0.8B-GGUF": ("Q8_0", "Q4_K_M"),
    "ggml-org/Qwen3.5-2B-GGUF": ("Q8_0", "Q4_K_M"),
    "ggml-org/Qwen3.5-4B-GGUF": ("Q8_0", "Q4_K_M"),
    "ggml-org/Qwen3.5-9B-GGUF": ("Q4_K_M", "Q8_0"),
    "Qwen/Qwen3.5-2B-GGUF": ("Q8_0", "Q4_K_M"),
    "Qwen/Qwen3.5-4B-GGUF": ("Q4_K_M",),
    "Qwen/Qwen3.5-9B-GGUF": ("Q4_K_M",),
    "unsloth/Qwen3.5-2B-GGUF": ("Q8_0", "Q4_K_M"),
    "unsloth/Qwen3.5-4B-GGUF": ("Q4_K_M",),
    "unsloth/Qwen3.5-9B-GGUF": ("Q4_K_M",),
    "ggml-org/gemma-4-12B-it-GGUF": ("Q4_K_M",),
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
    for term in SEARCHES:
        query = urllib.parse.urlencode(
            {"search": term, "filter": "gguf", "sort": "downloads", "direction": -1, "limit": 40}
        )
        print(f"gguf search {term!r}: " + ", ".join(m["id"] for m in get(f"models?{query}")))
    for author in ("Qwen", "ggml-org"):
        query = urllib.parse.urlencode({"author": author, "sort": "lastModified", "direction": -1, "limit": 40})
        names = [m["id"] for m in get(f"models?{query}")]
        print(f"recent {author}: " + ", ".join(names))
    # The newest llama.cpp release, in case a newer model needs a newer engine.
    with urllib.request.urlopen("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1", timeout=60) as r:
        release = json.load(r)[0]
    print(f"llama.cpp latest: {release['tag_name']} ({release['published_at']})")
    for asset in release["assets"]:
        if asset["name"].endswith(("bin-win-cpu-x64.zip", "bin-ubuntu-x64.tar.gz")):
            print(f"  {asset['name']} size={asset['size']} digest={asset.get('digest')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
