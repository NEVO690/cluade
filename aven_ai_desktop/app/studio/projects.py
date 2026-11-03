"""Made With AVEN projects: a list in the database and a folder of files per project.

Folder layout (inside the AVEN AI data folder, ``projects/<folder>/``):

    project.json          design plan and history of builds and changes
    game.js               the current game code
    index.html            the current playable page (locked down, see app.studio.page)
    versions/v3/game.js   every validated or attempted version, kept for going back
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.paths import user_data_dir
from app.storage.database import Database, StorageError
from app.studio.page import build_page
from app.studio.sandbox import engine_source

STATUSES = ("draft", "validated", "needs_fixes")


def projects_dir() -> Path:
    return user_data_dir() / "projects"


@dataclass
class Project:
    id: int
    title: str
    description: str
    status: str
    model: str | None
    version: int
    folder: str
    created_at: str
    updated_at: str
    root: Path
    plan: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return self.root / self.folder

    @property
    def page_path(self) -> Path:
        return self.path / "index.html"

    def code(self) -> str:
        try:
            return (self.path / "game.js").read_text(encoding="utf-8")
        except OSError:
            return ""

    def files(self) -> dict[str, str]:
        """The project's viewable files: name -> text."""
        out = {}
        for name in ("game.js", "project.json"):
            with contextlib.suppress(OSError):
                out[name] = (self.path / name).read_text(encoding="utf-8")
        out["aven_game.js (engine)"] = engine_source()
        return out


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "game"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


class ProjectStore:
    """Use from the GUI thread (it shares the app's database connection)."""

    def __init__(self, db: Database, root: Path | None = None) -> None:
        self.conn = db.conn
        self.root = root or projects_dir()

    def _row(self, row: sqlite3.Row) -> Project:
        project = Project(
            row["id"], row["title"], row["description"], row["status"], row["model"], row["version"],
            row["folder"], row["created_at"], row["updated_at"], self.root,
        )  # fmt: skip
        try:
            meta = json.loads((project.path / "project.json").read_text(encoding="utf-8"))
            project.plan = meta.get("plan", {}) if isinstance(meta, dict) else {}
            project.history = meta.get("history", []) if isinstance(meta, dict) else []
        except (OSError, ValueError):
            pass
        return project

    def list(self) -> list[Project]:
        try:
            rows = self.conn.execute("SELECT * FROM game_projects ORDER BY updated_at DESC, id DESC").fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Could not read projects: {exc}") from exc
        return [self._row(r) for r in rows]

    def get(self, project_id: int) -> Project | None:
        row = self.conn.execute("SELECT * FROM game_projects WHERE id = ?", (project_id,)).fetchone()
        return self._row(row) if row else None

    def create(self, description: str, model: str) -> Project:
        description = description.strip()
        if not description:
            raise ValueError("Describe the game first.")
        title = description.splitlines()[0][:60]
        folder = _slug(title)
        try:
            (self.root / folder).mkdir(parents=True, exist_ok=False)
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO game_projects (title, description, model, folder) VALUES (?, ?, ?, ?)",
                    (title, description, model, folder),
                )
        except (OSError, sqlite3.Error) as exc:
            raise StorageError(f"Could not create the project: {exc}") from exc
        project = self.get(int(cur.lastrowid))
        self._write_meta(project)
        return project

    def _write_meta(self, project: Project) -> None:
        data = {"title": project.title, "description": project.description, "plan": project.plan,
                "history": project.history}  # fmt: skip
        (project.path / "project.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _touch(self, project: Project) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE game_projects SET title = ?, status = ?, model = ?, version = ?, updated_at = ? WHERE id = ?",
                (project.title, project.status, project.model, project.version, _now(), project.id),
            )

    def save_plan(self, project: Project, plan: dict) -> None:
        project.plan = plan
        if plan.get("title"):
            project.title = str(plan["title"])[:60]
        project.history.append({"at": _now(), "kind": "plan"})
        try:
            self._write_meta(project)
            self._touch(project)
        except (OSError, sqlite3.Error) as exc:
            raise StorageError(f"Could not save the plan: {exc}") from exc

    def save_version(self, project: Project, code: str, validated: bool, kind: str, request: str,
                     errors: list[str], checks: list[str], model: str) -> None:  # fmt: skip
        """Save a new version of the game (validated or not) and make it the current one."""
        project.version += 1
        project.status = "validated" if validated else "needs_fixes"
        project.model = model
        project.history.append({
            "at": _now(), "kind": kind, "version": project.version, "request": request[:2000],
            "validated": validated, "errors": errors[:20], "checks": checks,
        })  # fmt: skip
        try:
            version_dir = project.path / "versions" / f"v{project.version}"
            version_dir.mkdir(parents=True, exist_ok=True)
            (version_dir / "game.js").write_text(code, encoding="utf-8", newline="\n")
            (project.path / "game.js").write_text(code, encoding="utf-8", newline="\n")
            (project.path / "index.html").write_text(build_page(project.title, code), encoding="utf-8")
            self._write_meta(project)
            self._touch(project)
        except (OSError, sqlite3.Error) as exc:
            raise StorageError(f"Could not save the game: {exc}") from exc

    def rename(self, project: Project, title: str) -> None:
        project.title = title.strip()[:60] or project.title
        self._write_meta(project)
        self._touch(project)

    def delete(self, project: Project) -> None:
        import shutil

        with self.conn:
            self.conn.execute("DELETE FROM game_projects WHERE id = ?", (project.id,))
        if project.path.resolve().parent == self.root.resolve():
            shutil.rmtree(project.path, ignore_errors=True)

    def export(self, project: Project, target: Path) -> Path:
        """Zip the playable game: index.html (self-contained), the sources and a README."""
        code = project.code()
        if not code:
            raise ValueError("This project has no game yet.")
        status = "validated by AVEN checks" if project.status == "validated" else "NOT validated"
        readme = (
            f"{project.title}\n\nMade With AVEN.\n\nOpen index.html in a web browser to play.\n"
            f"game.js is the game code; aven_game.js is the AVEN game engine it runs on.\n"
            f"Status when exported: {status}.\n"
        )
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("index.html", build_page(project.title, code))
            archive.writestr("game.js", code)
            archive.writestr("aven_game.js", engine_source())
            archive.writestr("README.txt", readme)
        return target
