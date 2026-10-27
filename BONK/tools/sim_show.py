"""Headless full show (all rounds) with bots, driven exactly like the client drives it.

    python tools/sim_show.py --players 16 --seed 2
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from bonk.ai import make_bot  # noqa: E402
from bonk.ai.bot_difficulty import mixed_lineup  # noqa: E402
from bonk.game.game_manager import GameManager, GameSettings, Participant  # noqa: E402
from bonk.game.game_state import GameState  # noqa: E402
from bonk.maps.map_manager import MapManager  # noqa: E402


def run_show(players=16, seed=1, frame_dt=1 / 30.0, log=print):
    mm = MapManager()
    rng = random.Random(seed)
    diffs = mixed_lineup(players, rng)
    parts = [Participant("p%d" % i, "Bot%02d" % i, is_bot=True, difficulty=diffs[i]) for i in range(players)]

    def factory(part, ch, rnd):
        return make_bot(part.difficulty, random.Random(rng.random()), rnd.world)

    gm = GameManager([mm.get(i) for i in mm.show_playlist()], parts, factory,
                     GameSettings(countdown=1.0, round_end=0.5, results_auto=0.1), seed=seed,
                     local_player_id="p0")
    states = []
    gm.add_listener(lambda k, d: states.append(d) if k == "state" else None)
    gm.start()
    sim_t = 0.0
    while gm.state != GameState.GAME_OVER and sim_t < 900:
        gm.update(frame_dt)
        sim_t += frame_dt
        if gm.state == GameState.RESULTS and gm.state_time == 0.0:
            pass
    return gm, states, sim_t


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=16)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    t0 = time.perf_counter()
    gm, states, sim_t = run_show(a.players, a.seed)
    print("final state:", gm.state, "after %.0fs game time (%.1fs wall)" % (sim_t, time.perf_counter() - t0))
    for map_id, results in gm.history:
        q = sum(1 for r in results if r.outcome != "eliminated")
        print("  round %-16s %2d players -> %2d advance (%s)" % (map_id, len(results), q,
              ", ".join(r.name for r in results if r.outcome != "eliminated")[:90]))
    champ = gm.champion_id
    print("champion:", champ and gm.participants[champ].name, gm.participants[champ].difficulty if champ else "")
    print("standings:", gm.final_standings[:5], "...", len(gm.final_standings), "placed")
    r = gm.local_report
    print("local report (p0):", r and dict(placement=r.placement, won=r.won, rounds=r.rounds_played, jumps=r.jumps))
    print("state sequence:", " > ".join(states[:9]), "...")
