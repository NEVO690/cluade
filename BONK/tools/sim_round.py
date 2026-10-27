"""Headless playtest: run one course with bots and print what happened.

    python tools/sim_round.py starter_run --bots 16 --difficulty NORMAL --seed 3
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from bonk.ai import make_bot  # noqa: E402
from bonk.game.round_manager import RoundSimulation  # noqa: E402
from bonk.maps.map_manager import MapManager  # noqa: E402
from bonk.sim import constants as C  # noqa: E402
from bonk.sim.character import Character  # noqa: E402


def run(map_id, bots=16, difficulty="NORMAL", seed=1, quota=None, final=False, verbose=False,
        max_time=None):
    mm = MapManager()
    m = mm.get(map_id)
    rng = random.Random(seed)
    diffs = difficulty.split(",")
    chars = [Character("b%d" % i, "Bot%02d" % i, is_bot=True) for i in range(bots)]
    rnd = RoundSimulation(m, chars, {}, quota or bots, final, seed=seed)
    for i, ch in enumerate(chars):
        d = diffs[i % len(diffs)]
        ch.difficulty = d
        rnd.controllers[ch.id] = make_bot(d, random.Random(rng.random()), rnd.world)
    rnd.start_race()
    t0 = time.perf_counter()
    limit = max_time or (m.time_limit + 5)
    last_report = 0.0
    while not rnd.over and rnd.race_time < limit:
        rnd.tick(C.DT)
        if verbose and rnd.race_time - last_report >= 10.0:
            last_report = rnd.race_time
            alive = [c for c in chars if c.alive]
            print("  t=%5.1f finished=%d alive=%d  progress: %s" % (
                rnd.race_time, len(rnd.finish_order), len(alive),
                " ".join("%.0f" % c.progress for c in sorted(alive, key=lambda c: -c.progress))))
    wall = time.perf_counter() - t0
    return rnd, wall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map_id")
    ap.add_argument("--bots", type=int, default=16)
    ap.add_argument("--difficulty", default="NORMAL")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--quota", type=int, default=None)
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    rnd, wall = run(a.map_id, a.bots, a.difficulty, a.seed, a.quota, verbose=a.v)
    print("map=%s end=%s race_time=%.1fs sim_wall=%.2fs (%.1fx realtime)" % (
        a.map_id, rnd.end_reason, rnd.race_time, wall, rnd.race_time / max(wall, 1e-6)))
    for c in sorted(rnd.characters, key=lambda c: (c.finish_place or 99, -c.best_progress)):
        print("  %-6s %-8s %s place=%-3s time=%-6s prog=%5.1f/%5.1f falls=%d hits=%d jumps=%d obst=%d %s" % (
            c.id, getattr(c, "difficulty", ""), "FIN " if c.finished else ("ELIM" if c.eliminated else "    "),
            c.finish_place, c.finish_time, c.best_progress, rnd.world.route.length, c.stat_falls,
            c.stat_hits, c.stat_jumps, c.stat_obstacles,
            "" if c.finished else "at (%.1f,%.1f,%.1f) %s" % (c.x, c.y, c.z, rnd.controllers.get(c.id).debug if rnd.controllers.get(c.id) else "")))


if __name__ == "__main__":
    main()
