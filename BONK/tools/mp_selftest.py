"""Multiplayer end-to-end check with three separate processes (server + two clients).

    python tools/mp_selftest.py

Checks:
  1. first client connects          5. both receive the same game start
  2. second client connects         6. the round ends with server results
  3. each client sees the other     7. a client disconnecting mid-round is handled
  4. movement updates arrive           (the other client is told and the game finishes)
"""

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def start_server(tmp, time_limit):
    proc = subprocess.Popen([PY, os.path.join(HERE, "..", "run_server.py"), "--host", "127.0.0.1", "--port", "0",
                             "--maps", "starter_run", "--time-limit", str(time_limit), "--data-dir",
                             os.path.join(tmp, "server_data")],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.time() + 20
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line.startswith("READY"):
            return proc, int(line.split()[1])
    proc.kill()
    raise RuntimeError("server did not start")


def run_pair(tmp, tag, quit_after=None, time_limit=20):
    server, port = start_server(tmp, time_limit)
    addr = "127.0.0.1:%d" % port
    room_file = os.path.join(tmp, tag + "_room.txt")
    outs = {n: os.path.join(tmp, "%s_%s.json" % (tag, n)) for n in ("alice", "bob")}
    host = subprocess.Popen([PY, os.path.join(HERE, "mp_test_client.py"), "--addr", addr, "--name", "Alice",
                             "--role", "host", "--room-file", room_file, "--out", outs["alice"]])
    time.sleep(0.4)  # guarantee the order: first client, then second client
    args = [PY, os.path.join(HERE, "mp_test_client.py"), "--addr", addr, "--name", "Bob", "--role", "guest",
            "--room-file", room_file, "--out", outs["bob"]]
    if quit_after is not None:
        args += ["--quit-after", str(quit_after)]
    guest = subprocess.Popen(args)
    host.wait(timeout=180)
    guest.wait(timeout=180)
    server_alive = server.poll() is None
    server.terminate()
    log = server.communicate(timeout=10)[0]
    with open(outs["alice"]) as fh:
        a = json.load(fh)
    with open(outs["bob"]) as fh:
        b = json.load(fh)
    return a, b, server_alive, log


def moved(positions):
    if len(positions) < 2:
        return 0.0
    ys = [p[3] if len(p) == 5 and isinstance(p[1], str) else p[2] for p in positions]
    return max(ys) - min(ys)


def main():
    tmp = tempfile.mkdtemp(prefix="bonk_mp_")
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok))
        print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail))

    a, b, alive, log = run_pair(tmp, "normal")
    check("1. first client connected", a["connected"] and a["player_id"] is not None, a["player_id"])
    check("2. second client connected", b["connected"] and b["player_id"] is not None, b["player_id"])
    check("3. each client sees the other",
          b["player_id"] in a["saw_players"] and a["player_id"] in b["saw_players"],
          "alice saw %s, bob saw %s" % (a["saw_players"], b["saw_players"]))
    check("4. movement updates for the other player",
          moved(a["other_positions"]) > 3.0 and moved(b["other_positions"]) > 3.0,
          "alice saw bob move %.1f m, bob saw alice move %.1f m" % (moved(a["other_positions"]),
                                                                    moved(b["other_positions"])))
    same_start = (a["states"][:3] == ["COUNTDOWN", "ROUND_START", "ROUND_ACTIVE"] == b["states"][:3]
                  and abs(a["first_countdown_at"] - b["first_countdown_at"]) < 0.5)
    check("5. shared game start", same_start, "countdown delta %.3fs, participants %s" % (
        abs(a["first_countdown_at"] - b["first_countdown_at"]), a.get("participants")))
    ok6 = (a["results"] is not None and b["results"] is not None and a["game_over"] is not None
           and b["game_over"] is not None and a["game_over"]["standings"] == b["game_over"]["standings"]
           and a["game_over"]["reports"][a["player_id"]]["verified_by_server"])
    check("6. round end + identical server results", ok6,
          "champion %s" % (a["game_over"] or {}).get("champion"))

    a2, b2, alive2, log2 = run_pair(tmp, "drop", quit_after=3.0)
    ok7 = (b2["disconnected_early"] and "Bob" in a2["player_left"] and a2["game_over"] is not None and alive2
           and any(s["name"] == "Bob" for s in a2["game_over"]["standings"]))
    check("7. disconnect handled", ok7, "alice got player_left=%s, game finished=%s, server alive=%s" % (
        a2["player_left"], a2["game_over"] is not None, alive2))
    print("\nserver log excerpt:\n" + "\n".join(log.splitlines()[:6]))
    print("\n%d/%d checks passed" % (sum(ok for _, ok in checks), len(checks)))
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
