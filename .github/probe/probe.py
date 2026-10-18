"""Temporary probe: lists llama.cpp release assets."""
import json
import urllib.request


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "aven-probe"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


for rel in get("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=3"):
    print("TAG", rel["tag_name"], rel["published_at"], "prerelease" if rel["prerelease"] else "")
    for a in rel["assets"]:
        print("  ASSET", a["name"], a["size"], a.get("digest"))
