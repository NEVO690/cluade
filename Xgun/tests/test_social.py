import pytest

from social.backend import SocialError
from social.friends import FriendError
from video.probe import panda_probe
from video.validation import UploadError, validate_video_file


@pytest.fixture
def social_services(tmp_path):
    from game.services import Services
    svc = Services(tmp_path / "social.db", probe=panda_probe, seed_demo=False)
    yield svc
    svc.close()


def _two_accounts(svc):
    a = svc.accounts.create("alice_x", "Alice")
    b = svc.accounts.create("bob_x", "Bob")
    return a, b


def test_upload_play_metadata_and_persist(social_services, make_video, tmp_path):
    svc = social_services
    a, b = _two_accounts(svc)
    clip = make_video("vertical.mp4", seconds=2, size="180x320")
    v = svc.social.upload(a.id, clip, "First drop #xgun", "Landing at #harborpoint")
    assert v.abs_path.exists() and v.abs_path != clip            # copied into storage
    assert v.height > v.width and 1.5 < v.duration < 2.5
    assert v.hashtags == ["xgun", "harborpoint"]
    assert svc.social.feed(b.id)[0].id == v.id

    assert svc.social.set_like(b.id, v.id, True) == 1
    assert svc.social.set_like(b.id, v.id, True) == 1          # idempotent
    svc.social.set_saved(b.id, v.id, True)
    c = svc.social.add_comment(b.id, v.id, "Nice landing!")
    assert svc.social.record_view(b.id, v.id) is True
    assert svc.social.record_view(b.id, v.id) is False         # throttled
    svc.social.set_follow(b.id, a.id, True)

    from game.services import Services
    svc.close()
    again = Services(tmp_path / "social.db", probe=panda_probe, seed_demo=False)
    v2 = again.social.get_video(b.id, v.id)
    assert (v2.likes, v2.comments, v2.saves, v2.views, v2.liked, v2.saved) == (1, 1, 1, 1, True, True)
    assert again.social.comments(b.id, v.id)[0].text == "Nice landing!"
    assert again.social.follower_count(a.id) == 1
    assert [x.id for x in again.social.saved_videos(b.id)] == [v.id]
    prof = again.social.profile(b.id, a.id)
    assert (prof.followers, prof.following, prof.total_likes, prof.video_count, prof.is_following) == (1, 0, 1, 1, True)
    assert again.social.set_like(b.id, v.id, False) == 0       # unlike
    again.social.set_follow(b.id, a.id, False)
    assert again.social.follower_count(a.id) == 0
    again.close()


def test_invalid_uploads_rejected(social_services, tmp_path, make_video):
    svc = social_services
    a, _ = _two_accounts(svc)
    bad_ext = tmp_path / "notes.txt"; bad_ext.write_text("hello" * 1000)
    renamed = tmp_path / "fake.mp4"; renamed.write_bytes(b"PNG not a video" * 400)
    empty = tmp_path / "empty.mp4"; empty.write_bytes(b"")
    good = make_video("good.mp4")
    truncated = tmp_path / "trunc.mp4"; truncated.write_bytes(good.read_bytes()[:3000])
    mismatch = tmp_path / "wrong.webm"; mismatch.write_bytes(good.read_bytes())
    for f in (bad_ext, renamed, empty, truncated, mismatch, tmp_path / "missing.mp4"):
        with pytest.raises(SocialError):
            svc.social.upload(a.id, f, "Bad upload")
    assert svc.social.profile_videos(a.id, a.id) == []
    with pytest.raises(SocialError):
        svc.social.upload(a.id, good, "")                      # empty title
    with pytest.raises(SocialError):
        svc.social.upload(a.id, good, "shit post")             # blocked language
    with pytest.raises(UploadError):
        validate_video_file(renamed)


def test_privacy_blocking_and_reports(social_services, make_video):
    svc = social_services
    a, b = _two_accounts(svc)
    c = svc.accounts.create("carol_x", "Carol")
    clip = make_video()
    public = svc.social.upload(a.id, clip, "Public")
    fol = svc.social.upload(a.id, clip, "Followers only", visibility="followers")
    priv = svc.social.upload(a.id, clip, "Just me", visibility="private")
    assert {v.id for v in svc.social.profile_videos(b.id, a.id)} == {public.id}
    svc.social.set_follow(b.id, a.id, True)
    assert {v.id for v in svc.social.profile_videos(b.id, a.id)} == {public.id, fol.id}
    assert len(svc.social.profile_videos(a.id, a.id)) == 3     # owner sees all
    with pytest.raises(SocialError):
        svc.social.get_video(b.id, priv.id)

    svc.social.set_block(a.id, b.id, True)
    assert svc.social.profile_videos(b.id, a.id) == []
    assert svc.social.follower_count(a.id) == 0
    svc.social.set_block(a.id, b.id, False)

    svc.social.update_video(a.id, public.id, allow_comments=False)
    with pytest.raises(SocialError):
        svc.social.add_comment(b.id, public.id, "hi")

    d = svc.accounts.create("dave_x", "Dave")
    for reporter in (b, c, d):
        svc.social.report(reporter.id, "video", public.id, "Spam")
    with pytest.raises(SocialError):
        svc.social.get_video(c.id, public.id)                   # auto-hidden after 3 reports
    assert svc.social.get_video(a.id, public.id).status == "hidden"


def test_comment_delete_and_search(social_services, make_video):
    svc = social_services
    a, b = _two_accounts(svc)
    v = svc.social.upload(a.id, make_video(), "Sniper montage #longshot", "Clean shots")
    cm = svc.social.add_comment(b.id, v.id, "how?")
    svc.social.delete_comment(a.id, cm.id)                       # video owner may remove
    assert svc.social.comments(b.id, v.id) == []
    res = svc.social.search(b.id, "#longshot")
    assert [x.id for x in res["videos"]] == [v.id] and "longshot" in res["hashtags"]
    assert a.id in svc.social.search(b.id, "alice")["accounts"]
    assert svc.social.trending_hashtags()[0] == ("longshot", 1)


def test_friends_flow(services):
    a = services.accounts.create("ann_f")
    b = services.accounts.create("ben_f")
    req = services.friends.send_request(a.id, b.id)
    with pytest.raises(FriendError):
        services.friends.send_request(a.id, b.id)
    assert [r.id for r in services.friends.incoming(b.id)] == [req.id]
    services.friends.accept(req.id, b.id)
    assert services.friends.are_friends(a.id, b.id) and services.friends.are_friends(b.id, a.id)
    services.friends.remove(a.id, b.id)
    assert not services.friends.are_friends(b.id, a.id)
    # mutual request auto-accepts
    services.friends.send_request(a.id, b.id)
    assert services.friends.send_request(b.id, a.id) is None
    assert services.friends.are_friends(a.id, b.id)


def test_tiktok_follower_count_matches_profile(services):
    a = services.accounts.create("star_x")
    for i in range(3):
        f = services.accounts.create(f"fan_{i}")
        services.social.set_follow(f.id, a.id, True)
    assert services.social.follower_count(a.id) == 3
    assert services.social.profile(a.id, a.id).followers == 3
