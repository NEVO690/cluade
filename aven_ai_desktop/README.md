# AVEN AI Desktop

AVEN AI Desktop is a Windows desktop AI app written in Python (PySide6). It has two modes:

- **AVEN** is a friendly general-purpose assistant for questions, explanations, brainstorming, writing, summaries, learning, planning and everyday problem-solving.
- **AVEN CODE** is a programming assistant for writing, debugging, explaining, refactoring and reviewing code. It knows Python, JavaScript/TypeScript, HTML/CSS, Roblox Luau, Unity C#, Unreal Engine C++, Java, C#, SQL and more.

Responses come from the AI provider you configure. Right now that's **Anthropic (Claude)**, **OpenAI**, or any **OpenAI-compatible server** (including local model servers on `localhost`). The app never makes up responses: if no provider is configured, it shows a setup screen.

| Dark theme, AVEN CODE | Light theme, first launch |
|---|---|
| ![AVEN CODE in dark theme](docs/screenshot-dark-code.png) | ![First launch setup in light theme](docs/screenshot-light-setup.png) |

*The screenshots were taken with a mock provider in an offscreen test harness.*

Version: **1.0.0** (defined in `app/version.py`)

---

## AVEN models

You choose between AVEN's own model lineup, separately for each mode (**Settings → General**):

| AVEN model | Best for | Default mapping (Anthropic) |
|---|---|---|
| **AVEN Swift** | Fastest replies for everyday questions | `claude-haiku-5-5` |
| **AVEN Core** | Balanced speed and quality | `claude-sonnet-5-5` |
| **AVEN Ultra** (default) | Complex reasoning, writing and code | `claude-opus-5-5` |

The chat interface only shows AVEN names. Each AVEN model runs on a real model at the provider you configured, and you can change that mapping in **Settings → AI Provider → Advanced**. OpenAI and compatible servers have no default mapping, so you enter model IDs or use **Load available models**. AVEN AI does not train its own model. Settings and the privacy notice state which provider processes conversations, and the assistant answers truthfully if asked what powers it.

## Features

- Sidebar with branding, a **New conversation** button, search, and history grouped by date (Today, Yesterday, …)
- Each conversation has its own **mode**. You can switch modes from the header at any time; the system instructions change from the next reply.
- **Streamed responses**, with a *thinking…* indicator, a **Stop** button (or `Esc`), **Retry** after errors and **Regenerate**
- **Markdown** rendering: headings, lists, tables, links and inline code
- **Code blocks** with syntax highlighting (Pygments) and a **Copy code** button. You can also copy whole messages.
- **Local history** in SQLite: create, rename, delete, load earlier messages on demand in long conversations, and delete everything
- **Settings**: theme (match Windows / light / dark), the AVEN model for each mode, provider, API key, the provider model behind each AVEN model, loading the list of models your key can use, a real **connection test**, max response length and timeout
- **Clear errors** for a missing or invalid key, unknown models, rate limits, timeouts, network failures, provider outages and declined requests
- The window stays responsive: network calls run on background threads and streamed text is batched for rendering

## Requirements

- Windows 11 (Windows 10 should also work, but Windows 11 is the main target)
- **End users** of a packaged release don't need anything else. Python is bundled.
- **Developers** need Python 3.11+ (3.12 recommended for Windows builds)
- An account and API key with a supported AI provider. A local OpenAI-compatible server needs no key.

## Running from source

```powershell
cd aven_ai_desktop
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

On macOS or Linux the steps are the same (`python3 -m venv .venv && source .venv/bin/activate`). The app runs there too, but Windows is the release target.

## Configuring an AI provider

On first launch AVEN shows a setup card. Open **Settings → AI Provider**, then:

1. Pick a **Provider**.
2. Paste your **API key**.
   - Anthropic keys come from the Claude Console: <https://platform.claude.com/>
   - OpenAI keys come from <https://platform.openai.com/>
3. Check the **Advanced** mapping, which sets the provider model behind AVEN Swift, Core and Ultra.
   - Anthropic comes pre-mapped (see [AVEN models](#aven-models)).
   - For OpenAI, type model IDs or click **Load available models** and pick from the list.
4. Under **General**, choose the AVEN model for each mode. The default for both is AVEN Ultra.
5. Click **Test connection**. This sends one short real request with the AVEN mode's model and shows either the reply or the exact error.
6. Click **Save**.

### OpenAI-compatible and local servers

Choose *OpenAI / OpenAI-compatible* and set a **Base URL**, for example `http://localhost:11434/v1`. Plain `http://` is only allowed for `localhost`. Every other address must use `https://`. Local servers don't need an API key.

### Environment variables (development)

When you run from source, you can put a `.env` file next to `main.py` (see `.env.example`) or set these variables:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | API key. Takes precedence over a key saved in Settings. |
| `AVEN_PROVIDER` | `anthropic` or `openai` |
| `AVEN_MODEL` / `AVEN_CODE_MODEL` | AVEN model for each mode: `aven-swift`, `aven-core` or `aven-ultra` |
| `AVEN_SWIFT_MODEL` / `AVEN_CORE_MODEL` / `AVEN_ULTRA_MODEL` | Provider model ID behind each AVEN model, for the current provider |
| `AVEN_BASE_URL` | Base URL for an OpenAI-compatible server |
| `AVEN_DATA_DIR` | Use a different data folder |

Packaged builds read real environment variables, but they never read `.env` files.

### How API keys are stored, and the limits of that

- A key entered in Settings goes to the **Windows Credential Manager** through the `keyring` library. On other systems it goes to the system credential store.
- Keys are **never** written to the settings file, the database or the logs. The logs also mask anything that looks like a key.
- **Limitation:** Credential Manager protects a key with your Windows sign-in. That keeps it away from other user accounts and from accidental disclosure, but **any program running under your own user account can read it**. Treat your API key like a password, set a spending limit in your provider's console, and revoke the key if you suspect your PC is compromised.
- If no credential store is available, the key is only kept in memory until you close the app. Use the environment variable instead.
- **Developers:** never put your own API key into the source code or the packaged app. Every user configures their own provider.

## Privacy and your data

**What leaves your computer.** When you send a message, AVEN sends the conversation so far, plus the mode's instructions, over HTTPS to the provider you selected. That provider processes it under its own terms and privacy policy ([Anthropic](https://www.anthropic.com/legal/privacy), [OpenAI](https://openai.com/policies/privacy-policy)). AVEN AI Desktop has no telemetry or analytics, and it does not upload files or conversations anywhere else.

**What stays on your computer.**

| Item | Location (Windows) |
|---|---|
| Conversations (SQLite) | `%APPDATA%\AVEN AI\conversations.db` |
| Settings (no secrets) | `%APPDATA%\AVEN AI\settings.json` |
| Logs (events and errors, no message contents) | `%APPDATA%\AVEN AI\logs\` |
| API key | Windows Credential Manager, entry “AVEN AI Desktop” |

On macOS the data folder is `~/Library/Application Support/AVEN AI`. On Linux it is `~/.local/share/aven-ai`.

The data folder is separate from the installation folder, so **updating or reinstalling the app keeps your conversations**.

**Deleting data:**

- One conversation: right-click it in the sidebar and choose **Delete**.
- Everything: **Settings → Privacy & Data → Delete all conversations…**
- Full removal: quit the app, delete the `%APPDATA%\AVEN AI` folder, and remove the key in Settings (**Remove saved key**) or in Windows Credential Manager.

Data you already sent to a provider is subject to that provider's retention policy. Deleting it locally doesn't delete it there.

### Other safety measures

- The app never renders raw HTML from AI output. Only `http`, `https` and `mailto` links are kept, and clicking one shows the full URL and asks before opening your browser. Images are never loaded.
- AI-generated code is **never executed**. AVEN CODE's instructions also forbid claiming that code was run or tested.
- Input length is limited, model IDs and base URLs are validated, and every provider error is converted into a safe message.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Enter` | Send. This can be changed to `Ctrl+Enter` in Settings. |
| `Shift+Enter` | New line |
| `Esc` | Stop generating |
| `Ctrl+N` | New conversation |
| `Ctrl+1` / `Ctrl+2` | Switch to AVEN / AVEN CODE |
| `Ctrl+L` | Focus the message box |
| `Ctrl+,` | Settings |

## Tests and static checks

```powershell
pip install -r requirements-dev.txt
$env:QT_QPA_PLATFORM="offscreen"   # optional: run UI tests without showing windows
python -m pytest -q
ruff check .
```

The tests never need a real API key and never touch the network. Provider tests drive the real `anthropic` and `openai` SDKs against a mocked HTTP transport that returns streaming responses in each provider's format. UI tests (pytest-qt) use a fake provider.

## Building the Windows executable

The build has to run **on Windows**. PyInstaller cannot cross-compile.

```powershell
cd aven_ai_desktop
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

The script:

1. Creates `.venv-build`.
2. Installs `requirements-dev.txt`.
3. Runs the tests.
4. Regenerates `assets\aven.ico` from the vector logo.
5. Runs PyInstaller with `aven_ai.spec`.

Output:

| Build | Path |
|---|---|
| Folder build (recommended) | `dist\AVEN AI\AVEN AI.exe`, plus `dist\AVEN-AI-Desktop-<version>-win64.zip` |
| Single file (`-OneFile`) | `dist\AVEN AI.exe` |

The folder build starts faster and antivirus heuristics flag it less often than a self-extracting single file. Distribute the **whole** `AVEN AI` folder (or the zip). The executable is windowed, so no console opens. It carries Windows version information and the AVEN icon, and it bundles the Python runtime.

Script options: `-OneFile`, `-SkipTests`, `-Python "py -3.13"`.

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before publishing a build.

### Runtime dependencies

| Package | Why |
|---|---|
| `PySide6-Essentials` | Qt GUI. Only the essentials, not WebEngine, to keep the bundle small. |
| `anthropic` | Official Anthropic SDK |
| `openai` | Official OpenAI SDK (also used for OpenAI-compatible servers) |
| `keyring` | Windows Credential Manager access |
| `Markdown` | Markdown → HTML, with raw HTML disabled |
| `Pygments` | Syntax highlighting |

## Project structure

```
aven_ai_desktop/
├── main.py                      # entry point, startup error reporting
├── aven_ai.spec                 # PyInstaller build definition
├── requirements.txt / requirements-dev.txt / pyproject.toml
├── .env.example                 # development configuration template
├── assets/                      # aven.ico, aven.png (generated from the vector logo)
├── scripts/
│   ├── build_windows.ps1        # reproducible Windows build
│   └── generate_icon.py         # renders the logo into a multi-size .ico
├── app/
│   ├── version.py               # app name and version (single source of truth)
│   ├── paths.py                 # per-user data dir, bundled resource paths
│   ├── logging_setup.py         # rotating log file with secret redaction
│   ├── application.py           # bootstrap: services, theme, main window
│   ├── config/
│   │   ├── aven_models.py       # AVEN Swift / Core / Ultra and default mappings
│   │   ├── settings.py          # settings model, JSON persistence, env overrides
│   │   └── secrets.py           # API keys: env var → credential store → session
│   ├── ai/
│   │   ├── base_provider.py     # provider interface, ChatRequest, StreamEvent
│   │   ├── anthropic_provider.py
│   │   ├── openai_provider.py
│   │   ├── provider_factory.py  # provider registry and construction
│   │   ├── chat_service.py      # config status, request building, history trimming
│   │   ├── prompts.py           # AVEN and AVEN CODE system instructions
│   │   └── errors.py            # user-facing error types
│   ├── storage/
│   │   ├── database.py          # SQLite connection and migrations
│   │   └── conversation_repository.py
│   ├── rendering/
│   │   └── markdown_renderer.py # safe Markdown, code segmentation, highlighting
│   ├── workers/
│   │   └── ai_worker.py         # background streaming and task threads
│   └── ui/
│       ├── main_window.py       # window and conversation controller
│       ├── sidebar.py
│       ├── chat_view.py         # header, mode switch, welcome, messages, composer
│       ├── message_widget.py    # message bubbles, code blocks, error card
│       ├── settings_dialog.py
│       ├── theme_manager.py     # light and dark palettes, stylesheet
│       └── logo.py              # vector-drawn AVEN logo
└── tests/                       # pytest + pytest-qt
```

## Troubleshooting

| Problem | What to do |
|---|---|
| “AI provider not configured” | Add an API key in Settings → AI Provider, or set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`. |
| “Invalid API key” | Copy the key again from the provider console. Check whether an environment variable is overriding the saved key; Settings shows where the key comes from. |
| “Model not available” | Your account may not have access to the model behind that AVEN model. In Settings → AI Provider → Advanced, click **Load available models** and pick one. |
| “AVEN Ultra is not set up for this provider yet” | Set its provider model ID under Settings → AI Provider → Advanced. |
| “Rate limit reached” | Wait and retry. Check your plan's limits and billing in the provider console. |
| “Request timed out” / “Connection problem” | Check your internet connection, proxy or firewall. Long answers may need a larger timeout in Settings. |
| Answer ends with “reached the maximum length” | Increase **Max response tokens** in Settings. |
| Windows SmartScreen warning | The build is not code-signed. Choose *More info → Run anyway*, or sign the build (see the release checklist). |
| The app does not start | See `%APPDATA%\AVEN AI\logs\startup-error.log` and `aven.log`. |
| Corrupted settings | Delete `%APPDATA%\AVEN AI\settings.json`. Defaults are restored and conversations are unaffected. |

## Current limitations

- Text conversations only: no image or file attachments, and no web browsing.
- Responses come from one provider at a time. Supported providers are Anthropic and OpenAI (or OpenAI-compatible).
- There is no automatic update system. Install new versions over the old one; your data folder is kept.
- Release builds are not code-signed unless you sign them yourself.
- Very long conversations send at most about the last 400,000 characters of history to the provider. All messages stay in the local database.
