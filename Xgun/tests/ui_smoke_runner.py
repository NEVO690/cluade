"""Boots the real game offscreen (software renderer), clicks through every lobby tab,
plays part of a match, leaves it and checks rewards were saved. Run by test_ui_smoke."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XGUN_NO_AUDIO"] = "1"

from panda3d.core import loadPrcFileData  # noqa: E402

loadPrcFileData("smoke", "load-display p3tinydisplay\naux-display p3tinydisplay")

from config.settings import Settings  # noqa: E402
from game.app import XgunApp  # noqa: E402


def main():
    s = Settings()
    s.window_width, s.window_height, s.bot_count, s.vsync = 1024, 600, 5, False
    app = XgunApp(s, offscreen=True)

    def steps(n):
        for _ in range(n):
            app.taskMgr.step()

    steps(5)
    lobby = app.screen
    for tab in ["LOCKER", "XON SHOP", "BATTLE PASS", "TIKTOK", "FRIENDS", "PROFILE", "QUESTS", "SETTINGS", "PLAY"]:
        lobby.select(tab)
        steps(3)
        assert lobby.tab_obj is not None, tab
    lobby.select("TIKTOK")
    steps(3)
    tt = lobby.tab_obj
    assert tt.videos, "feed should contain the bundled sample clips"
    assert tt.player.tex is not None or tt.player.error is not None
    tt.next()
    tt._toggle_like()
    steps(2)
    assert tt.current.liked
    before = app.services.wallet.balance(app.account.id)
    app.start_match()
    for _ in range(300):
        steps(1)
        if app.screen.__class__.__name__ == "MatchScreen":
            break
    m = app.screen
    assert m.__class__.__name__ == "MatchScreen"
    m._press("space")
    steps(120)
    assert m.sim.time > 1.0
    assert m.player.state in ("bus", "skydive", "glide", "ground")
    m._exit()                       # leave the match -> rewards -> lobby with results
    steps(5)
    stats = app.services.progression.stats(app.account.id)
    after = app.services.wallet.balance(app.account.id)
    assert stats["matches"] == 1, stats
    assert after > before, (before, after)
    assert app.screen.__class__.__name__ == "LobbyScreen"
    print("SMOKE OK", stats["matches"], before, after)


if __name__ == "__main__":
    main()
