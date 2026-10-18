# AVEN Cloud

AVEN Cloud is the AVEN AI server. It lets people use **AVEN AI Desktop without an API key**.

```
AVEN AI Desktop ──HTTPS──▶ AVEN Cloud (your server, holds the key) ──HTTPS──▶ Anthropic (Claude)
```

- The **Anthropic API key stays on the server** in an environment variable. It is never in the app, so it can't be pulled out of the `.exe`.
- The server maps the four AVEN models to Claude models:

  | AVEN model | Claude model |
  |---|---|
  | AVEN 1.0 | `claude-opus-5-5` |
  | AVEN Ultra | `claude-opus-5-5`, with extra-deep reasoning (`effort: xhigh`) |
  | AVEN Core | `claude-sonnet-5-5` |
  | AVEN Light | `claude-haiku-5-5` |

- It exposes an OpenAI-compatible API: `POST /v1/chat/completions` with streaming, and `GET /v1/models`. Health checks use `GET /health`.
- **Fair-use limits** keep a free public service affordable:
  - per install, per minute and per day
  - per IP address
  - a cap on concurrent requests
  - a cap on reply length and conversation size
- It never logs message contents.

## Costs: read this first

Every message anyone sends is billed to **your** Anthropic account. Before you publish:

1. Set a **monthly spend limit** in the Claude Console (<https://platform.claude.com/>).
2. Tune the limits below. Deeper reasoning (AVEN Ultra) and longer replies cost more.
3. If you need to save money, point the AVEN models at cheaper Claude models. For example, set `AVEN_1_MODEL=claude-sonnet-5-5`.

## Deploy on Render (free tier works for testing)

1. Create an API key in the Claude Console.
2. On <https://render.com>, choose **New → Blueprint** and select this repository. Render reads `aven_cloud/render.yaml`.
3. When Render asks for `ANTHROPIC_API_KEY`, paste your key. It is stored as a secret on Render, never in git.
4. Wait for the deploy to finish, then open `https://<your-service>.onrender.com/health`. It should show `{"status":"ok","configured":true}`.
5. In GitHub, go to **Settings → Secrets and variables → Actions → Variables** and add `AVEN_CLOUD_URL` = `https://<your-service>.onrender.com`.
6. Run the **Build AVEN AI Desktop (Windows)** workflow again (**Actions** tab → *Run workflow*). The new `.exe` works out of the box, with no API key.

The same Docker image runs on any host: Railway, Fly.io, a VPS, and others.

```bash
docker build -t aven-cloud aven_cloud
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... aven-cloud
```

## Configuration

All settings are environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | - | **Required.** Your Anthropic key. |
| `AVEN_1_MODEL` / `AVEN_ULTRA_MODEL` / `AVEN_CORE_MODEL` / `AVEN_LIGHT_MODEL` | see the table above | Claude model behind each AVEN model |
| `AVEN_REQUESTS_PER_MINUTE` | 20 | Messages per install per minute |
| `AVEN_REQUESTS_PER_DAY` | 300 | Messages per install per day |
| `AVEN_IP_REQUESTS_PER_MINUTE` | 60 | Messages per IP address per minute |
| `AVEN_MAX_CONCURRENT` | 20 | Replies generated at the same time |
| `AVEN_MAX_OUTPUT_TOKENS` | 16000 | Longest reply allowed |
| `AVEN_MAX_INPUT_CHARS` | 400000 | Longest conversation accepted |
| `AVEN_TRUST_PROXY` | false | Read the client IP from `X-Forwarded-For`. Enable only behind a trusted proxy, as on Render. |

The limits live in memory, so run **one** instance with one worker; the Dockerfile already does this. They are a fair-use guard, not strong security: someone determined could rotate install IDs and IP addresses. Your Anthropic spend limit is the real backstop.

## Run locally

```bash
cd aven_cloud
pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... uvicorn server:app --port 8000
# In another terminal, run the desktop app against it:
AVEN_CLOUD_URL=http://localhost:8000 python ../aven_ai_desktop/main.py
```

## Tests

```bash
pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

The tests mock Anthropic at the HTTP level, so they need no key and no network. They cover:
- model mapping, streaming, validation, rate limits and error mapping
- an end-to-end test where the desktop app's real provider code chats with a running server over HTTP

## Privacy

Users' messages pass through this server to Anthropic. The server keeps nothing except in-memory rate-limit counters, and its logs record only the model name and a shortened hash of the install ID. If you publish AVEN Cloud, your website's privacy policy should say that conversations are processed by your server and by Anthropic.
