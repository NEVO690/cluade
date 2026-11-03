"""Made With AVEN: sandbox, checks, pipeline, projects and the locked-down page."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest

from app.storage.database import Database
from app.studio.page import build_page
from app.studio.pipeline import GamePipeline, PipelineError, extract_code, parse_plan
from app.studio.projects import ProjectStore
from app.studio.sandbox import smoke_test
from app.studio.validate import validate_game

GOOD = (Path(__file__).parent / "data" / "sample_game.js").read_text(encoding="utf-8")
FENCE = "`" * 3
PLAN = {"title": "Coin Run", "genre": "arcade", "summary": "Collect coins.", "controls": ["Arrows: move"],
        "systems": [{"name": "Movement", "description": "arrows"}], "entities": [{"name": "Player"}],
        "scenes": ["title", "play"], "goal": "score", "scope_notes": ""}  # fmt: skip


def js(code: str) -> str:
    return f"{FENCE}javascript\n{code}\n{FENCE}\nEnjoy!"


# --- sandbox and checks ---------------------------------------------------------------------


def test_a_working_game_passes_every_check() -> None:
    report = validate_game(GOOD)
    assert report.ok, report.errors
    assert len(report.checks) == 3 and "Sandbox test" in report.checks[2]


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("", "No game code"),
        ("const g = AVEN.createGame({}); function broken( {", "syntax error"),
        (GOOD + '\nfetch("https://example.com");', "network access"),
        (GOOD + '\neval("1+1");', "eval"),
        (GOOD + '\nimport("./x.js");', "imports"),
        ('const g = 1; g.start("x");', "AVEN.createGame"),
        ("const game = AVEN.createGame({});", "game.start"),
        (GOOD.replace("g.state.p.x, g.state.p.y", "g.state.player.x, g.state.p.y"), "crashed while running"),
        ("const game = AVEN.createGame({}); while (true) {} game.start('a');", "too long"),
        ("const game = AVEN.createGame({}); game.scene('a', {}); game.start('a');", "drew nothing"),
        ("const game = AVEN.createGame({}); game.start('missing');", "No scene named"),
    ],
)
def test_broken_or_unsafe_games_are_rejected(code: str, message: str) -> None:
    report = validate_game(code)
    assert not report.ok
    assert any(message in error for error in report.errors), report.errors


def test_sandbox_has_no_network_or_files() -> None:
    names = ["fetch", "XMLHttpRequest", "WebSocket", "require", "process", "std", "os", "Deno"]
    exposed = " || ".join(f"typeof {n} !== 'undefined'" for n in names)
    probe = (
        f"if ({exposed}) throw new Error('a system API is reachable');"
        "const game = AVEN.createGame({}); game.scene('a', { draw(g) { g.clear(); } }); game.start('a');"
    )
    result = smoke_test(probe)
    assert result.ok, result.errors


# --- pipeline -----------------------------------------------------------------------------------


def scripted(*replies: str):
    queue = list(replies)
    calls: list[tuple[str, str, int]] = []

    def complete(system, user, max_tokens, on_text):
        calls.append((system, user, max_tokens))
        return queue.pop(0)

    return complete, calls


def test_plan_is_parsed_from_json_with_fences_and_normalized() -> None:
    plan = parse_plan("Sure!\n" + FENCE + "json\n" + json.dumps(PLAN) + "\n" + FENCE)
    assert plan["title"] == "Coin Run" and plan["entities"] == [{"name": "Player", "description": ""}]
    with pytest.raises(PipelineError):
        parse_plan("no json here")


def test_pipeline_repairs_a_crashing_game_until_it_passes() -> None:
    crashing = GOOD.replace("g.state.p.x, g.state.p.y", "g.state.player.x, g.state.p.y")
    complete, calls = scripted(json.dumps(PLAN), js(crashing), js(GOOD))
    progress: list[str] = []
    pipeline = GamePipeline(complete, progress.append)
    result = pipeline.build(pipeline.plan("a coin game"))
    assert result.validated and len(result.attempts) == 2
    assert "crashed" in result.attempts[0].report.errors[0]
    assert "Problems found by AVEN's checks" in calls[2][1] and "player" in calls[2][1]
    assert progress[-1] == "All checks passed."


def test_pipeline_never_calls_a_failing_game_validated() -> None:
    crashing = GOOD.replace("g.state.p.x, g.state.p.y", "g.state.player.x, g.state.p.y")
    complete, _calls = scripted(js(crashing), js(crashing), js(crashing), js(crashing))
    result = GamePipeline(complete, max_repairs=3).build(PLAN)
    assert not result.validated and len(result.attempts) == 4  # first try + 3 repairs
    assert result.report.errors


def test_plan_retries_once_when_the_reply_is_not_json() -> None:
    complete, calls = scripted("I think it will be fun!", json.dumps(PLAN))
    assert GamePipeline(complete).plan("x")["title"] == "Coin Run"
    assert "ONLY the JSON object" in calls[1][1]


def test_change_requests_send_the_current_code_and_plan() -> None:
    complete, calls = scripted(js(GOOD.replace("#7b6cff", "#ff0000")))
    result = GamePipeline(complete).change(PLAN, GOOD, "make the player red")
    assert result.validated and "#ff0000" in result.code
    assert "make the player red" in calls[0][1] and "Coin Run" in calls[0][1] and "AVEN.createGame" in calls[0][1]


def test_extract_code_takes_the_largest_javascript_block() -> None:
    reply = f"{FENCE}js\nsmall()\n{FENCE}\n{FENCE}javascript\n{GOOD}\n{FENCE}"
    assert extract_code(reply).strip() == GOOD.strip()
    assert extract_code("no code at all") == ""


# --- the playable page ---------------------------------------------------------------------------


def test_page_allows_only_its_own_scripts_and_no_network() -> None:
    page = build_page("Coin <Run>", GOOD)
    policy = re.search(r'Content-Security-Policy" content="([^"]+)"', page).group(1)
    assert "default-src 'none'" in policy and "connect-src 'none'" in policy
    assert "unsafe-inline" not in policy.split("style-src")[0]  # scripts are allowed only by hash
    scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert len(scripts) == 2
    for script in scripts:  # every inline script is allowed by its exact hash
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        assert f"'sha256-{digest}'" in policy
    assert "<title>Coin &lt;Run&gt;</title>" in page


def test_script_end_tags_in_game_code_cannot_break_out_of_the_page() -> None:
    page = build_page("x", GOOD + '\nconst s = "</script><img src=x onerror=alert(1)>";')
    assert page.count("</script>") == 2


# --- projects --------------------------------------------------------------------------------------


def test_projects_save_versions_and_export(tmp_path) -> None:
    store = ProjectStore(Database(":memory:"), root=tmp_path / "projects")
    project = store.create("A coin game\nwith slimes", "aven-2")
    assert project.title == "A coin game" and project.status == "draft"
    store.save_plan(project, PLAN)
    store.save_version(project, GOOD, True, "build", "A coin game", [], ["ok"], "aven-2")
    store.save_version(project, GOOD + "\n// v2", False, "change", "make it faster", ["crash"], [], "aven-2")
    again = store.get(project.id)
    assert again.title == "Coin Run" and again.version == 2 and again.status == "needs_fixes"
    assert (again.path / "versions" / "v1" / "game.js").read_text() == GOOD
    assert again.code().endswith("// v2") and again.page_path.exists()
    assert [h["kind"] for h in again.history] == ["plan", "build", "change"]
    archive = store.export(again, tmp_path / "game.zip")
    with zipfile.ZipFile(archive) as z:
        assert sorted(z.namelist()) == ["README.txt", "aven_game.js", "game.js", "index.html"]
        assert "NOT validated" in z.read("README.txt").decode()
    store.delete(again)
    assert store.list() == [] and not again.path.exists()


def test_empty_description_is_refused(tmp_path) -> None:
    store = ProjectStore(Database(":memory:"), root=tmp_path)
    with pytest.raises(ValueError):
        store.create("   ", "aven-2")
