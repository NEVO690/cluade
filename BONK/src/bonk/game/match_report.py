"""What the local player did in a show.  Progression turns this into rewards."""

from dataclasses import asdict, dataclass, field


@dataclass
class MatchReport:
    mode: str = "ai_showdown"  # ai_showdown / quick_play / online
    player_count: int = 1
    rounds: list = field(default_factory=list)  # [{map_id, outcome, time, place, reason}]
    won: bool = False
    placement: int = None
    quit_early: bool = False
    jumps: int = 0
    obstacles_cleared: int = 0
    falls: int = 0
    hits: int = 0
    bonks: int = 0
    difficulty: str = None
    verified_by_server: bool = False  # only true for results confirmed by a game server

    @property
    def rounds_played(self):
        return len(self.rounds)

    @property
    def rounds_qualified(self):
        return sum(1 for r in self.rounds if r["outcome"] in ("qualified", "winner"))

    @property
    def finishes(self):
        return sum(1 for r in self.rounds if r.get("time") is not None)

    def best_times(self):
        out = {}
        for r in self.rounds:
            if r.get("time") is not None:
                prev = out.get(r["map_id"])
                out[r["map_id"]] = r["time"] if prev is None else min(prev, r["time"])
        return out

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)
