"""Safe Markdown → HTML conversion and code highlighting for chat messages.

Safety model:
* Raw HTML in model output is never rendered - Markdown's HTML passthrough is
  disabled, so tags such as ``<script>`` or ``<img onerror=…>`` appear as text.
* Links are only kept for ``http``, ``https`` and ``mailto``; everything else
  (``javascript:``, ``file:``, ``data:``…) becomes plain text.
* Images are never loaded; they are shown as a link to their source.
* The resulting HTML is displayed in Qt's rich-text engine, which has no
  scripting support.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

ALLOWED_LINK_SCHEMES = ("http", "https", "mailto")

# Aliases for languages Pygments names differently.
LANGUAGE_ALIASES = {
    "luau": "lua",
    "roblox": "lua",
    "unity": "csharp",
    "c#": "csharp",
    "cs": "csharp",
    "c++": "cpp",
    "ue": "cpp",
    "unreal": "cpp",
    "sh": "bash",
    "shell": "bash",
    "ps1": "powershell",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "yml": "yaml",
    "md": "markdown",
}


# --- segmentation -------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    kind: str  # "markdown" or "code"
    text: str
    language: str = ""
    closed: bool = True


_FENCE_OPEN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>[^`\n]*)$")


def split_segments(text: str) -> list[Segment]:
    """Split a message into Markdown prose and fenced code blocks.

    Handles an unterminated fence (common while a response is streaming) by
    treating the remainder as an open code block.
    """
    segments: list[Segment] = []
    prose: list[str] = []
    code: list[str] = []
    fence = ""
    language = ""

    def flush_prose() -> None:
        joined = "\n".join(prose).strip("\n")
        if joined.strip():
            segments.append(Segment("markdown", joined))
        prose.clear()

    for line in text.split("\n"):
        if not fence:
            match = _FENCE_OPEN.match(line)
            if match:
                flush_prose()
                fence = match.group("fence")
                info = match.group("info").strip().split()
                language = info[0].lower() if info else ""
                code.clear()
            else:
                prose.append(line)
        else:
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            if indent <= 3 and stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                segments.append(Segment("code", "\n".join(code), language, True))
                fence = ""
                language = ""
                code.clear()
            else:
                code.append(line)

    if fence:
        segments.append(Segment("code", "\n".join(code), language, False))
    else:
        flush_prose()
    return segments


# --- markdown -----------------------------------------------------------------------


def _is_safe_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    scheme = urlparse(url).scheme.lower()
    return scheme in ALLOWED_LINK_SCHEMES


class _SanitizeTree(Treeprocessor):
    def run(self, root: ET.Element) -> None:
        for parent in root.iter():
            for index, child in enumerate(list(parent)):
                if child.tag == "img":
                    parent.remove(child)
                    src = child.get("src", "")
                    alt = child.get("alt") or "image"
                    replacement = ET.Element("a" if _is_safe_url(src) else "span")
                    if _is_safe_url(src):
                        replacement.set("href", src)
                    replacement.text = f"[{alt}]"
                    replacement.tail = child.tail
                    parent.insert(index, replacement)
                elif child.tag == "a":
                    href = child.get("href", "")
                    for attr in list(child.attrib):
                        if attr not in ("href", "title"):
                            del child.attrib[attr]
                    if not _is_safe_url(href):
                        child.tag = "span"
                        child.attrib.pop("href", None)
                elif child.tag == "table":
                    child.set("border", "1")
                    child.set("cellspacing", "0")
                    child.set("cellpadding", "6")


class _SafeExtension(Extension):
    def extendMarkdown(self, md: markdown.Markdown) -> None:  # noqa: N802 (API name)
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.treeprocessors.register(_SanitizeTree(md), "aven_sanitize", 0)


def _new_markdown() -> markdown.Markdown:
    return markdown.Markdown(extensions=["tables", "sane_lists", _SafeExtension()], output_format="html")


_md = _new_markdown()


def markdown_to_html(text: str) -> str:
    _md.reset()
    try:
        return _md.convert(text)
    except Exception:  # pragma: no cover - extremely defensive
        return f"<p>{html.escape(text)}</p>".replace("\n", "<br>")


# --- code highlighting ------------------------------------------------------------------


def normalize_language(language: str) -> str:
    language = (language or "").strip().lower()
    return LANGUAGE_ALIASES.get(language, language)


def display_language(language: str) -> str:
    if not language:
        return "code"
    pretty = {"luau": "Luau", "csharp": "C#", "cs": "C#", "c#": "C#", "cpp": "C++", "c++": "C++"}
    return pretty.get(language.lower(), language)


@lru_cache(maxsize=4)
def _formatter(dark: bool) -> HtmlFormatter:
    return HtmlFormatter(noclasses=True, nowrap=True, style="monokai" if dark else "friendly")


def highlight_code_html(code: str, language: str, dark: bool) -> str:
    """Return HTML spans (no wrapper) with inline colors for ``code``."""
    lexer = None
    name = normalize_language(language)
    if name:
        try:
            lexer = get_lexer_by_name(name, stripnl=False, ensurenl=False)
        except ClassNotFound:
            lexer = None
    if lexer is None and 0 < len(code) < 20_000:
        try:
            lexer = guess_lexer(code, stripnl=False, ensurenl=False)
        except ClassNotFound:
            lexer = None
    if lexer is None or len(code) > 200_000:
        return html.escape(code)
    result = highlight(code, lexer, _formatter(dark))
    return result[:-1] if result.endswith("\n") and not code.endswith("\n") else result
