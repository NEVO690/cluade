"""Made With AVEN: the game creation studio (dashboard and project workspace).

The studio drives :class:`app.studio.pipeline.GamePipeline` on a background thread and
stores results with :class:`app.studio.projects.ProjectStore` on the GUI thread. Games
are played in the system browser from a locked-down page (no network access).
"""

from __future__ import annotations

import html
import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.ai import errors
from app.ai.base_provider import ChatMessage, ChatRequest
from app.config.catalog import catalog
from app.rendering.markdown_renderer import highlight_code_html
from app.storage.database import StorageError
from app.studio.pipeline import BuildResult, GamePipeline, PipelineError
from app.studio.projects import Project, ProjectStore
from app.ui.chat_view import ModelPicker
from app.ui.theme_manager import CODE_FONT_FAMILIES, Palette
from app.workers.ai_worker import BackgroundJob

log = logging.getLogger(__name__)

STATUS_LABELS = {"draft": "Draft", "validated": "✓ Validated", "needs_fixes": "⚠ Needs fixes"}


class CancelledError(Exception):
    pass


class StudioSignals(QObject):
    done = Signal()
    progress = Signal(str)
    text = Signal(int)  # characters received so far in the current AI reply
    plan = Signal(object)  # dict
    succeeded = Signal(object)  # BuildResult or None
    failed = Signal(str)


class StudioJob(BackgroundJob):
    """Runs one studio task (plan + build, build, or change) off the GUI thread."""

    def __init__(self, task, cancel_event: threading.Event) -> None:
        self.task = task
        self.cancel_event = cancel_event
        self.signals = StudioSignals()

    def run(self) -> None:
        try:
            result = self.task(self)
        except CancelledError:
            self.signals.failed.emit("Stopped.")
        except (PipelineError, errors.AIError) as exc:
            self.signals.failed.emit(getattr(exc, "user_message", None) or str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Studio task crashed")
            self.signals.failed.emit(f"Unexpected error: {type(exc).__name__}")
        else:
            self.signals.succeeded.emit(result)


def _status_chip(status: str) -> QLabel:
    chip = QLabel(STATUS_LABELS.get(status, status))
    chip.setObjectName("StatusChip")
    chip.setProperty("state", status)
    return chip


class ProjectCard(QFrame):
    clicked = Signal(int)

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_id = project.id
        self.setObjectName("ProjectCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        title = QLabel(project.title)
        title.setObjectName("ProjectTitle")
        title.setWordWrap(True)
        summary = QLabel(str(project.plan.get("summary") or project.description)[:140])
        summary.setObjectName("HelpText")
        summary.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(_status_chip(project.status))
        meta = QLabel(f"v{project.version}" if project.version else "no game yet")
        meta.setObjectName("HelpText")
        row.addStretch(1)
        row.addWidget(meta)
        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addStretch(1)
        layout.addLayout(row)
        self.setMinimumHeight(120)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.project_id)
        super().mouseReleaseEvent(event)


class StudioView(QWidget):
    projects_changed = Signal()
    download_requested = Signal()
    settings_requested = Signal()
    model_changed = Signal(str)

    def __init__(self, store: ProjectStore, chat_service, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.chat_service = chat_service
        self.palette_ = palette
        self.category = catalog().category("made")
        self.project: Project | None = None
        self.job: StudioJob | None = None
        self.cancel_event: threading.Event | None = None
        self._last_result: BuildResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_dashboard())
        self.stack.addWidget(self._build_workspace())
        root.addWidget(self.stack, 1)

    # --- construction ----------------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("ChatHeader")
        header.setFixedHeight(60)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 16, 0)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addStretch(1)
        self.title_label = QLabel("Made With AVEN")
        self.title_label.setObjectName("ConversationTitle")
        self.subtitle_label = QLabel("Describe a game and AVEN builds it")
        self.subtitle_label.setObjectName("ModelLabel")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        titles.addStretch(1)
        layout.addLayout(titles, 1)
        badge = QLabel("Preview")
        badge.setObjectName("AccessBadge")
        badge.setProperty("kind", "preview")
        badge.setToolTip(self.category.pricing_note)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _build_dashboard(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        page.setObjectName("StudioPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(16)

        hero_title = QLabel("Made With AVEN")
        hero_title.setObjectName("WelcomeTitle")
        hero_text = QLabel(self.category.tagline)
        hero_text.setObjectName("WelcomeSubtitle")
        hero_text.setWordWrap(True)
        note = QLabel(
            f"{self.category.description} Games are 2D for now; AVEN tells you what it simplified. "
            f"{self.category.pricing_note}"
        )
        note.setObjectName("HelpText")
        note.setWordWrap(True)
        outer.addWidget(hero_title)
        outer.addWidget(hero_text)
        outer.addWidget(note)

        card = QFrame()
        card.setObjectName("StudioCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)
        label = QLabel("New game")
        label.setObjectName("SectionTitle")
        card_layout.addWidget(label)
        self.description_input = QPlainTextEdit()
        self.description_input.setObjectName("StudioInput")
        self.description_input.setPlaceholderText(
            "Describe your game: the world, the player, the goal, enemies, items, levels…"
        )
        self.description_input.setFixedHeight(110)
        card_layout.addWidget(self.description_input)
        ideas = QGridLayout()
        ideas.setSpacing(8)
        for index, idea in enumerate(self.category.suggestions):
            button = QPushButton(idea)
            button.setObjectName("SuggestionCard")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            button.clicked.connect(lambda _=False, text=idea: self.description_input.setPlainText(text))
            ideas.addWidget(button, index // 2, index % 2)
        card_layout.addLayout(ideas)
        row = QHBoxLayout()
        self.model_picker = ModelPicker()
        self.model_picker.set_allowed(self.category.models)
        self.model_picker.model_selected.connect(self.model_changed.emit)
        row.addWidget(self.model_picker)
        self.setup_label = QLabel("")
        self.setup_label.setObjectName("HelpText")
        self.setup_label.setWordWrap(True)
        row.addWidget(self.setup_label, 1)
        self.create_button = QPushButton("Create game")
        self.create_button.setObjectName("PrimaryButton")
        self.create_button.clicked.connect(self.create_game)
        row.addWidget(self.create_button)
        card_layout.addLayout(row)
        outer.addWidget(card)

        projects_title = QLabel("Your projects")
        projects_title.setObjectName("SectionTitle")
        outer.addWidget(projects_title)
        self.projects_grid = QGridLayout()
        self.projects_grid.setSpacing(12)
        for column in range(3):
            self.projects_grid.setColumnStretch(column, 1)
        outer.addLayout(self.projects_grid)
        self.empty_label = QLabel("No games yet. Describe one above and AVEN will build it.")
        self.empty_label.setObjectName("HelpText")
        outer.addWidget(self.empty_label)
        outer.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def _build_workspace(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        back = QPushButton("← All projects")
        back.clicked.connect(self.show_dashboard)
        bar.addWidget(back)
        self.status_chip_holder = QHBoxLayout()
        bar.addLayout(self.status_chip_holder)
        bar.addStretch(1)
        self.play_button = QPushButton("▶  Play")
        self.play_button.setObjectName("PrimaryButton")
        self.play_button.setToolTip("Open the game in your web browser (it cannot use the network)")
        self.play_button.clicked.connect(self.play)
        self.export_button = QPushButton("Export…")
        self.export_button.setToolTip("Save the game as a .zip you can share")
        self.export_button.clicked.connect(self.export)
        self.folder_button = QPushButton("Open folder")
        self.folder_button.clicked.connect(self.open_folder)
        for button in (self.play_button, self.export_button, self.folder_button):
            bar.addWidget(button)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)
        plan_title = QLabel("Game design")
        plan_title.setObjectName("SectionTitle")
        left_layout.addWidget(plan_title)
        self.plan_view = QTextBrowser()
        self.plan_view.setObjectName("PlanView")
        self.plan_view.setOpenLinks(False)
        left_layout.addWidget(self.plan_view, 3)

        self.build_button = QPushButton("Build game")
        self.build_button.setObjectName("PrimaryButton")
        self.build_button.clicked.connect(self.build)
        left_layout.addWidget(self.build_button)
        change_title = QLabel("Request a change")
        change_title.setObjectName("SectionTitle")
        left_layout.addWidget(change_title)
        self.change_input = QPlainTextEdit()
        self.change_input.setObjectName("StudioInput")
        self.change_input.setPlaceholderText("For example: add a boss after level 3, make the player faster…")
        self.change_input.setFixedHeight(70)
        left_layout.addWidget(self.change_input)
        actions = QHBoxLayout()
        self.change_button = QPushButton("Apply change")
        self.change_button.clicked.connect(self.apply_change)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.hide()
        actions.addWidget(self.change_button)
        actions.addStretch(1)
        actions.addWidget(self.stop_button)
        left_layout.addLayout(actions)
        progress_title = QLabel("Progress")
        progress_title.setObjectName("SectionTitle")
        left_layout.addWidget(progress_title)
        self.progress_list = QListWidget()
        self.progress_list.setObjectName("ProgressList")
        left_layout.addWidget(self.progress_list, 2)
        splitter.addWidget(left)

        self.tabs = QTabWidget()
        code_tab = QWidget()
        code_layout = QHBoxLayout(code_tab)
        code_layout.setContentsMargins(8, 8, 8, 8)
        self.file_list = QListWidget()
        self.file_list.setMaximumWidth(190)
        self.file_list.currentTextChanged.connect(self._show_file)
        self.code_view = QTextBrowser()
        self.code_view.setObjectName("CodeViewer")
        self.code_view.setLineWrapMode(QTextBrowser.LineWrapMode.NoWrap)
        code_layout.addWidget(self.file_list)
        code_layout.addWidget(self.code_view, 1)
        self.tabs.addTab(code_tab, "Code")
        self.checks_view = QTextBrowser()
        self.checks_view.setObjectName("ChecksView")
        self.tabs.addTab(self.checks_view, "Checks")
        self.history_view = QTextBrowser()
        self.tabs.addTab(self.history_view, "History")
        splitter.addWidget(self.tabs)
        splitter.setSizes([380, 620])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        return page

    # --- state ------------------------------------------------------------------------
    @property
    def busy(self) -> bool:
        return self.job is not None

    def set_status(self, status) -> None:
        self._status = status
        self.setup_label.setText("" if status.ready else status.problem)
        self.create_button.setText("Download model" if status.needs_download else "Create game")
        self.model_picker.set_current(status.aven_model)

    def refresh(self) -> list[Project]:
        try:
            projects = self.store.list()
        except StorageError as exc:
            QMessageBox.warning(self, "Projects", str(exc))
            return []
        while self.projects_grid.count():
            item = self.projects_grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for index, project in enumerate(projects):
            card = ProjectCard(project)
            card.clicked.connect(self.open_project)
            self.projects_grid.addWidget(card, index // 3, index % 3)
        self.empty_label.setVisible(not projects)
        return projects

    def show_dashboard(self) -> None:
        self.project = None
        self.title_label.setText("Made With AVEN")
        self.subtitle_label.setText("Describe a game and AVEN builds it")
        self.refresh()
        self.stack.setCurrentIndex(0)

    def open_project(self, project_id: int) -> None:
        if self.busy and (self.project is None or self.project.id != project_id):
            QMessageBox.information(self, "Busy", "Wait for the current task to finish, or press Stop.")
            return
        project = self.store.get(project_id)
        if project is None:
            self.show_dashboard()
            return
        self.project = project
        self.stack.setCurrentIndex(1)
        self._render_project()

    def _render_project(self) -> None:
        project = self.project
        if project is None:
            return
        self.title_label.setText(project.title)
        self.subtitle_label.setText(
            f"Made With AVEN · version {project.version}" if project.version else "Made With AVEN"
        )
        while self.status_chip_holder.count():
            item = self.status_chip_holder.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.status_chip_holder.addWidget(_status_chip(project.status))
        self.plan_view.setHtml(self._plan_html(project))
        has_code = bool(project.version)
        self.build_button.setText("Rebuild from the design" if has_code else "Build game")
        self.build_button.setVisible(bool(project.plan))
        for button in (self.play_button, self.export_button):
            button.setEnabled(has_code)
        self.change_button.setEnabled(has_code)
        self.file_list.clear()
        self._files = project.files()
        for name in self._files:
            self.file_list.addItem(name)
        if self._files:
            self.file_list.setCurrentRow(0)
        self.checks_view.setHtml(self._checks_html(project))
        self.history_view.setHtml(self._history_html(project))
        self._set_busy(self.busy)

    def _plan_html(self, project: Project) -> str:
        plan = project.plan
        if not plan:
            return f"<p><b>Description</b></p><p>{html.escape(project.description)}</p><p>No design yet.</p>"
        esc = html.escape
        parts = [f"<h2>{esc(str(plan.get('title', '')))}</h2>",
                 f"<p><i>{esc(str(plan.get('genre', '')))}</i></p>",
                 f"<p>{esc(str(plan.get('summary', '')))}</p>"]  # fmt: skip
        if plan.get("goal"):
            parts.append(f"<p><b>Goal:</b> {esc(str(plan['goal']))}</p>")
        for key, title in (("controls", "Controls"), ("scenes", "Scenes")):
            if plan.get(key):
                parts.append(
                    f"<p><b>{title}</b></p><ul>" + "".join(f"<li>{esc(str(v))}</li>" for v in plan[key]) + "</ul>"
                )
        for key, title in (("systems", "Systems"), ("entities", "Characters and objects")):
            if plan.get(key):
                items = "".join(f"<li><b>{esc(i['name'])}</b>: {esc(i['description'])}</li>" for i in plan[key])
                parts.append(f"<p><b>{title}</b></p><ul>{items}</ul>")
        if plan.get("scope_notes"):
            parts.append(f"<p><b>Simplified:</b> {esc(str(plan['scope_notes']))}</p>")
        return "".join(parts)

    def _checks_html(self, project: Project) -> str:
        builds = [h for h in project.history if h.get("kind") in ("build", "change")]
        if not builds:
            return "<p>No game has been checked yet.</p>"
        last = builds[-1]
        esc = html.escape
        if last.get("validated"):
            head = "<h3>✓ Version {} passed every check</h3>".format(last.get("version"))
        else:
            head = "<h3>⚠ Version {} did not pass every check</h3>".format(last.get("version"))
        items = "".join(f"<li>✓ {esc(c)}</li>" for c in last.get("checks", []))
        items += "".join(f"<li>✗ {esc(e)}</li>" for e in last.get("errors", []))
        note = (
            "<p>Checks: JavaScript syntax, safety rules (no network, no eval, no external files) and a "
            "sandboxed test run with simulated keys. They catch crashes, not every bug: play it to be sure.</p>"
        )
        return head + f"<ul>{items}</ul>" + note

    def _history_html(self, project: Project) -> str:
        rows = []
        for h in reversed(project.history):
            kind = {"plan": "Design created", "build": "Game built", "change": "Change applied"}.get(
                h.get("kind"), h.get("kind")
            )
            state = "" if h.get("kind") == "plan" else (" ✓ validated" if h.get("validated") else " ⚠ not validated")
            request = (
                f"<br><small>{html.escape(h.get('request', ''))[:200]}</small>" if h.get("kind") == "change" else ""
            )
            version = f" (v{h['version']})" if h.get("version") else ""
            rows.append(
                f"<li><b>{html.escape(str(kind))}{version}</b>{state}"
                f"<br><small>{html.escape(h.get('at', ''))}</small>{request}</li>"
            )
        return "<ul>" + "".join(rows) + "</ul>" if rows else "<p>No history yet.</p>"

    def _show_file(self, name: str) -> None:
        text = getattr(self, "_files", {}).get(name, "")
        language = "json" if name.endswith(".json") else "javascript"
        body = highlight_code_html(text, language, self.palette_.dark)
        self.code_view.setHtml(
            f'<pre style="font-family: {html.escape(CODE_FONT_FAMILIES, quote=True)}; '
            f'color: {self.palette_.text}; margin: 0;">{body}</pre>'
        )

    def _set_busy(self, busy: bool) -> None:
        self.stop_button.setVisible(busy)
        for button in (self.build_button, self.change_button, self.create_button):
            button.setEnabled(
                not busy and (button is not self.change_button or bool(self.project and self.project.version))
            )
        self.description_input.setReadOnly(busy)

    def _log(self, message: str) -> None:
        item = QListWidgetItem(f"{time.strftime('%H:%M:%S')}  {message}")
        self.progress_list.addItem(item)
        self.progress_list.scrollToBottom()

    # --- AI access ----------------------------------------------------------------------
    def _ready(self) -> bool:
        status = self.chat_service.status("made")
        if status.ready:
            return True
        if status.needs_download:
            self.download_requested.emit()
            return self.chat_service.status("made").ready
        if QMessageBox.question(
            self, "Set up an AI provider", f"{status.problem}\n\nOpen Settings now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:  # fmt: skip
            self.settings_requested.emit()
        return False

    def _completer(self, job: StudioJob):
        service = self.chat_service
        model = service.settings.resolved_model()
        provider = service.create_provider(category="made")

        def complete(system: str, user: str, max_tokens: int, on_text) -> str:
            request = ChatRequest(
                model=model, system_prompt=system, messages=[ChatMessage("user", user)],
                max_tokens=max_tokens, cancel_event=job.cancel_event,
            )  # fmt: skip
            parts: list[str] = []
            last = 0.0
            for event in service.stream(request, provider):
                if job.cancel_event.is_set():
                    raise CancelledError
                if event.kind == "text":
                    parts.append(event.text)
                    now = time.monotonic()
                    if now - last > 0.25:
                        job.signals.text.emit(sum(len(p) for p in parts))
                        last = now
            if job.cancel_event.is_set():
                raise CancelledError
            return "".join(parts)

        return complete

    def _start(self, task, on_done) -> None:
        self.cancel_event = threading.Event()
        job = StudioJob(task, self.cancel_event)
        job.signals.progress.connect(self._log)
        job.signals.text.connect(self._on_text)
        job.signals.plan.connect(self._on_plan)
        job.signals.succeeded.connect(on_done)
        job.signals.failed.connect(self._on_failed)
        job.signals.done.connect(self._on_done)
        self.job = job
        self._set_busy(True)
        job.start()

    def _on_text(self, characters: int) -> None:
        """Show how much of the current AI reply has arrived on the latest progress line."""
        item = self.progress_list.item(self.progress_list.count() - 1)
        if item is not None:
            item.setText(item.text().split("  ·  ")[0] + f"  ·  {characters:,} characters written")

    def _on_done(self) -> None:
        self.job = None
        self._set_busy(False)
        if self.project is not None:
            self._render_project()

    def _on_failed(self, message: str) -> None:
        self._log(f"✗ {message}")
        if message != "Stopped.":
            QMessageBox.warning(self, "Made With AVEN", message)

    def stop(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
            self._log("Stopping…")

    # --- actions ------------------------------------------------------------------------
    def create_game(self) -> None:
        description = self.description_input.toPlainText().strip()
        if self.chat_service.status("made").needs_download and not description:
            self.download_requested.emit()  # the button reads "Download model"
            return
        if not description:
            QMessageBox.information(self, "Made With AVEN", "Describe your game first.")
            return
        if self.busy or not self._ready():
            return
        try:
            project = self.store.create(description, self.chat_service.settings.model)
        except (StorageError, ValueError) as exc:
            QMessageBox.warning(self, "Made With AVEN", str(exc))
            return
        self.description_input.clear()
        self.project = project
        self.progress_list.clear()
        self.stack.setCurrentIndex(1)
        self._render_project()
        self.projects_changed.emit()
        model = self.chat_service.settings.model
        complete = self._completer

        def task(job: StudioJob) -> BuildResult:
            pipeline = GamePipeline(complete(job), job.signals.progress.emit)
            plan = pipeline.plan(description)
            job.signals.plan.emit(plan)
            return pipeline.build(plan)

        self._start(task, lambda result: self._on_built(result, "build", description, model))

    def _on_plan(self, plan: dict) -> None:
        if self.project is None:
            return
        try:
            self.store.save_plan(self.project, plan)
        except StorageError as exc:
            self._log(f"✗ {exc}")
        self._log(f"Design ready: {plan.get('title')}")
        self._render_project()
        self.projects_changed.emit()

    def _on_built(self, result: BuildResult, kind: str, request: str, model: str) -> None:
        if self.project is None or result is None:
            return
        try:
            self.store.save_version(
                self.project, result.code, result.validated, kind, request,
                result.report.errors, result.report.checks, model,
            )  # fmt: skip
        except StorageError as exc:
            QMessageBox.warning(self, "Made With AVEN", str(exc))
            return
        if result.validated:
            self._log(f"✓ Version {self.project.version} passed every check. Press Play to try it.")
        else:
            self._log(f"⚠ Version {self.project.version} still has problems (see Checks). You can request a fix.")
            self.tabs.setCurrentIndex(1)
        self.projects_changed.emit()

    def build(self) -> None:
        project = self.project
        if project is None or not project.plan or self.busy or not self._ready():
            return
        plan, model = project.plan, self.chat_service.settings.model
        complete = self._completer

        def task(job: StudioJob) -> BuildResult:
            return GamePipeline(complete(job), job.signals.progress.emit).build(plan)

        self._start(task, lambda result: self._on_built(result, "build", "Build from the design", model))

    def apply_change(self) -> None:
        project = self.project
        change = self.change_input.toPlainText().strip()
        if project is None or self.busy:
            return
        if not change:
            QMessageBox.information(self, "Made With AVEN", "Describe the change first.")
            return
        if not self._ready():
            return
        plan, code, model = project.plan, project.code(), self.chat_service.settings.model
        complete = self._completer
        self.change_input.clear()

        def task(job: StudioJob) -> BuildResult:
            return GamePipeline(complete(job), job.signals.progress.emit).change(plan, code, change)

        self._start(task, lambda result: self._on_built(result, "change", change, model))

    def play(self) -> None:
        project = self.project
        if project is None or not project.page_path.exists():
            return
        if project.status != "validated" and QMessageBox.question(
            self, "Not validated",
            "This version did not pass every check and may not work. Open it anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:  # fmt: skip
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(project.page_path)))

    def export(self) -> None:
        project = self.project
        if project is None:
            return
        target, _ = QFileDialog.getSaveFileName(self, "Export game", f"{project.title}.zip", "Zip archive (*.zip)")
        if not target:
            return
        try:
            self.store.export(project, Path(target))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self._log(f"Exported to {target}")

    def open_folder(self) -> None:
        if self.project is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project.path)))

    def apply_palette(self, palette: Palette) -> None:
        self.palette_ = palette
        if self.project is not None and self.file_list.currentItem() is not None:
            self._show_file(self.file_list.currentItem().text())
