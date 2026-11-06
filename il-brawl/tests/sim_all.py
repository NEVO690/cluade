"""Headless simulation: every mode x map with bots only, all characters cycled."""
import sys, time, random, itertools, collections
sys.path.insert(0, '.')
from ilbrawl.data_loader import GameData
from ilbrawl.gameplay.world import World

gd = GameData.load()
chars = gd.char_order
random.seed(1)
summary = collections.Counter()
t0 = time.time()
ci = itertools.cycle(chars)
for mode in gd.mode_order:
    for m in gd.maps_for_mode(mode):
        for diff in ("easy", "expert"):
            cfg = gd.modes[mode]
            parts = []
            if mode == "solo_survival":
                for i in range(6):
                    parts.append({"char": next(ci), "team": i, "name": "B%d" % i, "level": random.randint(1, 9)})
            else:
                for i in range(6):
                    parts.append({"char": next(ci), "team": i // 3, "name": "B%d" % i, "level": random.randint(1, 9)})
            w = World(gd, m, mode, parts, diff, seed=42)
            steps = 0
            while w.state != "over" and steps < 60 * 400:
                w.update(1 / 60)
                w.pop_events()
                steps += 1
            res = w.build_result() if w.state == "over" else None
            stats = [(b.char_id, b.stats.kills, int(b.stats.damage), b.stats.supers) for b in w.brawlers]
            outcome = w.result.get("winner") if w.result else "TIMEOUT"
            print("%-15s %-15s %-6s t=%5.1fs winner=%s score=%s kills=%d supers=%d" % (
                mode, m["id"], diff, w.time, outcome, w.mode.final_score_text(),
                sum(s[1] for s in stats), sum(s[3] for s in stats)))
            summary[(mode, outcome == "TIMEOUT")] += 1
print("elapsed %.1fs" % (time.time() - t0))
print(summary)
