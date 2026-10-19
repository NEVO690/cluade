"""Stand-in for llama.cpp's llama-server, used by the engine tests.

Accepts the same command-line flags, requires the API key, reports /health,
and streams OpenAI-style chunks that echo the loaded model file and whether
thinking was enabled.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("-m")
parser.add_argument("--host")
parser.add_argument("--port", type=int)
parser.add_argument("-c")
parser.add_argument("--jinja", action="store_true")
parser.add_argument("--api-key")
args = parser.parse_args()

if Path(args.m).name.startswith("crash"):
    print("error: failed to load model", file=sys.stderr, flush=True)
    sys.exit(1)

STARTED = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep test output quiet
        pass

    def do_GET(self):
        if self.path == "/health":
            ready = time.monotonic() - STARTED > 0.3  # simulate model loading
            self.send_response(200 if ready else 503)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}' if ready else b'{"status":"loading"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.headers.get("Authorization") != f"Bearer {args.api_key}":
            self.send_response(401)
            self.end_headers()
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        thinking = body.get("chat_template_kwargs", {}).get("enable_thinking")
        user = body["messages"][-1]["content"]
        parts = [f"model={Path(args.m).name} ", f"thinking={thinking} ", f"echo={user}"]
        if user == "sampling":
            parts = [f"temperature={body.get('temperature')} top_p={body.get('top_p')} top_k={body.get('top_k')}"]
        if user == "think-tags":
            parts = ["<think>secret ", "reasoning</think>", "\n\nVisible answer"]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for part in parts:
            chunk = {
                "id": "x",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "local",
                "choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        end = {
            "id": "x",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "local",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        self.wfile.write(f"data: {json.dumps(end)}\n\ndata: [DONE]\n\n".encode())


ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
