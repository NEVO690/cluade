import os
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from bonk.game.match_report import MatchReport  # noqa: E402
from bonk.progression.profile import PlayerProfile  # noqa: E402
from bonk.save.save_manager import SaveManager  # noqa: E402


class FakeClock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def temp_profile(clock=None):
    d = tempfile.mkdtemp(prefix="bonk_test_")
    sm = SaveManager(d)
    sm.load()
    return PlayerProfile(sm, clock=clock or FakeClock()), d


def report(**kw):
    base = dict(mode="ai_showdown", player_count=16, rounds=[], won=False, placement=10,
                difficulty="NORMAL")
    base.update(kw)
    return MatchReport(**base)


def win_report():
    rounds = [{"map_id": "starter_run", "outcome": "qualified", "time": 23.0, "place": 1, "reason": "finished"},
              {"map_id": "hammer_havoc", "outcome": "qualified", "time": 40.0, "place": 2, "reason": "finished"},
              {"map_id": "vanishing_tiles", "outcome": "winner", "time": 19.0, "place": 1, "reason": "finished"}]
    return report(rounds=rounds, won=True, placement=1, jumps=30, obstacles_cleared=15, bonks=1)
