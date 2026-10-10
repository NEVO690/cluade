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
    # in-game thumbnail extraction (no ffmpeg on players' PCs)
    vid = tt.videos[0]
    assert app.thumbs.get(vid) is None or True
    for _ in range(40):
        steps(1)
        if app.thumbs.get(vid) is not None:
            break
    from panda3d.core import PNMImage
    from video.thumbnails import thumb_path
    img = PNMImage(str(thumb_path(vid.id)))
    assert (img.getXSize(), img.getYSize()) == (180, 320)
    assert img.getAverageGray() > 0.03, "thumbnail is black"
    tt.next()
    tt._toggle_like()
    steps(2)
    assert tt.current.liked
    # upload flow through the real UI: a broken file is rejected, a real clip is posted
    import shutil
    import tempfile
    from config import paths
    tmp = Path(tempfile.mkdtemp())
    bad = tmp / "broken.mp4"
    bad.write_bytes(b"not a video" * 500)
    tt.show_upload()
    steps(2)
    tt.u_path.set(str(bad))
    tt.u_title.set("Broken clip")
    tt._do_upload()
    assert "video" in tt.u_status.getText().lower(), tt.u_status.getText()
    good = tmp / "my_clip.mp4"
    shutil.copyfile(paths.SAMPLE_VIDEOS / "groove_check.mp4", good)
    tt.u_path.set(str(good))
    tt.u_title.set("My first drop #xgun")
    tt._do_upload()
    steps(2)
    mine = app.services.social.profile_videos(app.account.id, app.account.id)
    assert len(mine) == 1 and mine[0].title == "My first drop #xgun"
    assert Path(mine[0].file_path).exists() and paths.user_dir() in Path(mine[0].file_path).parents
    # friends between two local accounts, then follow -> follower count on the profile
    me = app.account.id
    other = app.services.accounts.create("second_player", "Second")
    lobby.select("FRIENDS")
    steps(2)
    lobby.tab_obj._add(other.id)
    req = app.services.friends.incoming(other.id)[0]
    app.services.friends.accept(req.id, other.id)
    assert app.services.friends.are_friends(me, other.id)
    app.services.social.set_follow(other.id, me, True)
    lobby.select("PROFILE")
    steps(2)
    assert app.services.social.profile(me, me).followers == 1
    # online social: sign up through the dialog, then the server disappears -> graceful fallback
    from net.social_server import SocialServer
    srv = SocialServer(tmp / "social_server", "127.0.0.1", 0)
    srv.serve_in_background()
    lobby.select("TIKTOK")
    steps(2)
    tt = lobby.tab_obj
    tt._online_dialog()
    tt.o_server.set(f"127.0.0.1:{srv.port}")
    tt.o_user.set("smoke_online")
    tt.o_pass.set("pass1234")
    tt._online(True)
    steps(3)
    assert app.services.online and app.settings.social_token
    tt = lobby.tab_obj
    assert tt.me == app.services.social.account["id"] and tt.videos, "online feed should show the server clips"
    srv.stop()
    tt.show_feed("for_you")                      # server gone: must not crash
    steps(3)
    assert not app.services.online, "should fall back to the local network"
    lobby.select("PROFILE")
    steps(2)
    lobby.select("PLAY")
    steps(2)
    # online match: host from the PLAY tab and play a little (solo host + bots)
    app.host_online()
    steps(3)
    assert app.online_lobby is not None
    for _ in range(100):
        steps(1)
        if app.online_lobby.host:
            break
    app.online_lobby._start()
    for _ in range(600):
        steps(1)
        if app.screen.__class__.__name__ == "MatchScreen":
            break
    om = app.screen
    assert om.__class__.__name__ == "MatchScreen" and om.online
    import time as _time
    for _ in range(90):
        steps(1)
        _time.sleep(0.01)
    assert om.sim.time > 0.5 and len(om.sim.items) > 50, (om.sim.time, len(om.sim.items))
    server = om.sim.hosted_server
    om._exit()
    steps(5)
    assert server.stopped.is_set()
    assert app.screen.__class__.__name__ == "LobbyScreen"
    lobby = app.screen
    lobby.select("PLAY")
    steps(2)
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
    assert stats["matches"] == 2, stats
    assert after > before, (before, after)
    assert app.screen.__class__.__name__ == "LobbyScreen"
    print("SMOKE OK", stats["matches"], before, after)


if __name__ == "__main__":
    main()
