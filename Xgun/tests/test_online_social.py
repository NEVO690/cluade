"""Shared social server + RemoteSocialBackend over real HTTP on localhost."""
import json
import urllib.request

import pytest

from net import social_client as SC
from net.social_server import SocialServer
from social.errors import SocialError


@pytest.fixture()
def server(tmp_path):
    srv = SocialServer(tmp_path / "server", "127.0.0.1", 0)
    srv.serve_in_background()
    yield f"127.0.0.1:{srv.port}", srv
    srv.stop()


def test_accounts_and_auth(server):
    url, _ = server
    alice = SC.register(url, "alice_x", "secret12", "Alice")
    assert alice.account["username"] == "alice_x"
    with pytest.raises(SocialError, match="already taken on this server"):
        SC.register(url, "alice_x", "another1")
    with pytest.raises(SocialError, match="at least 6"):
        SC.register(url, "bob_x", "123")
    with pytest.raises(SocialError, match="Wrong username or password"):
        SC.login(url, "alice_x", "wrong-pass")
    with pytest.raises(SocialError, match="Wrong username or password"):
        SC.login(url, "nobody_here", "whatever")
    again = SC.login(url, "alice_x", "secret12")
    assert again.self_id(999) == alice.account["id"]
    resumed = SC.resume(url, alice.token)
    assert resumed.account["id"] == alice.account["id"]
    with pytest.raises(SocialError, match="sign in"):
        SC.resume(url, "forged-token")


def test_password_is_not_stored_in_plain_text(server):
    url, srv = server
    SC.register(url, "carol_x", "hunter22")
    rows = srv.service.db.all("SELECT * FROM server_auth")
    assert rows and all("hunter22" not in str(dict(r)) for r in rows)


def test_two_players_see_each_others_activity(server, tmp_path, make_video, monkeypatch):
    url, _ = server
    monkeypatch.setenv("XGUN_USER_DIR", str(tmp_path / "client_a"))
    a = SC.register(url, "creator_a", "pass1234", "Creator A")
    monkeypatch.setenv("XGUN_USER_DIR", str(tmp_path / "client_b"))
    b = SC.register(url, "viewer_b", "pass1234", "Viewer B")

    # demo content is on the server, so the shared feed isn't empty
    assert len(b.feed(0)) >= 6
    assert b.trending_hashtags(5)

    clip = make_video(tmp_path / "mine.mp4")
    v = a.upload(0, clip, "Online clutch #xgun", "first online upload")
    assert v.owner_id == a.account["id"] and v.abs_path.exists()

    # B (a different PC/cache) finds it, downloads it and interacts
    found = b.search(0, "clutch")
    assert [x.id for x in found["videos"]] == [v.id]
    seen = found["videos"][0]
    assert seen.abs_path.exists() and seen.abs_path.read_bytes() == clip.read_bytes()
    assert str(tmp_path / "client_b") in str(seen.abs_path)
    assert b.set_like(0, v.id, True) == 1
    b.add_comment(0, v.id, "nice one")
    b.set_follow(0, a.account["id"], True)
    b.record_view(0, v.id)

    # A sees B's like, comment and follow
    mine = a.get_video(0, v.id)
    assert (mine.likes, mine.comments) == (1, 1)
    assert [c.text for c in a.comments(0, v.id)] == ["nice one"]
    prof = a.profile(0, a.account["id"])
    assert prof.followers == 1 and a.follower_count(a.account["id"]) == 1
    assert b.account["id"] in a.followers(a.account["id"])

    # privacy is enforced by the server: private videos are invisible to others, even by direct id
    a.update_video(0, v.id, visibility="private")
    with pytest.raises(SocialError):
        b.get_video(0, v.id)
    with pytest.raises(SocialError):
        SC._request(b.opener, b.base, f"/api/video/{v.id}", token=b.token, raw=True)
    # B can't touch A's video
    with pytest.raises(SocialError):
        b.delete_video(0, v.id)
    a.delete_video(0, v.id)

    # profile editing goes to the server
    a.update_profile(0, display_name="Creator Prime", bio="hi", private_account=False, allow_comments=True)
    assert b.profile(0, a.account["id"]).display_name == "Creator Prime"


def test_server_rejects_bad_requests(server, tmp_path):
    url, _ = server
    a = SC.register(url, "dave_x", "pass1234")
    with pytest.raises(SocialError, match="Unknown request"):
        a._call("__init__")
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video at all" * 20000)
    with pytest.raises(SocialError, match="doesn't look like a video"):
        a.upload(0, bad, "fake")
    # no token -> 401
    req = urllib.request.Request(f"http://{url}/api/call", data=json.dumps({"method": "feed"}).encode(),
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with pytest.raises(urllib.error.HTTPError) as exc:
        opener.open(req, timeout=5)
    assert exc.value.code == 401


def test_unreachable_server_is_a_clean_error():
    with pytest.raises(SocialError, match="Couldn't reach"):
        SC.login("127.0.0.1:1", "x", "y")
