"""Temporary probe: prints llama.cpp release assets and GGUF model files (size + sha256)."""
import json
import urllib.request


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "aven-probe"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


rel = get("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest")
print("LLAMA_TAG", rel["tag_name"])
for a in rel["assets"]:
    if any(k in a["name"] for k in ("win-cpu", "win-vulkan", "ubuntu-x64", "macos-arm64")):
        print("ASSET", a["name"], a["size"], a.get("digest"))

print("SEARCH")
for m in get("https://huggingface.co/api/models?search=GGUF&author=Qwen&sort=downloads&limit=25"):
    print("  QWEN", m["id"], m.get("downloads"))
for m in get("https://huggingface.co/api/models?search=GGUF&author=ggml-org&sort=downloads&limit=40"):
    print("  GGML", m["id"], m.get("downloads"))

for repo in ["Qwen/Qwen3-1.7B-GGUF", "Qwen/Qwen3-4B-GGUF", "Qwen/Qwen3-8B-GGUF",
             "ggml-org/Qwen3-1.7B-GGUF", "ggml-org/Qwen3-4B-GGUF", "ggml-org/Qwen3-8B-GGUF",
             "unsloth/Qwen3-1.7B-GGUF", "unsloth/Qwen3-4B-GGUF", "unsloth/Qwen3-8B-GGUF",
             "ggml-org/gemma-3-1b-it-GGUF", "ggml-org/gemma-3-4b-it-GGUF"]:
    try:
        info = get(f"https://huggingface.co/api/models/{repo}")
        sha = info["sha"]
        tree = get(f"https://huggingface.co/api/models/{repo}/tree/{sha}")
        print("REPO", repo, sha, info.get("cardData", {}).get("license"))
        for f in tree:
            if f["path"].endswith(".gguf") and any(q in f["path"] for q in ("Q4_K_M", "Q8_0", "q4_k_m", "q8_0")):
                print("  FILE", f["path"], f["size"], (f.get("lfs") or {}).get("oid"))
    except Exception as e:
        print("REPO", repo, "ERROR", e)
