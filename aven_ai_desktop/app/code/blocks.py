"""Find the code blocks (and the file each one belongs to) in an assistant reply."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.rendering.markdown_renderer import normalize_language, split_segments

# "**File: src/main.py**", "File: `src/main.py`", "### src/main.py" just before a block.
_FILE_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?\s*(?:file(?:name)?\s*:\s*)?"
    r"`?(?P<path>[\w.\-/\\ ]+\.[\w]{1,10})`?\s*(?:\*\*|__)?\s*:?\s*$",
    re.I,
)
# Language tag spellings in the info string, e.g. ```python title="src/app.py"
_INFO_PATH = re.compile(r"""(?:title|file|path|filename)\s*=\s*["']?([^"'\s]+)""", re.I)

EXTENSION_LANGUAGES = {
    ".py": "python", ".pyw": "python", ".cs": "csharp", ".js": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "tsx", ".java": "java",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".h": "cpp", ".c": "cpp", ".html": "html",
    ".htm": "html", ".css": "css", ".sql": "sql", ".json": "json", ".md": "markdown", ".txt": "text",
    ".toml": "toml", ".yaml": "yaml", ".yml": "yaml", ".sh": "bash", ".ps1": "powershell",
}  # fmt: skip
LANGUAGE_ALIASES = {
    "c#": "csharp",
    "cs": "csharp",
    "js": "javascript",
    "ts": "typescript",
    "c++": "cpp",
    "py": "python",
}


@dataclass(frozen=True)
class CodeBlock:
    index: int
    language: str  # normalized, e.g. "python", "csharp", "tsx" ("" when unknown)
    code: str
    path: str = ""  # relative file path the reply gave for this block ("" when none)

    @property
    def label(self) -> str:
        return self.path or f"block {self.index + 1}" + (f" ({self.language})" if self.language else "")


def _language(tag: str, path: str) -> str:
    tag = (tag or "").strip().split()[0].lower() if tag and tag.strip() else ""
    tag = LANGUAGE_ALIASES.get(tag, tag)
    if path:
        by_ext = EXTENSION_LANGUAGES.get(PurePosixPath(path.replace("\\", "/")).suffix.lower(), "")
        if by_ext and (not tag or tag in ("text", "plaintext")):
            return by_ext
        if by_ext == "tsx" and tag == "typescript":
            return "tsx"
    return normalize_language(tag) if tag else ""


def extract_blocks(text: str) -> list[CodeBlock]:
    """Code blocks in a reply, each with the file path written just before it (if any)."""
    blocks: list[CodeBlock] = []
    previous_prose = ""
    for segment in split_segments(text):
        if segment.kind != "code":
            previous_prose = segment.text
            continue
        path = ""
        info_path = _INFO_PATH.search(segment.language or "")
        if info_path:
            path = info_path.group(1)
        else:
            lines = [line for line in previous_prose.splitlines() if line.strip()]
            match = _FILE_LINE.match(lines[-1]) if lines else None
            if match and ("/" in match.group("path") or "." in match.group("path")):
                path = match.group("path").strip().replace("\\", "/")
        tag = (segment.language or "").split()[0] if segment.language else ""
        blocks.append(CodeBlock(len(blocks), _language(tag, path), segment.text, path))
        previous_prose = ""
    return blocks
