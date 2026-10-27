"""Bot benchmark: finish rate and time per difficulty on every course.

    python tools/ai_benchmark.py --seeds 3 --bots 16
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim_round import run  # noqa: E402

from bonk.maps.map_manager import MapManager  # noqa: E402

DIFFS = ("EASY", "NORMAL", "HARD", "CHAOTIC")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--bots", type=int, default=16)
    ap.add_argument("--maps", default=None, help="comma separated map ids")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    maps = a.maps.split(",") if a.maps else MapManager().ids()
    for map_id in maps:
        fin = collections.Counter()
        tot = collections.Counter()
        times = collections.defaultdict(list)
        falls = collections.Counter()
        hits = collections.Counter()
        stuck = []
        wall_total = race_total = 0.0
        for seed in range(1, a.seeds + 1):
            rnd, wall = run(map_id, a.bots, ",".join(DIFFS), seed, quota=a.bots)
            wall_total += wall
            race_total += rnd.race_time
            for c in rnd.characters:
                d = c.difficulty
                tot[d] += 1
                falls[d] += c.stat_falls
                hits[d] += c.stat_hits
                if c.finished:
                    fin[d] += 1
                    times[d].append(c.finish_time)
                elif not c.eliminated or c.elim_reason == "timeout":
                    stuck.append("%s@(%.0f,%.0f,%.1f)" % (d[0], c.x, c.y, c.z))
        print("%-16s sim speed %.0fx realtime" % (map_id, race_total / max(wall_total, 1e-6)))
        for d in DIFFS:
            ts = sorted(times[d])
            med = ts[len(ts) // 2] if ts else None
            print("   %-8s finished %3d/%-3d  median time %-6s  falls/bot %.1f  hits/bot %.1f" % (
                d, fin[d], tot[d], "%.1f" % med if med else "-", falls[d] / max(1, tot[d]),
                hits[d] / max(1, tot[d])))
        if a.verbose and stuck:
            print("   timed out at:", " ".join(stuck[:20]))


if __name__ == "__main__":
    main()
