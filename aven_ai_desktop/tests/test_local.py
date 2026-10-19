"""AVEN Local: downloader, engine lifecycle, provider and UI integration."""

from __future__ import annotations

import hashlib
import sys
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.ai.base_provider import ChatMessage, ChatRequest
from app.ai.local_provider import LocalProvider, ModelNotDownloadedError, ThinkFilter
from app.local import downloader
from app.local.downloader import DownloadCancelledError, DownloadError, download_model
from app.local.engine import EngineError, LocalEngine
from app.local.models import LOCAL_MODELS, MODEL_FILES, ModelFile

FAKE_SERVER = Path(__file__).with_name("fake_llama_server.py")

# --- think filter ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chunks",
    [
        ["<think>hidden</think>Hello"],
        ["<thi", "nk>hid", "den</th", "ink>\n\nHel", "lo"],
        ["Hel", "lo"],
    ],
)
def test_think_filter_hides_reasoning(chunks) -> None:
    f = ThinkFilter()
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    assert out == "Hello"


def test_think_filter_keeps_normal_angle_brackets() -> None:
    f = ThinkFilter()
    assert "".join(f.feed(c) for c in ["a < b and <thing>", " ok"]) + f.flush() == "a < b and <thing> ok"


# --- downloader -------------------------------------------------------------------------------


class FileServer:
    """Serves bytes over HTTP on 127.0.0.1 with Range support."""

    def __init__(self, payload: bytes, honour_range: bool = True) -> None:
        self.payload = payload
        self.requests: list[str | None] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                rng = self.headers.get("Range")
                outer.requests.append(rng)
                data = outer.payload
                if rng and honour_range:
                    start = int(rng.split("=")[1].rstrip("-"))
                    self.send_response(206)
                    data = data[start:]
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/model.gguf"

    def close(self) -> None:
        self.server.shutdown()


def file_for(payload: bytes, **overrides) -> ModelFile:
    base = ModelFile("test", "org/repo", "rev", "model.gguf", len(payload), hashlib.sha256(payload).hexdigest(), "T")
    return replace(base, **overrides)


def test_download_verifies_and_reports_progress(tmp_path) -> None:
    payload = b"x" * (3 * 1024 * 1024 + 7)
    server = FileServer(payload)
    progress = []
    try:
        path = download_model(
            file_for(payload), progress=lambda d, t: progress.append((d, t)), url=server.url, dest_dir=tmp_path
        )
    finally:
        server.close()
    assert path.read_bytes() == payload
    assert progress[-1] == (len(payload), len(payload))
    assert not (tmp_path / "model.gguf.part").exists()


def test_download_resumes_partial_file(tmp_path) -> None:
    payload = bytes(range(256)) * 10_000
    (tmp_path / "model.gguf.part").write_bytes(payload[:1000])
    server = FileServer(payload)
    try:
        download_model(file_for(payload), url=server.url, dest_dir=tmp_path)
    finally:
        server.close()
    assert server.requests == ["bytes=1000-"]
    assert (tmp_path / "model.gguf").read_bytes() == payload


def test_download_restarts_if_server_ignores_range(tmp_path) -> None:
    payload = b"abc" * 5000
    (tmp_path / "model.gguf.part").write_bytes(payload[:100])
    server = FileServer(payload, honour_range=False)
    try:
        download_model(file_for(payload), url=server.url, dest_dir=tmp_path)
    finally:
        server.close()
    assert (tmp_path / "model.gguf").read_bytes() == payload


def test_download_rejects_tampered_file(tmp_path) -> None:
    payload = b"genuine model" * 1000
    server = FileServer(b"tampered model" * 1000)
    try:
        with pytest.raises(DownloadError):
            download_model(file_for(payload, size=len(b"tampered model" * 1000)), url=server.url, dest_dir=tmp_path)
    finally:
        server.close()
    assert not (tmp_path / "model.gguf").exists()
    assert not (tmp_path / "model.gguf.part").exists()


def test_download_cancel_keeps_partial(tmp_path) -> None:
    payload = b"z" * (4 * 1024 * 1024)
    server = FileServer(payload)
    cancel = threading.Event()
    try:
        with pytest.raises(DownloadCancelledError):
            download_model(
                file_for(payload), progress=lambda d, t: cancel.set(), cancel=cancel, url=server.url, dest_dir=tmp_path
            )
    finally:
        server.close()
    assert (tmp_path / "model.gguf.part").stat().st_size > 0


def test_download_refuses_insecure_urls(tmp_path) -> None:
    with pytest.raises(DownloadError):
        download_model(file_for(b"x"), url="http://example.com/model.gguf", dest_dir=tmp_path)


def test_pinned_model_files_are_https_and_verified() -> None:
    for file in MODEL_FILES.values():
        assert file.url.startswith("https://huggingface.co/")
        assert len(file.revision) == 40 and len(file.sha256) == 64
    assert {m: v.file.key for m, v in LOCAL_MODELS.items()} == {
        "aven-light": "qwen3-1.7b",
        "aven-core": "qwen3-4b",
        "aven-1-1": "qwen3-8b",  # AVEN 1.1: the big model, answering directly
        "aven-ultra": "qwen3-8b",
    }
    assert [LOCAL_MODELS[m].thinking for m in ("aven-light", "aven-core", "aven-1-1", "aven-ultra")] == [
        False,
        False,
        False,
        True,
    ]


# --- engine + provider ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    eng = LocalEngine(command_prefix=[sys.executable, str(FAKE_SERVER)])
    yield eng
    eng.stop()


@pytest.fixture
def downloaded(monkeypatch, tmp_path):
    """Pretend every model is downloaded; model files live in tmp_path."""
    import app.ai.local_provider as lp

    monkeypatch.setattr(lp, "is_downloaded", lambda file: True)
    monkeypatch.setattr(lp, "model_path", lambda file: tmp_path / file.filename)
    return tmp_path


def ask(provider, model: str, text: str = "hello") -> str:
    request = ChatRequest(model=model, system_prompt="You are AVEN.", messages=[ChatMessage("user", text)])
    return "".join(e.text for e in provider.stream_chat(request) if e.kind == "text")


def test_local_provider_streams_with_thinking_per_model(engine, downloaded) -> None:
    provider = LocalProvider(engine)
    assert ask(provider, "aven-light") == "model=Qwen3-1.7B-Q4_K_M.gguf thinking=False echo=hello"
    first_process = engine.process
    assert ask(provider, "aven-light", "again").endswith("echo=again")
    assert engine.process is first_process  # same model: engine reused

    assert ask(provider, "aven-ultra") == "model=Qwen3-8B-Q4_K_M.gguf thinking=True echo=hello"
    assert engine.process is not first_process  # switched model: engine restarted
    assert first_process.poll() is not None  # old engine stopped
    second_process = engine.process
    # AVEN 1.1 uses the same file as Ultra (no extra download, no restart) without thinking.
    assert ask(provider, "aven-1-1") == "model=Qwen3-8B-Q4_K_M.gguf thinking=False echo=hello"
    assert engine.process is second_process
    assert ask(provider, "aven-core").startswith("model=Qwen3-4B-Q4_K_M.gguf thinking=False")


def test_local_provider_uses_recommended_sampling(engine, downloaded) -> None:
    provider = LocalProvider(engine)
    # Qwen3's recommended settings: direct answers vs. thinking mode.
    assert ask(provider, "aven-1-1", "sampling") == "temperature=0.7 top_p=0.8 top_k=20"
    assert ask(provider, "aven-ultra", "sampling") == "temperature=0.6 top_p=0.95 top_k=20"


def test_context_window_and_reply_budget_per_model(engine, downloaded) -> None:
    provider = LocalProvider(engine)
    # The 8B file opens a larger window; Ultra may use more tokens because it thinks first.
    assert ask(provider, "aven-light", "context-info") == "ctx=12288 max_tokens=4096 messages=2"
    assert ask(provider, "aven-1-1", "context-info") == "ctx=16384 max_tokens=4096 messages=2"
    assert ask(provider, "aven-ultra", "context-info") == "ctx=16384 max_tokens=8192 messages=2"


def test_history_is_fitted_by_exact_token_counts(engine, downloaded) -> None:
    # The fake engine counts one token per character. Old turns are dropped to fit the window.
    provider = LocalProvider(engine)
    old = [ChatMessage("user", "x" * 4000), ChatMessage("assistant", "y" * 4000)]
    request = ChatRequest(
        model="aven-light", system_prompt="S", messages=[*old, *old, ChatMessage("user", "context-info")]
    )
    reply = "".join(e.text for e in provider.stream_chat(request) if e.kind == "text")
    assert reply == "ctx=12288 max_tokens=4096 messages=4"  # system + one old pair + the question


def test_fit_messages_shrinks_the_reply_before_failing() -> None:
    from app.ai.local_provider import ContextTooLongError, fit_messages

    messages = [ChatMessage("user", "a" * 9000)]
    kept, budget = fit_messages(messages, 100, 12_288, 4096, len)
    assert kept == messages and 1024 <= budget < 4096
    with pytest.raises(ContextTooLongError):
        fit_messages([ChatMessage("user", "a" * 12_000)], 100, 12_288, 4096, len)


def test_ultra_reports_when_thinking_uses_the_whole_budget(engine, downloaded) -> None:
    from app.ai.local_provider import ThinkingTooLongError

    with pytest.raises(ThinkingTooLongError, match="thinking budget"):
        ask(LocalProvider(engine), "aven-ultra", "think-forever")


def test_local_provider_sends_the_script_guard(engine, downloaded) -> None:
    assert ask(LocalProvider(engine), "aven-light", "grammar-info") == "grammar=True"


def test_local_provider_hides_think_tags(engine, downloaded) -> None:
    assert ask(LocalProvider(engine), "aven-ultra", "think-tags") == "Visible answer"


def test_engine_requires_token(engine, downloaded) -> None:
    import urllib.error
    import urllib.request

    engine.ensure(downloaded / "model.gguf")
    request = urllib.request.Request(f"{engine.base_url}/chat/completions", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(request, timeout=5)
    assert info.value.code == 401
    assert engine.base_url.startswith("http://127.0.0.1:")


def test_engine_reports_crash(engine, tmp_path) -> None:
    with pytest.raises(EngineError) as info:
        engine.ensure(tmp_path / "crash-model.gguf")
    assert "memory" in str(info.value)
    assert engine.process is None


def test_engine_missing_binary(tmp_path) -> None:
    eng = LocalEngine(binary=tmp_path / "missing" / "llama-server")
    assert not eng.available()
    with pytest.raises(EngineError):
        eng.ensure(tmp_path / "m.gguf")


def test_model_not_downloaded(engine, monkeypatch) -> None:
    import app.ai.local_provider as lp

    monkeypatch.setattr(lp, "is_downloaded", lambda file: False)
    with pytest.raises(ModelNotDownloadedError) as info:
        ask(LocalProvider(engine), "aven-core")
    assert "2.5 GB" in info.value.user_message


# --- chat service + UI ----------------------------------------------------------------------------


@pytest.fixture
def shared_engine(engine):
    from app.local import engine as engine_module

    engine_module.set_engine(engine)
    yield engine
    engine_module.set_engine(None)


def test_status_asks_for_download_then_ready(shared_engine, monkeypatch) -> None:
    from app.ai.chat_service import ChatService
    from app.config.secrets import CredentialStore
    from app.config.settings import AppSettings

    svc = ChatService(AppSettings(provider="aven_local"), CredentialStore(use_keyring=False))
    monkeypatch.setattr(downloader, "is_downloaded", lambda file: False)
    status = svc.status()
    assert not status.ready and status.needs_download
    assert "1.3 GB" in status.problem and "AVEN Light" in status.problem
    monkeypatch.setattr(downloader, "is_downloaded", lambda file: True)
    assert svc.status().ready


def test_ui_downloads_then_chats_locally(qtbot, qapp, tmp_path, shared_engine, downloaded, monkeypatch) -> None:
    from app.ai.chat_service import ChatService
    from app.config.secrets import CredentialStore
    from app.config.settings import AppSettings, SettingsStore
    from app.storage.conversation_repository import ConversationRepository
    from app.storage.database import Database
    from app.ui import download_dialog
    from app.ui.main_window import MainWindow
    from app.ui.theme_manager import ThemeManager

    state = {"downloaded": False}
    monkeypatch.setattr(downloader, "is_downloaded", lambda file: state["downloaded"])

    def fake_exec(dialog):
        state["downloaded"] = True
        return download_dialog.DownloadDialog.DialogCode.Accepted

    monkeypatch.setattr(download_dialog.DownloadDialog, "exec", fake_exec)

    settings = AppSettings(provider="aven_local")
    theme = ThemeManager(qapp)
    theme.apply("dark")
    repo = ConversationRepository(Database(tmp_path / "ui.db"))
    window = MainWindow(
        settings,
        SettingsStore(tmp_path / "s.json"),
        CredentialStore(use_keyring=False),
        repo,
        theme,
        ChatService(settings, CredentialStore(use_keyring=False)),
    )
    qtbot.addWidget(window)
    window.show()
    assert not window.chat.setup_card.isHidden()
    assert window.chat.setup_button.text() == "Download"
    assert "1.3 GB download" in window.chat.model_picker.options["aven-light"].description.text()

    window.send_message("hi there")  # triggers the download, then sends
    qtbot.waitUntil(lambda: window.generation is None and bool(repo.list_conversations()), timeout=15000)
    qtbot.waitUntil(lambda: len(repo.list_messages(repo.list_conversations()[0].id)) == 2, timeout=15000)
    reply = repo.list_messages(repo.list_conversations()[0].id)[-1]
    assert reply.content == "model=Qwen3-1.7B-Q4_K_M.gguf thinking=False echo=hi there"
    assert reply.model == "aven-light"
    assert window.chat.setup_card.isHidden()
    assert "On this computer" in window.chat.model_picker.options["aven-light"].description.text()
