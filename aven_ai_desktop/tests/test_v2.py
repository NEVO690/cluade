"""AVEN AI 2.0: categories, paid access, coding tools, Made With AVEN, What's New, upgrade path."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from app.ai.chat_service import ChatService
from app.code.files import AttachedFile
from app.config.catalog import RETIRED_NAMES, CatalogError, catalog, load_catalog
from app.config.secrets import CredentialStore
from app.config.settings import AppSettings, SettingsStore
from app.storage.conversation_repository import MODES as REPO_MODES
from app.storage.conversation_repository import ConversationRepository
from app.storage.database import Database
from app.studio.projects import ProjectStore
from app.ui.main_window import MainWindow
from app.ui.message_widget import AssistantMessageWidget, UserMessageWidget
from app.ui.theme_manager import ThemeManager
from app.version import __version__
from tests.conftest import FakeProvider

FENCE = "`" * 3
GAME = (Path(__file__).parent / "data" / "sample_game.js").read_text(encoding="utf-8")
PLAN = {"title": "Coin Run", "genre": "arcade", "summary": "Collect coins.", "controls": ["Arrows: move"],
        "systems": [], "entities": [], "scenes": ["title", "play"], "goal": "score", "scope_notes": ""}  # fmt: skip


class FakeAccount:
    """Stands in for the server-verified account (the real one is tested in test_account/test_billing)."""

    def __init__(self, entitled: bool = False, available: bool = True) -> None:
        self.entitled = entitled
        self.available = available
        self.token = "avk_test" if available else ""
        self.account_id = "acc_test" if available else ""

    def has(self, entitlement: str) -> bool:
        return self.entitled and entitlement == "aven_code"

    def refresh(self) -> None:
        self.refreshed = True


@pytest.fixture
def window_factory(qtbot, qapp, tmp_path):
    def factory(provider=None, account=None, settings=None):
        credentials = CredentialStore(use_keyring=False)
        credentials.save_key("anthropic", "sk-test-key-123456")
        settings = settings or AppSettings(theme="dark", provider="anthropic", last_seen_version=__version__)
        theme = ThemeManager(qapp)
        theme.apply("dark")
        db = Database(tmp_path / "v2.db")
        repo = ConversationRepository(db)
        holder = {"provider": provider or FakeProvider(), "calls": []}

        def factory_(*args, **kwargs):
            holder["calls"].append(kwargs)
            return holder["provider"]

        service = ChatService(settings, credentials, provider_factory=factory_, account=account or FakeAccount())
        store = ProjectStore(db, root=tmp_path / "projects")
        window = MainWindow(
            settings, SettingsStore(tmp_path / "settings.json"), credentials, repo, theme, service, store
        )
        qtbot.addWidget(window)
        window.resize(1200, 820)
        window.show()
        return window, repo, holder

    return factory


# --- catalog ---------------------------------------------------------------------------------


def test_catalog_has_the_planned_lineup_and_no_retired_models() -> None:
    c = catalog()
    assert [m.display_name for m in c.models.values()] == [
        "AVEN 2.0",
        "AVEN Ultra 1.0",
        "AVEN Core 1.1",
        "AVEN Light 1.1",
    ]
    assert {m.id: m.released for m in c.models.values() if m.version != "1.0"} == {
        "aven-2": "2026-11-03", "aven-core": "2026-11-03", "aven-light": "2026-11-03",
    }  # fmt: skip
    assert [cat.name for cat in c.categories.values()] == [
        "AVEN AI", "AVEN Python", "AVEN Unity", "AVEN CODE", "Made With AVEN",
    ]  # fmt: skip
    access = {cat.id: cat.access for cat in c.categories.values()}
    assert access == {"aven": "free", "python": "free", "unity": "free", "code": "paid", "made": "free"}
    assert c.categories["made"].pricing_note  # pricing not final: shown as a preview, not as free forever
    assert all(m.access == "free" for m in c.models.values())  # Ultra stays free until configured otherwise
    everything = json.dumps([m.__dict__ for m in c.models.values()], default=str) + json.dumps(
        [r.__dict__ for r in c.releases], default=str
    )
    for name in RETIRED_NAMES:
        assert name.lower() not in everything.lower()
    assert "flagship" not in everything.lower()


def test_catalog_refuses_retired_model_names(tmp_path) -> None:
    source = Path(__file__).resolve().parent.parent / "app" / "data"
    for name in ("models.json", "categories.json", "releases.json"):
        (tmp_path / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    releases = json.loads((tmp_path / "releases.json").read_text(encoding="utf-8"))
    releases["releases"][0]["items"].append({"title": "AVEN Energy", "body": "coming soon"})
    (tmp_path / "releases.json").write_text(json.dumps(releases), encoding="utf-8")
    with pytest.raises(CatalogError, match="never released"):
        load_catalog(tmp_path)


def test_repository_accepts_every_chat_category() -> None:
    chat = tuple(cid for cid, cat in catalog().categories.items() if cat.kind == "chat")
    assert chat == REPO_MODES


# --- categories in the window --------------------------------------------------------------------


def test_sidebar_shows_five_categories_with_access_badges(window_factory) -> None:
    window, _repo, _holder = window_factory()
    badges = {cid: b.badge.text() for cid, b in window.sidebar.categories.buttons.items()}
    assert badges == {"aven": "Free", "python": "Free", "unity": "Free", "code": "Paid", "made": "Preview"}
    for cid in ("aven", "python", "unity"):
        window.set_category(cid)
        assert window.main_stack.currentWidget() is window.chat
        assert window.chat.access_badge.text() == "Free"
    window.set_category("made")
    assert window.main_stack.currentWidget() is window.studio


def test_each_category_remembers_its_model(window_factory) -> None:
    window, _repo, _holder = window_factory()
    window.set_category("python")
    window.chat.model_picker.options["aven-core"].clicked.emit()
    window.set_category("aven")
    assert window.settings.model == "aven-2"
    window.set_category("python")
    assert window.settings.model == "aven-core" and window.settings.category_models["python"] == "aven-core"


def test_conversations_are_listed_per_category(window_factory, qtbot) -> None:
    window, repo, _holder = window_factory(FakeProvider(reply="ok"))
    repo.create_conversation("aven", "General chat")
    repo.create_conversation("unity", "Unity chat")
    window.set_category("unity")
    titles = [window.sidebar.list.item(i).text() for i in range(window.sidebar.list.count())]
    assert "Unity chat" in titles and "General chat" not in titles


# --- paid access ----------------------------------------------------------------------------------


def test_aven_code_is_locked_without_a_verified_subscription(window_factory, monkeypatch) -> None:
    provider = FakeProvider()
    window, repo, _holder = window_factory(provider, account=FakeAccount(entitled=False))
    opened = []
    monkeypatch.setattr(window, "open_account", lambda: opened.append(True))
    window.set_category("code")
    assert window.chat.access_badge.text() == "Paid"
    assert not window.chat.setup_card.isHidden() and window.chat.setup_button.text() == "Subscribe"
    window.send_message("build me an API")
    assert opened and provider.requests == [] and repo.list_conversations() == []


def test_aven_code_without_a_server_explains_it_is_not_available(window_factory) -> None:
    window, _repo, _holder = window_factory(account=FakeAccount(available=False))
    window.set_category("code")
    assert "not available in this build" in window.chat.setup_label.text()


def test_aven_code_works_with_a_verified_subscription(window_factory, qtbot) -> None:
    provider = FakeProvider(reply="Here is the plan.")
    window, repo, holder = window_factory(provider, account=FakeAccount(entitled=True))
    window.set_category("code")
    assert window.chat.setup_card.isHidden()
    window.send_message("review my code")
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    assert provider.requests[0].system_prompt.startswith("You are AVEN CODE")
    assert holder["calls"][-1]["client_id"]  # provider created for this request
    assert repo.list_conversations()[0].mode == "code"


# --- coding tools -----------------------------------------------------------------------------------


def test_attached_files_are_sent_and_shown_compactly(window_factory, qtbot) -> None:
    provider = FakeProvider(reply="Looks fine.")
    window, repo, _holder = window_factory(provider)
    window.set_category("python")
    window.chat.add_attachments([AttachedFile("src/app.py", "def main():\n    return 42\n")])
    assert not window.chat.attachment_holder.isHidden()
    window.send_message("what does main return?")
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    sent = provider.requests[0].messages[-1].content
    assert "### src/app.py" in sent and "return 42" in sent and sent.startswith("what does main return?")
    stored = repo.list_messages(repo.list_conversations()[0].id)[0].content
    assert "<<<AVEN_FILES" in stored
    user = next(w for w in window.chat.message_widgets() if isinstance(w, UserMessageWidget))
    assert user.view.toPlainText() == "what does main return?"
    assert "src/app.py" in user.files_label.text()
    assert window.chat.attachments == [] and window.chat.attachment_holder.isHidden()


def test_python_replies_are_checked_and_files_can_be_saved(window_factory, qtbot, tmp_path, monkeypatch) -> None:
    reply = (
        f"**File: app/main.py**\n{FENCE}python\ndef add(a, b):\n    return a + b\n{FENCE}\n\n"
        f"**File: ../outside.py**\n{FENCE}python\nprint(\n{FENCE}\n"
    )
    window, _repo, _holder = window_factory(FakeProvider(reply=reply))
    window.set_category("python")
    window.send_message("make an add function")
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    widget = [w for w in window.chat.message_widgets() if isinstance(w, AssistantMessageWidget)][-1]
    assert not widget.checks.isHidden()
    assert "1 problem found" in widget.checks.title.text()  # the unclosed print( is a syntax error
    assert "was not run" in widget.checks.details.text()
    assert not widget.save_button.isHidden()

    target = tmp_path / "out"
    target.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(target))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window.save_files(widget)
    assert (target / "app" / "main.py").read_text() == "def add(a, b):\n    return a + b\n"
    assert not (tmp_path / "outside.py").exists()  # unsafe path refused


def test_unity_replies_get_unity_checks(window_factory, qtbot) -> None:
    reply = (
        f"**File: Assets/Scripts/Player.cs**\n{FENCE}csharp\nusing UnityEngine;\n"
        "public class Mover : MonoBehaviour {\n"
        "    void Update() { GetComponent<Rigidbody>().AddForce(Vector3.up); }\n}\n"
        f"{FENCE}\n"
    )
    window, _repo, _holder = window_factory(FakeProvider(reply=reply))
    window.set_category("unity")
    window.send_message("player script")
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    widget = [w for w in window.chat.message_widgets() if isinstance(w, AssistantMessageWidget)][-1]
    details = widget.checks.details.text()
    assert "Mover.cs" in details and "every frame" in details and "FixedUpdate" in details


def test_general_category_does_not_show_code_checks(window_factory, qtbot) -> None:
    window, _repo, _holder = window_factory(FakeProvider(reply=f"{FENCE}python\nprint(\n{FENCE}"))
    window.send_message("hi")
    qtbot.waitUntil(lambda: window.generation is None, timeout=5000)
    widget = [w for w in window.chat.message_widgets() if isinstance(w, AssistantMessageWidget)][-1]
    assert widget.checks.isHidden() and window.chat.attach_button.isHidden()


# --- Made With AVEN ------------------------------------------------------------------------------------


def test_studio_creates_checks_repairs_and_saves_a_game(window_factory, qtbot, monkeypatch) -> None:
    crashing = GAME.replace("g.state.p.x, g.state.p.y", "g.state.player.x, g.state.p.y")
    provider = FakeProvider(replies=[json.dumps(PLAN), f"{FENCE}javascript\n{crashing}\n{FENCE}",
                                     f"{FENCE}javascript\n{GAME}\n{FENCE}"])  # fmt: skip
    window, _repo, _holder = window_factory(provider)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    window.set_category("made")
    studio = window.studio
    studio.description_input.setPlainText("A coin game")
    studio.create_game()
    qtbot.waitUntil(lambda: not studio.busy, timeout=30000)
    project = window.projects.list()[0]
    assert project.title == "Coin Run" and project.status == "validated" and project.version == 1
    assert project.page_path.exists() and "Content-Security-Policy" in project.page_path.read_text()
    assert [h["kind"] for h in project.history] == ["plan", "build"]
    assert len(provider.requests) == 3  # plan, code, one repair
    assert "Made With AVEN" in provider.requests[0].system_prompt
    assert studio.stack.currentIndex() == 1 and studio.play_button.isEnabled()
    titles = [window.sidebar.list.item(i).text() for i in range(window.sidebar.list.count())]
    assert "Coin Run" in titles

    provider.replies = [f"{FENCE}javascript\n{GAME.replace('#7b6cff', '#ff4444')}\n{FENCE}"]
    studio.change_input.setPlainText("make the player red")
    studio.apply_change()
    qtbot.waitUntil(lambda: not studio.busy, timeout=30000)
    project = window.projects.get(project.id)
    assert project.version == 2 and "#ff4444" in project.code() and project.status == "validated"


def test_studio_reports_a_game_that_cannot_be_fixed(window_factory, qtbot, monkeypatch) -> None:
    broken = f"{FENCE}javascript\nconst game = AVEN.createGame({{}});\nfunction oops( {{\n{FENCE}"
    provider = FakeProvider(replies=[json.dumps(PLAN)] + [broken] * 4)
    window, _repo, _holder = window_factory(provider)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    window.set_category("made")
    window.studio.description_input.setPlainText("A broken game")
    window.studio.create_game()
    qtbot.waitUntil(lambda: not window.studio.busy, timeout=30000)
    project = window.projects.list()[0]
    assert project.status == "needs_fixes"  # never called validated
    assert project.history[-1]["errors"]


def test_studio_stop_cancels_the_build(window_factory, qtbot) -> None:
    provider = FakeProvider(reply="x" * 4000, delay=0.01)
    window, _repo, _holder = window_factory(provider)
    window.set_category("made")
    window.studio.description_input.setPlainText("A slow game")
    window.studio.create_game()
    qtbot.waitUntil(lambda: window.studio.busy, timeout=5000)
    window.studio.stop()
    qtbot.waitUntil(lambda: not window.studio.busy, timeout=10000)
    assert window.projects.list()[0].version == 0


# --- What's New and upgrades ----------------------------------------------------------------------------


def test_whats_new_opens_once_after_an_upgrade(window_factory, qtbot) -> None:
    settings = AppSettings(theme="dark", provider="anthropic", last_seen_version="1.2.0")
    window, _repo, _holder = window_factory(settings=settings)
    from app.ui.whats_new import WhatsNewDialog

    qtbot.waitUntil(
        lambda: any(isinstance(w, WhatsNewDialog) and w.isVisible() for w in window.findChildren(WhatsNewDialog)),
        timeout=3000,
    )
    dialog = window.findChildren(WhatsNewDialog)[0]
    text = dialog.view.toPlainText()
    for expected in (
        "AVEN 2.0",
        "AVEN Light 1.1 and AVEN Core 1.1",
        "AVEN Python",
        "AVEN Unity",
        "AVEN CODE",
        "Made With AVEN",
    ):
        assert expected in text
    assert window.settings.last_seen_version == __version__
    dialog.close()


def test_upgrade_from_1x_keeps_conversations_and_settings(tmp_path) -> None:
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'aven', created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00Z',
            updated_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00Z');
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')), content TEXT NOT NULL, model TEXT,
            status TEXT NOT NULL DEFAULT 'complete', created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00Z');
        INSERT INTO conversations (title, mode) VALUES ('Old code chat', 'code');
        INSERT INTO messages (conversation_id, role, content, model) VALUES (1, 'user', 'hi', NULL);
        INSERT INTO messages (conversation_id, role, content, model) VALUES (1, 'assistant', 'hello', 'aven-1-1');
        PRAGMA user_version = 1;
        """
    )
    conn.close()
    db = Database(path)
    repo = ConversationRepository(db)
    assert [c.title for c in repo.list_conversations()] == ["Old code chat"]
    assert [m.content for m in repo.list_messages(1)] == ["hi", "hello"]
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert db.meta("app_version") == __version__
    from app.config.aven_models import aven_model_name

    assert aven_model_name("aven-1-1") == "AVEN 1.1"  # old replies keep the model's old name

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"provider": "anthropic", "model": "aven-1-1", "theme": "dark"}))
    loaded = SettingsStore(settings_file).load()
    assert loaded.model == "aven-2" and loaded.theme == "dark" and loaded.category == "aven"


def test_a_model_marked_in_development_is_not_offered_as_working(monkeypatch, qtbot) -> None:
    import dataclasses

    from app.ui.chat_view import ModelOption

    models = catalog().models
    monkeypatch.setitem(models, "aven-ultra", dataclasses.replace(models["aven-ultra"], status="in_development"))
    credentials = CredentialStore(use_keyring=False)
    credentials.save_key("anthropic", "sk-test-key-123456")
    service = ChatService(AppSettings(provider="anthropic", model="aven-ultra"), credentials, account=FakeAccount())
    status = service.status("aven")
    assert not status.ready and "still in development" in status.problem
    option = ModelOption(models["aven-ultra"])
    qtbot.addWidget(option)
    assert not option.isEnabled() and "In development" in option.description.text()
