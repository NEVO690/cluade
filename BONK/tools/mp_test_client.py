"""Headless BONK! client process used by tools/mp_selftest.py.

    python tools/mp_test_client.py --addr 127.0.0.1:7777 --name Alice --role host --out alice.json
    python tools/mp_test_client.py --addr 127.0.0.1:7777 --name Bob --role guest --room r123 --out bob.json

It talks to the server only through the real protocol over TCP and records
what it observed (other players, movement, states, results) as JSON.
"""

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from bonk.multiplayer.client import NetworkClient  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--role", choices=("host", "guest"), required=True)
    ap.add_argument("--room", default=None)
    ap.add_argument("--room-file", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--quit-after", type=float, default=None, help="disconnect N s after the race starts")
    ap.add_argument("--timeout", type=float, default=120)
    a = ap.parse_args()

    obs = {"name": a.name, "role": a.role, "connected": False, "player_id": None, "room": None,
           "saw_players": [], "other_positions": [], "my_positions": [], "states": [], "results": None,
           "game_over": None, "player_left": [], "errors": [], "inputs_sent": 0, "disconnected_early": False,
           "first_countdown_at": None}
    cli = NetworkClient(a.name, "cool_shades" if a.role == "host" else "bubblegum")
    cli.connect(a.addr)
    t0 = time.time()
    race_started = None
    ready_sent = False
    started = False
    last_input = 0.0
    phase = "connect"

    def save():
        with open(a.out, "w") as fh:
            json.dump(obs, fh, indent=1)

    while time.time() - t0 < a.timeout:
        for msg in cli.poll():
            t = msg["t"]
            if t == "welcome":
                obs["connected"] = True
                obs["player_id"] = msg["id"]
            elif t == "room":
                obs["room"] = msg["room"]["id"]
                obs["members"] = [m["name"] for m in msg["room"]["members"]]
            elif t == "game_state":
                obs["states"].append(msg["state"])
                if msg["state"] == "COUNTDOWN" and obs["first_countdown_at"] is None:
                    obs["first_countdown_at"] = time.time()
                    obs["participants"] = [p["name"] for p in msg["participants"]]
                if msg["state"] == "ROUND_START":
                    race_started = time.time()
            elif t == "snap":
                ids = [c[0] for c in msg["chars"]]
                for cid in ids:
                    if cid != cli.player_id and cid not in obs["saw_players"]:
                        obs["saw_players"].append(cid)
                for c in msg["chars"]:
                    if c[0] == cli.player_id:
                        obs["my_positions"].append([round(time.time() - t0, 2), c[1], c[2], c[3], c[8]])
                    elif not c[0].startswith("bot"):
                        obs["other_positions"].append([round(time.time() - t0, 2), c[0], c[1], c[2], c[3]])
            elif t == "results":
                obs["results"] = msg["results"]
            elif t == "game_over":
                obs["game_over"] = msg
            elif t == "player_left":
                obs["player_left"].append(msg["name"])
            elif t == "error":
                obs["errors"].append(msg["msg"])
        if cli.status == "closed":
            obs["errors"].append("closed: %s" % cli.error)
            break
        if not cli.online:
            time.sleep(0.01)
            continue
        # ---- lobby choreography
        if phase == "connect":
            if a.role == "host":
                cli.create_room("Test Room", bots=2, max_players=8)
                phase = "wait_guest"
            else:
                room = a.room
                if a.room_file:
                    while not os.path.exists(a.room_file) or not open(a.room_file).read().strip():
                        time.sleep(0.05)
                    room = open(a.room_file).read().strip()
                cli.join_room(room)
                phase = "joined"
        elif phase == "wait_guest" and cli.room is not None:
            if a.room_file and not os.path.exists(a.room_file):
                with open(a.room_file, "w") as fh:
                    fh.write(cli.room["id"])
            others = [m for m in cli.room["members"] if m["id"] != cli.player_id]
            if others and all(m["ready"] for m in others) and not started:
                cli.start_game()
                started = True
                phase = "playing"
        elif phase == "joined" and cli.room is not None and not ready_sent:
            cli.set_ready(True)
            ready_sent = True
            phase = "playing"
        # ---- racing: run forward, hop regularly, weave a little
        if race_started and time.time() - last_input > 1 / 30.0:
            el = time.time() - race_started
            jump = (int(el * 10) % 7) == 0
            cli.send_input(0.25 * math.sin(el * 1.3), 1.0, jump, False)
            obs["inputs_sent"] += 1
            last_input = time.time()
            if a.quit_after is not None and el > a.quit_after:
                obs["disconnected_early"] = True
                cli.close()
                break
        if obs["game_over"] is not None:
            break
        time.sleep(0.005)
    save()
    print("CLIENT %s done: connected=%s saw=%d states=%s game_over=%s" % (
        a.name, obs["connected"], len(obs["saw_players"]), obs["states"][:3], obs["game_over"] is not None))


if __name__ == "__main__":
    main()
