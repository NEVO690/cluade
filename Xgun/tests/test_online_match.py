"""Online match: real TCP server + clients on localhost, no rendering."""
import time

import pytest

from game.entities import ControlInput
from game.match import TICK
from net import protocol as P
from net.match_client import ClientMatch, ConnectionFailed, MatchConnection
from net.match_server import MatchServer
from world.island import build_island


@pytest.fixture(scope="module")
def island_factory():
    return lambda: build_island(7)


def _server(factory, **kw):
    srv = MatchServer("127.0.0.1", 0, layout=factory(), seed=1234, **kw)
    srv.serve_in_background()
    return srv


def _tick(clients, inputs_for, n):
    for _ in range(n):
        for cm in clients:
            inp = inputs_for(cm)
            cm.step(TICK, {cm.player.id: inp} if inp else {})
            cm.drain_events()
        time.sleep(TICK)


def test_protocol_input_roundtrip_and_merge():
    a = ControlInput(move_y=1.0, yaw=33.333, jump=True, select=2)
    b = P.input_from_wire(P.input_to_wire(a))
    assert (b.move_y, round(b.yaw, 2), b.jump, b.select) == (1.0, 33.33, True, 2)
    merged = P.merge_inputs(a, ControlInput(move_y=0.5, fire=True))
    assert merged.jump and merged.select == 2 and merged.fire and merged.move_y == 0.5
    held = P.held_only(merged)
    assert not held.jump and held.select is None and held.fire
    # hostile / garbage fields are ignored or coerced
    c = P.input_from_wire({"cycle": 99, "emote": "x" * 500, "nope": 1})
    assert c.cycle == 1 and len(c.emote) == 32


def test_two_players_share_one_authoritative_match(island_factory):
    srv = _server(island_factory, bot_count=5)
    a = MatchConnection("127.0.0.1", srv.port, "Alice", {"outfit": "outfit_vex_runner"})
    lobby = a.wait_for("lobby")
    assert lobby["players"] == ["Alice"] and lobby["host"]
    b = MatchConnection("127.0.0.1", srv.port, "Alice", {})
    lobby_b = b.wait_for("lobby")
    assert lobby_b["players"] == ["Alice", "Alice 2"] and not lobby_b["host"]
    b.send({"t": "start"})                      # only the host may start
    time.sleep(0.3)
    assert srv.status == "lobby"
    a.send({"t": "start"})
    sa, sb = a.wait_for("start"), b.wait_for("start")
    assert (sa["you"], sb["you"]) == (0, 1) and sa["seed"] == sb["seed"]
    late = MatchConnection("127.0.0.1", srv.port, "Late", {})
    with pytest.raises(ConnectionFailed, match="already started"):
        late.wait_for("lobby")

    ca, cb = ClientMatch(a, sa, island_factory()), ClientMatch(b, sb, island_factory())
    assert len(ca.combatants) == 6 and ca.combatants[1].name == "Alice 2" and not ca.combatants[1].is_bot
    assert ca.combatants[2].is_bot

    # both jump out, then hold "forward" while skydiving
    def inputs(cm):
        p = cm.player
        if p.state == "bus":
            return ControlInput(yaw=0, deploy=True)
        return ControlInput(yaw=90, move_y=1.0)
    _tick([ca, cb], inputs, 30 * 8)
    server_a = srv.sim.combatants[0]
    assert server_a.state in ("skydive", "glide", "ground")
    assert len(ca.items) == len(srv.sim.items) > 50
    # mirrors agree with the server within a few ticks of latency
    for cm in (ca, cb):
        for mine, real in zip(cm.combatants, srv.sim.combatants):
            assert mine.state == real.state or mine.state in ("bus", "skydive", "glide")
            assert abs(mine.x - real.x) < 25 and abs(mine.y - real.y) < 25
    # A's own view of B matches B's own view of itself
    assert abs(ca.combatants[1].x - cb.player.x) < 25
    # the input really drove the server: A moved west (yaw 90 = -X) from the drop point
    assert server_a.vx < -1.0 or server_a.state == "ground"
    ca.close()
    _tick([cb], inputs, 15)
    assert 0 in srv.sim.brains                  # a bot took over Alice
    cb.close()
    srv.stop()


def test_disconnect_and_full_match_end(island_factory):
    srv = _server(island_factory, bot_count=3, storm_time_scale=0.05, autostart=1)
    a = MatchConnection("127.0.0.1", srv.port, "Solo", {})
    start = a.wait_for("start")
    cm = ClientMatch(a, start, island_factory())
    deadline = time.monotonic() + 240
    while not cm.over and time.monotonic() < deadline and not cm.lost:
        cm.step(TICK, {cm.player.id: ControlInput(deploy=True)} if cm.player.alive else {})
        cm.drain_events()
        time.sleep(TICK / 3)
    assert cm.over and not cm.lost
    assert cm.winner == srv.sim.winner
    summary = cm.summary_for(cm.player)
    assert summary.players == 4 and 1 <= summary.placement <= 4
    cm.close()
    srv.stop()


def test_wrong_version_is_rejected(island_factory):
    srv = _server(island_factory)
    import socket
    s = P.LineSocket(socket.create_connection(("127.0.0.1", srv.port)))
    s.send({"t": "hello", "v": 999, "name": "x"})
    assert s.recv()["t"] == "error"
    s.close()
    srv.stop()
