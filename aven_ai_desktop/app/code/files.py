"""Safe file handling for coding categories: attaching project files and saving generated ones.

Attaching reads text files only (size-limited, skipping binaries and build folders).
Saving writes only inside the folder the user chose: absolute paths, drive letters,
``..`` and Windows reserved names are rejected, so a reply can never write elsewhere.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.ai.prompts import FILES_BEGIN, FILES_END
from app.code.blocks import CodeBlock

MAX_FILE_BYTES = 200_000
MAX_FILES = 200
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", ".idea", ".vs", ".vscode", "bin", "obj",
    # Unity generated folders
    "Library", "Temp", "Logs", "UserSettings", "MemoryCaptures",
}  # fmt: skip
TEXT_EXTENSIONS = {
    ".py", ".pyw", ".pyi", ".cs", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".java", ".kt", ".cpp", ".cc", ".cxx",
    ".c", ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".swift", ".lua", ".luau", ".sql", ".html", ".htm", ".css",
    ".scss", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".md", ".txt", ".rst", ".xml", ".csv", ".sh",
    ".ps1", ".bat", ".gradle", ".shader", ".hlsl", ".uxml", ".uss", ".asmdef", ".env.example", ".gitignore",
}  # fmt: skip
_WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", re.I)


class UnsafePathError(ValueError):
    """A generated file path points outside the chosen folder or is not a valid name."""


@dataclass(frozen=True)
class AttachedFile:
    path: str  # display path, relative to the folder it came from
    text: str

    @property
    def size(self) -> int:
        return len(self.text.encode("utf-8"))


def _is_text_file(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() in TEXT_EXTENSIONS or name in ("dockerfile", "makefile", "requirements.txt")


def read_attachment(path: Path, display: str | None = None) -> AttachedFile:
    """Read one text file to attach (raises ValueError with a user-facing reason)."""
    if not path.is_file():
        raise ValueError(f"{path.name} is not a file.")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"{path.name} is larger than {MAX_FILE_BYTES // 1000} KB.")
    data = path.read_bytes()
    if b"\0" in data[:8000]:
        raise ValueError(f"{path.name} looks like a binary file.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return AttachedFile(display or path.name, text.replace("\r\n", "\n"))


def collect_folder(folder: Path) -> tuple[list[AttachedFile], list[str]]:
    """Text files in a project folder (skipping build and dependency folders); returns (files, skipped notes)."""
    files: list[AttachedFile] = []
    skipped: list[str] = []
    for root, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            path = Path(root) / name
            rel = path.relative_to(folder).as_posix()
            if not _is_text_file(path):
                continue
            if len(files) >= MAX_FILES:
                skipped.append(f"more than {MAX_FILES} files; the rest were left out")
                return files, skipped
            try:
                files.append(read_attachment(path, rel))
            except (OSError, ValueError) as exc:
                skipped.append(f"{rel}: {exc}")
    return files, skipped


def attachment_block(files: list[AttachedFile], max_chars: int) -> tuple[str, list[str]]:
    """The text added to a message for attached files, within ``max_chars``; returns (block, left out)."""
    if not files:
        return "", []
    tree = "\n".join(f"- {f.path}" for f in files)
    parts = [f"{FILES_BEGIN}\nProject files:\n{tree}\n"]
    used = len(parts[0])
    left_out = []
    for f in files:
        fence = "````" if "```" in f.text else "```"
        language = PurePosixPath(f.path).suffix.lstrip(".")
        chunk = f"\n### {f.path}\n{fence}{language}\n{f.text.rstrip()}\n{fence}\n"
        if used + len(chunk) > max_chars:
            left_out.append(f.path)
            continue
        parts.append(chunk)
        used += len(chunk)
    parts.append(FILES_END)
    return "".join(parts), left_out


def split_attachments(message: str) -> tuple[str, list[str]]:
    """Split a stored user message into (text the user typed, attached file paths)."""
    start = message.find(FILES_BEGIN)
    if start < 0:
        return message, []
    end = message.find(FILES_END, start)
    block = message[start : end if end >= 0 else len(message)]
    paths = re.findall(r"^### (.+)$", block, re.M)
    rest = (message[:start] + (message[end + len(FILES_END) :] if end >= 0 else "")).strip()
    return rest, paths


# --- saving generated files ------------------------------------------------------------------


def safe_relative_path(raw: str) -> PurePosixPath:
    """Validate a path from a reply; raises UnsafePathError unless it is a plain relative path."""
    text = raw.strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[a-zA-Z]:", text) or "\0" in text:
        raise UnsafePathError(f"{raw!r} is not a relative path")
    path = PurePosixPath(text)
    for part in path.parts:
        if part in ("..", ".") or part.startswith("~") or _WINDOWS_RESERVED.match(part) or part.endswith((" ", ".")):
            raise UnsafePathError(f"{raw!r} is not allowed")
        if re.search(r'[<>:"|?*]', part):
            raise UnsafePathError(f"{raw!r} contains characters that are not allowed in file names")
    return path


@dataclass(frozen=True)
class PlannedFile:
    relative: PurePosixPath
    target: Path
    content: str
    exists: bool


def plan_save(blocks: list[CodeBlock], folder: Path) -> tuple[list[PlannedFile], list[str]]:
    """Files that would be written for the blocks that name a path; returns (files, problems)."""
    folder = folder.resolve()
    planned: dict[str, PlannedFile] = {}
    problems: list[str] = []
    for block in blocks:
        if not block.path:
            continue
        try:
            relative = safe_relative_path(block.path)
        except UnsafePathError as exc:
            problems.append(str(exc))
            continue
        target = (folder / relative).resolve()
        if folder not in target.parents:
            problems.append(f"{block.path!r} points outside the folder")
            continue
        content = block.code if block.code.endswith("\n") else block.code + "\n"
        planned[str(relative)] = PlannedFile(relative, target, content, target.exists())  # last block wins
    return list(planned.values()), problems


def write_files(files: list[PlannedFile]) -> list[Path]:
    written = []
    for f in files:
        f.target.parent.mkdir(parents=True, exist_ok=True)
        f.target.write_text(f.content, encoding="utf-8", newline="\n")
        written.append(f.target)
    return written
