"""Battle royale simulation: movement, combat, looting, storm, bots."""
import math

import pytest

from combat.weapons import WeaponInstance
from game.entities import ControlInput
from game.match import TICK, MatchSim
from inventory.match_inventory import ConsumableStack
from world.island import build_island


@pytest.fixture(scope="module")
def layout():
    return build_island(7)


def fresh(layout, bots=3, **kw):
    """Match with ``bots`` opponents. bots=0 adds one passive, unkillable dummy so the
    match doesn't end immediately (a lone player is the last one standing)."""
    import copy
    sim = MatchSim(seed=11, bot_count=max(1, bots), player_name="Tester", layout=copy.deepcopy(layout), **kw)
    if bots == 0:
        dummy = sim.combatants[1]
        sim.brains.pop(dummy.id)
        dummy.health = 1e9
    return sim


def land(sim, c, x, y):
    c.state = "ground"
    c.x, c.y = x, y
    c.z = sim.collision.floor_height(x, y, 200, 0.4)
    c.on_ground = True
    c.prev = (c.x, c.y, c.z)


def open_spot(sim):
    p = sim.layout.pois[0]
    return p.x + 2, p.y + 2


def test_island_has_named_locations_buildings_and_loot(layout):
    assert len(layout.pois) == 7
    assert sum(1 for p in layout.placements if p.asset.startswith("env_house")) >= 8
    assert len(layout.collision.boxes) > 500
    assert len(layout.loot_spots) > 50 and len(layout.chest_spots) > 40
    for p in layout.pois:
        assert layout.terrain.height(p.x, p.y) > 1.0, p.name


def test_player_walks_jumps_and_is_blocked_by_walls(layout):
    sim = fresh(layout, 0)
    p = sim.player
    x, y = open_spot(sim)
    land(sim, p, x, y)
    start = (p.x, p.y)
    for _ in range(30):
        sim.step(TICK, {p.id: ControlInput(move_y=1, yaw=0)})
    assert p.y - start[1] > 3.0             # walked forward (+Y at yaw 0)
    land(sim, p, x, y)
    z0 = p.z
    sim.step(TICK, {p.id: ControlInput(jump=True)})
    for _ in range(5):
        sim.step(TICK, {p.id: ControlInput()})
    assert p.z > z0 + 0.5
    # a wall box directly in front stops movement
    from world.collision import Box
    land(sim, p, x, y)
    sim.collision.add(Box.from_center((x, y + 3, p.z + 1.5), (6, 0.5, 3)))
    for _ in range(60):
        sim.step(TICK, {p.id: ControlInput(move_y=1, yaw=0)})
    assert p.y < y + 3 - 0.25 - 0.39


def test_hitscan_damage_shield_headshot_and_elimination(layout):
    sim = fresh(layout, 1)
    p, bot = sim.player, sim.combatants[1]
    x, y = open_spot(sim)
    land(sim, p, x, y)
    land(sim, bot, x, y + 10)
    sim.brains.pop(bot.id)                  # hold the target still
    ar = WeaponInstance(sim.armory.weapons["striker_ar"], "common", 30)
    p.inventory.add_weapon(ar)
    p.inventory.select(1)
    bot.shield = 50
    def aim_at(z_off):
        ex, ey, ez = p.eye
        return math.degrees(math.atan2(bot.z + z_off - ez, bot.y - ey))
    inp = ControlInput(yaw=0, pitch=aim_at(1.2), fire_pressed=True, aim=True)
    sim.step(TICK, {p.id: inp, bot.id: ControlInput()})
    assert bot.shield == pytest.approx(20)  # 30 damage taken by the shield first
    assert bot.health == 100
    for _ in range(10):
        sim.step(TICK, {p.id: ControlInput(), bot.id: ControlInput()})
    sim.step(TICK, {p.id: ControlInput(yaw=0, pitch=aim_at(1.64), fire_pressed=True, aim=True), bot.id: ControlInput()})
    assert bot.shield == 0 and bot.health == pytest.approx(100 - (45 - 20))   # 30 * 1.5 headshot
    events = sim.drain_events()
    assert any(e["type"] == "hit" and e["head"] for e in events)
    for _ in range(400):
        if not bot.alive:
            break
        sim.step(TICK, {p.id: ControlInput(yaw=0, pitch=aim_at(1.2), fire=True, aim=True), bot.id: ControlInput()})
    assert not bot.alive and bot.killer == p.id
    assert p.stats.eliminations == 1 and p.stats.damage >= 150
    for _ in range(40):                     # the match can only end after the drop ship launches (1 s)
        sim.step(TICK, {p.id: ControlInput()})
    assert sim.over and sim.winner == p.id
    assert sim.summary_for(p).placement == 1


def test_pickup_chest_and_healing(layout):
    sim = fresh(layout, 0)
    p = sim.player
    x, y = open_spot(sim)
    land(sim, p, x, y)
    from game.entities import Container
    chest = Container(len(sim.containers), "chest", x, y + 1.5, p.z, 0)
    sim.containers.append(chest)
    for _ in range(25):
        sim.step(TICK, {p.id: ControlInput(interact=True)})
    assert chest.opened and p.stats.chests == 1
    weapons = [i for i in sim.items.values() if i.kind == "weapon" and math.hypot(i.x - x, i.y - y) < 4]
    assert weapons
    w = weapons[0]
    p.x, p.y = w.x, w.y
    sim.step(TICK, {p.id: ControlInput(interact=True)})
    sim.step(TICK, {p.id: ControlInput()})
    assert any(isinstance(s, WeaponInstance) for s in p.inventory.slots)
    # healing respects caps
    p.health = 40
    p.inventory.add_consumable("bandage_roll", 5)
    slot = next(i for i, s in p.inventory.consumables())
    sim.step(TICK, {p.id: ControlInput(select=slot)})
    sim.step(TICK, {p.id: ControlInput(fire_pressed=True)})
    for _ in range(int(3.2 / TICK)):
        sim.step(TICK, {p.id: ControlInput()})
    assert p.health == pytest.approx(55)
    p.health = 80
    stack_before = p.inventory.slots[slot - 1].count
    sim.step(TICK, {p.id: ControlInput(fire_pressed=True)})
    assert p.use_timer == 0 and p.inventory.slots[slot - 1].count == stack_before   # bandages cap at 75


def test_storm_damages_outside_and_shrinks(layout):
    sim = fresh(layout, 0, storm_time_scale=0.02)
    p = sim.player
    land(sim, p, 0, 0)
    radii = []
    for _ in range(int(3 / TICK)):
        sim.step(TICK, {p.id: ControlInput()})
        radii.append(sim.storm.radius)
    assert radii[-1] < radii[0]
    far = (sim.storm.center[0] + sim.storm.radius + 50, sim.storm.center[1])
    land(sim, p, *far)
    p.health = hp = 100.0
    for _ in range(int(2.5 / TICK)):
        sim.step(TICK, {p.id: ControlInput()})
    assert p.health < hp


def test_inventory_full_swaps_held_weapon(layout):
    sim = fresh(layout, 0)
    inv = sim.player.inventory
    for i in range(5):
        inv.add_weapon(WeaponInstance(sim.armory.weapons["hornet_smg"], "common", 30))
    inv.select(3)
    ok, dropped = inv.add_weapon(WeaponInstance(sim.armory.weapons["longshot_sniper"], "epic", 4))
    assert ok and dropped is not None and inv.slots[2].wdef.id == "longshot_sniper"
    assert inv.add_consumable("medkit", 2) == 0       # no room


@pytest.mark.parametrize("seed", [1, 2])
def test_bot_only_match_finishes_with_one_winner(layout, seed):
    import copy
    sim = MatchSim(seed=seed, bot_count=12, player_name=None, layout=copy.deepcopy(layout), storm_time_scale=0.5)
    counts = {}
    while not sim.over and sim.time < 900:
        sim.step(TICK, {})
        for e in sim.drain_events():
            counts[e["type"]] = counts.get(e["type"], 0) + 1
    assert sim.over and sim.winner is not None
    assert counts.get("elim", 0) == 11
    assert counts.get("land", 0) == 12 and counts.get("open", 0) > 0 and counts.get("shot", 0) > 20
    placements = sorted(c.placement for c in sim.combatants)
    assert placements == list(range(1, 13))
    assert all(c.name.startswith("BOT ") for c in sim.combatants)


def test_cosmetic_loadouts_do_not_change_gameplay(layout):
    import copy
    a = MatchSim(seed=5, bot_count=4, player_name=None, layout=copy.deepcopy(layout),
                 bot_loadouts=[{"outfit": "outfit_vex_runner"}])
    b = MatchSim(seed=5, bot_count=4, player_name=None, layout=copy.deepcopy(layout),
                 bot_loadouts=[{"outfit": "outfit_ember_ronin", "pickaxe": "pickaxe_dragonfang", "glider": "glider_phoenix"}])
    for _ in range(int(120 / TICK)):
        a.step(TICK, {})
        b.step(TICK, {})
    assert [(round(c.x, 3), round(c.health, 3)) for c in a.combatants] == [(round(c.x, 3), round(c.health, 3)) for c in b.combatants]
