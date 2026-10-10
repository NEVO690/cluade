"""Bundled sample clips are valid, decodable, vertical and seed the social feed."""
import json

from config import paths
from video.probe import panda_probe
from video.validation import validate_video_file


def test_sample_clips_decode_and_are_vertical():
    index = json.loads((paths.SAMPLE_VIDEOS / "samples.json").read_text())
    assert len(index) >= 5
    for entry in index:
        info = validate_video_file(paths.SAMPLE_VIDEOS / entry["file"], panda_probe)
        assert info.is_vertical and 3 <= info.duration <= 10


def test_demo_seed_creates_labelled_demo_creators(tmp_path):
    from game.services import Services
    svc = Services(tmp_path / "seed.db", probe=panda_probe, seed_demo=True)
    me = svc.ensure_player("Viewer")
    demo = [a for a in svc.accounts.list() if a.is_demo]
    assert len(demo) == 4 and all(a.is_demo for a in demo)
    feed = svc.social.feed(me.id)
    assert len(feed) >= 5 and all(v.is_sample for v in feed)
    assert svc.wallet.balance(demo[0].id) == 0          # demo accounts get no XON
    Services(tmp_path / "seed.db", probe=panda_probe, seed_demo=True).close()   # idempotent reseed
    again = Services(tmp_path / "seed.db", probe=panda_probe, seed_demo=True)
    assert len([v for v in again.social.feed(me.id, limit=100)]) == len(feed)
    again.close()
    svc.close()
