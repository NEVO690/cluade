# AVEN Cloud

AVEN Cloud is the AVEN AI server. It lets people use **AVEN AI Desktop without an API key**.

```
AVEN AI Desktop ──HTTPS──▶ AVEN Cloud (your server, holds the key) ──HTTPS──▶ AI service
```

The **key stays on the server** in an environment variable. It is never in the app, so it can't be pulled out of the `.exe`.

## Which AI service? (free options first)

| Service | Cost | Key from | Env variable |
|---|---|---|---|
| **Groq** (recommended) | **Free tier**, no credit card | <https://console.groq.com> → API Keys | `GROQ_API_KEY` |
| **Google Gemini** | **Free tier** | <https://aistudio.google.com> → Get API key | `GEMINI_API_KEY` |
| Anthropic (Claude) | Paid | <https://platform.claude.com> | `ANTHROPIC_API_KEY` |
| Any OpenAI-compatible service | Varies | - | `AVEN_UPSTREAM=openai_compatible`, `AVEN_UPSTREAM_API_KEY`, `AVEN_UPSTREAM_BASE_URL`, and the four `AVEN_*_MODEL` variables |

The server uses whichever key you set. With several keys, set `AVEN_UPSTREAM` (`groq`, `gemini` or `anthropic`).

**About free tiers:** they are free but **limited**. Groq allows roughly 30 requests per minute and a daily cap per model. All of your users **share** that limit, because they all use your one key. When it runs out, users see "AVEN Cloud is very busy" until the limit resets. Check each service's console for the current limits. Free tiers may also let the service use the content it receives, so read their terms and mention this in your privacy policy.

## How AVEN models are mapped

Free services rename models often, so for each AVEN model the server asks the service which models exist and **automatically picks the best available one**. There's nothing to update when a model is renamed.

| AVEN model | Groq (free) | Gemini (free) | Anthropic (paid) |
|---|---|---|---|
| AVEN 2.0 | `openai/gpt-oss-120b`, else the newest 70B model | newest Flash | `claude-opus-5-5` with deeper reasoning |
| AVEN Ultra | `openai/gpt-oss-120b` | newest Flash | `claude-opus-5-5` with extra-deep reasoning |
| AVEN Core | `llama-3.3-70b-versatile`, else the newest 70B model | newest Flash | `claude-sonnet-5-5` |
| AVEN Light | `llama-3.1-8b-instant`, else the newest 8B model | newest Flash-Lite | `claude-haiku-5-5` |

Requests for `aven-1` (AVEN 1.0, from older app versions) are served by AVEN 2.0.

To pin an exact model, set `AVEN_2_MODEL`, `AVEN_ULTRA_MODEL`, `AVEN_CORE_MODEL` or `AVEN_LIGHT_MODEL`. Check `GET /health` to see which service is active.

## Free deployment: Groq + Render (about 15 minutes, $0)

1. **Get a free Groq key.** Sign up at <https://console.groq.com>, open **API Keys**, and create a key.
2. **Deploy the server.** At <https://render.com> (free account), choose **New → Blueprint**, select this GitHub repository, and paste the Groq key when Render asks for `GROQ_API_KEY`. It is stored as a secret on Render, never in git.
3. **Check it.** Open `https://<your-service>.onrender.com/health`. It should show `"configured": true, "service": "groq"`.
4. **Connect the app.** In GitHub, go to **Settings → Secrets and variables → Actions → Variables** and add `AVEN_CLOUD_URL` = `https://<your-service>.onrender.com`.
5. **Rebuild.** Open the **Actions** tab → *Build AVEN AI Desktop (Windows)* → **Run workflow**. Every copy of the new `.exe` chats with no setup.

Render's free plan puts the server to sleep after a period with no traffic. The first message after a quiet period can take up to about a minute while it wakes up.

The same Docker image runs on any host (Railway, Fly.io, a VPS, and others):

```bash
docker build -t aven-cloud aven_cloud
docker run -p 8000:8000 -e GROQ_API_KEY=gsk_... aven-cloud
```

## Configuration

All settings are environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | - | **One is required.** Key for the AI service. |
| `AVEN_UPSTREAM` | auto | `groq`, `gemini`, `anthropic` or `openai_compatible` |
| `AVEN_2_MODEL` / `AVEN_ULTRA_MODEL` / `AVEN_CORE_MODEL` / `AVEN_LIGHT_MODEL` | automatic | Pin the exact model behind each AVEN model |
| `AVEN_REQUESTS_PER_MINUTE` | 10 | Messages per install per minute |
| `AVEN_REQUESTS_PER_DAY` | 100 | Messages per install per day |
| `AVEN_IP_REQUESTS_PER_MINUTE` | 30 | Messages per IP address per minute |
| `AVEN_MAX_CONCURRENT` | 10 | Replies generated at the same time |
| `AVEN_MAX_OUTPUT_TOKENS` | 8000 | Longest reply allowed |
| `AVEN_MAX_INPUT_CHARS` | 400000 | Longest conversation accepted |
| `AVEN_TRUST_PROXY` | false | Read the client IP from `X-Forwarded-For`. Enable only behind a trusted proxy, as on Render. |

The limits live in memory, so run **one** instance with one worker; the Dockerfile already does this. They are a fair-use guard, not strong security: someone determined could rotate install IDs and IP addresses. On a free tier the worst case is that the shared daily quota runs out. On a paid service, set a spend limit in its console.

## AVEN CODE subscriptions (Stripe)

AVEN CODE is the paid category. This server is the only place payments are verified:

- **Accounts.** The desktop app creates an anonymous AVEN AI account (`POST /v1/accounts`) and keeps its token in the operating system's credential store. The server stores only a SHA-256 hash of the token.
- **Checkout.** `POST /v1/billing/checkout` creates a Stripe Checkout session for the configured price and returns Stripe's URL. The app opens it in the browser and never sees card details or Stripe keys.
- **Webhooks.** `POST /v1/billing/webhook` accepts only events with a valid Stripe signature (`STRIPE_WEBHOOK_SECRET`). Each event is processed once, and the subscription's current state is always re-read from Stripe, so out-of-order or replayed events cannot restore a cancelled subscription.
- **Access.** Only `active` and `trialing` subscriptions with a current period grant access. `past_due` (failed payment), `unpaid`, `canceled` and expired periods do not. A subscription set to cancel at period end keeps access until that date.
- **Enforcement.** Every chat request is checked on the server: AVEN CODE requests (header `X-AVEN-Category: code`) without an active subscription get HTTP 402. `GET /v1/account` also returns the entitlements signed with an Ed25519 key, which the app verifies with the public key before it unlocks AVEN CODE for on-device or personal-key use.
- **Management.** `POST /v1/billing/portal` opens Stripe's customer portal (update card, cancel).

| Variable | Meaning |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_test_...` for test mode (no real charges), `sk_live_...` for live mode |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` of the webhook endpoint `https://<server>/v1/billing/webhook` (events: `checkout.session.completed`, `customer.subscription.created/updated/deleted`, `invoice.payment_failed`) |
| `STRIPE_PRICE_AVEN_CODE` | The Price id (`price_...`) of the AVEN CODE subscription. **The price is set in Stripe**, not in code; the app shows what Stripe reports. |
| `AVEN_ENTITLEMENT_SIGNING_KEY` | Private key from `python scripts/new_signing_key.py`. Its public key goes into the desktop build as `AVEN_ENTITLEMENT_PUBLIC_KEY`. |
| `AVEN_PUBLIC_URL` | This server's public `https://` address (Stripe's return pages) |
| `AVEN_BILLING_DB` | SQLite file for accounts and subscriptions. **Put it on a persistent disk**: on Render that needs a paid instance with a disk mounted at `/var/data`. On the free plan it is lost on restart. |

Billing stays off (`GET /v1/billing/config` reports `enabled: false`, AVEN CODE stays locked) until all of the first four are set. Test the whole flow in Stripe test mode with the test card `4242 4242 4242 4242` before switching to live keys.

Limitation: accounts are anonymous and tied to one computer's credential store. Moving a subscription to a new computer needs a sign-in system, which is not built yet.

## Run locally

```bash
cd aven_cloud
pip install -r requirements.txt
GROQ_API_KEY=gsk_... uvicorn server:app --port 8000
# In another terminal, run the desktop app against it:
AVEN_CLOUD_URL=http://localhost:8000 python ../aven_ai_desktop/main.py
```

## Tests

```bash
pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

The tests mock the AI services at the HTTP level, so they need no key and no network. They cover:
- Groq, Gemini and Anthropic
- automatic model selection, including renamed models
- streaming, validation, rate limits and error mapping
- an end-to-end test where the desktop app's real provider code chats with a running server over HTTP
- accounts, Stripe checkout (mocked), signed webhooks (real signature verification), failed payments, cancellations, replayed and out-of-order events, server-side AVEN CODE checks, and the desktop app verifying signed entitlements

## Privacy

Users' messages pass through this server to the AI service it runs on. The server keeps no conversations: only in-memory rate-limit counters and, when billing is on, account ids, token hashes and subscription status. Its logs record only the model name and a shortened hash of the client id. If you publish AVEN Cloud, your website's privacy policy should say that conversations are processed by your server and by that AI service, under that service's terms.
