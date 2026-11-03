"""Static checks for code in assistant replies. Nothing here runs the code.

* Python: compiled to an AST (syntax) and checked with pyflakes (undefined names,
  unused imports, redefinitions).
* C#, JavaScript, TypeScript/TSX, Java, C++, HTML, CSS: parsed with tree-sitter
  grammars; parse errors are reported with their line.
* Unity: common mistakes in MonoBehaviours (file and class names, GetComponent or Find
  every frame, physics in Update, missing ``using UnityEngine``).

Languages without a checker are reported as "not checked", never as passing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import PurePosixPath

from app.code.blocks import CodeBlock, extract_blocks

log = logging.getLogger(__name__)

ERROR, WARNING, INFO = "error", "warning", "info"


@dataclass(frozen=True)
class Finding:
    severity: str
    block: str  # CodeBlock.label
    line: int  # 1-based, 0 when not tied to a line
    message: str

    def __str__(self) -> str:
        where = f"{self.block}, line {self.line}" if self.line else self.block
        return f"{where}: {self.message}"


@dataclass
class Report:
    checked: list[str] = field(default_factory=list)  # labels of blocks that were checked
    unchecked: list[str] = field(default_factory=list)  # blocks in a language without a checker
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        return bool(self.checked) and not self.errors

    def summary(self) -> str:
        if not self.checked and not self.unchecked:
            return ""
        parts = []
        if self.checked:
            noun = "block" if len(self.checked) == 1 else "blocks"
            if self.errors:
                parts.append(f"{len(self.errors)} problem{'s' if len(self.errors) != 1 else ''} found")
            else:
                parts.append(f"{len(self.checked)} code {noun} checked: no syntax errors")
            if self.warnings:
                parts.append(f"{len(self.warnings)} warning{'s' if len(self.warnings) != 1 else ''}")
        if self.unchecked:
            parts.append(f"{len(self.unchecked)} not checked")
        return ", ".join(parts)


# --- Python ---------------------------------------------------------------------------------


def check_python(block: CodeBlock) -> list[Finding]:
    try:
        compile(block.code, block.label, "exec", dont_inherit=True)  # parse only: never exec
    except SyntaxError as exc:
        return [Finding(ERROR, block.label, exc.lineno or 0, f"syntax error: {exc.msg}")]
    except ValueError as exc:  # e.g. null bytes
        return [Finding(ERROR, block.label, 0, f"invalid source: {exc}")]
    from pyflakes import api, reporter

    class _Collect(reporter.Reporter):
        def __init__(self) -> None:
            self.messages: list = []

        def flake(self, message) -> None:
            self.messages.append(message)

        def syntaxError(self, *args) -> None:  # noqa: N802 - pyflakes API
            pass

        def unexpectedError(self, *args) -> None:  # noqa: N802 - pyflakes API
            pass

    collect = _Collect()
    api.check(block.code, block.label, collect)
    findings = []
    for message in collect.messages:
        text = message.message % message.message_args
        name = type(message).__name__
        # Snippets often use names defined elsewhere, so undefined names are warnings.
        severity = WARNING if name in ("UndefinedName", "UndefinedExport", "UndefinedLocal") else INFO
        if name in ("UnusedImport", "UnusedVariable", "RedefinedWhileUnused", "ImportStarUsed"):
            severity = INFO
        findings.append(Finding(severity, block.label, message.lineno, text))
    return findings


# --- tree-sitter languages --------------------------------------------------------------------

_GRAMMARS = {
    "csharp": ("tree_sitter_c_sharp", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "java": ("tree_sitter_java", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "html": ("tree_sitter_html", "language"),
    "css": ("tree_sitter_css", "language"),
}


@cache
def _parser(language: str):
    import importlib

    import tree_sitter

    module_name, attr = _GRAMMARS[language]
    module = importlib.import_module(module_name)
    return tree_sitter.Parser(tree_sitter.Language(getattr(module, attr)()))


def _syntax_errors(node, out: list, limit: int = 5) -> list:
    if len(out) >= limit:
        return out
    if node.is_missing:
        out.append((node.start_point[0] + 1, f"missing {node.type!r}"))
    elif node.is_error:
        snippet = node.text.decode("utf-8", "replace").strip().splitlines()[0][:40] if node.text else ""
        out.append((node.start_point[0] + 1, f"syntax error near {snippet!r}" if snippet else "syntax error"))
        return out  # children of an error node add nothing useful
    for child in node.children:
        _syntax_errors(child, out, limit)
    return out


def check_tree_sitter(block: CodeBlock) -> list[Finding]:
    try:
        tree = _parser(block.language).parse(block.code.encode("utf-8"))
    except Exception as exc:  # a missing grammar must not break the chat
        log.warning("Parser unavailable for %s: %s", block.language, type(exc).__name__)
        return [Finding(INFO, block.label, 0, f"{block.language} checker unavailable")]
    if not tree.root_node.has_error:
        return []
    return [Finding(ERROR, block.label, line, message) for line, message in _syntax_errors(tree.root_node, [])]


# --- Unity ------------------------------------------------------------------------------------

_MONO = re.compile(r"\bclass\s+(\w+)\s*:\s*(?:\w+\.)*(MonoBehaviour|NetworkBehaviour|ScriptableObject)\b")
_FRAME_METHOD = re.compile(r"\bvoid\s+(Update|LateUpdate|FixedUpdate)\s*\(\s*\)\s*\{")
_EXPENSIVE = re.compile(
    r"\b(GetComponent(?:InChildren|InParent)?\s*<|GameObject\.Find\w*\s*\(|FindObjectOfType\w*\s*[<(]|FindObjectsOfType\w*\s*[<(]|FindFirstObjectByType\s*<)"
)
_PHYSICS = re.compile(r"\.(AddForce|AddTorque|MovePosition|MoveRotation)\s*\(|\.(velocity|linearVelocity)\s*=")


def _method_body(code: str, start: int) -> tuple[str, int]:
    """Text of the brace-delimited body starting at ``start`` (index of "{") and its end index."""
    depth = 0
    for i in range(start, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[start : i + 1], i
    return code[start:], len(code)


def check_unity(block: CodeBlock) -> list[Finding]:
    code = block.code
    findings: list[Finding] = []
    mono = _MONO.search(code)
    if mono and mono.group(2) == "MonoBehaviour" and "UnityEngine" not in code:
        findings.append(Finding(WARNING, block.label, 0, "uses MonoBehaviour but has no 'using UnityEngine;'"))
    if mono and block.path:
        stem = PurePosixPath(block.path).stem
        if stem != mono.group(1):
            findings.append(
                Finding(
                    ERROR,
                    block.label,
                    code[: mono.start()].count("\n") + 1,
                    f"class {mono.group(1)} must be in a file named {mono.group(1)}.cs for Unity to attach it",
                )
            )
    for match in _FRAME_METHOD.finditer(code):
        body, _end = _method_body(code, match.end() - 1)
        offset = match.end() - 1
        method = match.group(1)
        for call in _EXPENSIVE.finditer(body):
            line = code[: offset + call.start()].count("\n") + 1
            findings.append(
                Finding(
                    WARNING,
                    block.label,
                    line,
                    f"{call.group(1).rstrip('<( ')} runs every frame in {method}; cache it in Awake or Start",
                )
            )
        if method == "Update":
            for call in _PHYSICS.finditer(body):
                line = code[: offset + call.start()].count("\n") + 1
                findings.append(
                    Finding(WARNING, block.label, line, "physics changes belong in FixedUpdate, not Update")
                )
    return findings


# --- entry point --------------------------------------------------------------------------------

AUTO = "auto"


def validate_reply(text: str, validators: tuple[str, ...]) -> Report:
    """Check the code blocks in ``text`` with the category's validators.

    ``validators`` lists languages to check ("python", "csharp", "javascript"…), "unity"
    for Unity rules, or "auto" to check every language that has a checker.
    """
    report = Report()
    if not validators:
        return report
    for block in extract_blocks(text):
        language = block.language
        wanted = AUTO in validators or language in validators or (language == "tsx" and "typescript" in validators)
        if not wanted or not block.code.strip():
            continue
        if language == "python":
            report.findings += check_python(block)
        elif language in _GRAMMARS:
            report.findings += check_tree_sitter(block)
            if language == "csharp" and "unity" in validators:
                report.findings += check_unity(block)
        else:
            report.unchecked.append(block.label)
            continue
        report.checked.append(block.label)
    return report
