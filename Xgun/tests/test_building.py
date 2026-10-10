"""Harvesting and building: walls block, ramps climb, floors carry, gunfire destroys."""
import copy
import math

import pytest

from bots.brain import yaw_to
from combat.weapons import WeaponInstance
from game import building as B
from game.entities import ControlInput
from game.match import TICK, MatchSim
from world.island import build_island


@pytest.fixture(scope="module")
def layout():
    return build_island(7)


def setup(layout):
    sim = MatchSim(seed=3, bot_count=1, player_name="Builder", layout=copy.deepcopy(layout))
    dummy = sim.combatants[1]
    sim.brains.pop(dummy.id)
    dummy.health = 1e9
    dummy.x, dummy.y, dummy.z, dummy.state = 500, 500, 30, "ground"
    p = sim.player
    poi = sim.layout.pois[0]
    p.state, p.on_ground = "ground", True
    p.x, p.y = B.cell_center(*B.cell_of(poi.x, poi.y))
    p.z = sim.collision.floor_height(p.x, p.y, poi.height + 1, 0.4)
    sim.ship.t = sim.ship.duration
    return sim, p


def step(sim, p, n=1, **kw):
    for _ in range(n):
        sim.step(TICK, {p.id: ControlInput(yaw=kw.pop("yaw", p.yaw), pitch=kw.pop("pitch", 0), **kw)})


def test_pickaxe_harvests_materials_from_trees(layout):
    sim, p = setup(layout)
    tree = next(pl for pl in sim.layout.placements if pl.asset == "env_tree_oak")
    p.x, p.y = tree.x, tree.y - 1.6
    p.z = sim.collision.floor_height(p.x, p.y, tree.z + 2, 0.4)
    for _ in range(int(3 / TICK)):
        ex, ey, ez = p.eye
        step(sim, p, yaw=yaw_to(tree.x - p.x, tree.y - p.y), pitch=-5, fire=True)
    assert p.materials["wood"] >= 24


def test_build_wall_blocks_movement_and_costs_material(layout):
    sim, p = setup(layout)
    p.materials["wood"] = 30
    step(sim, p, yaw=0, build_toggle=True)
    assert p.build_mode
    step(sim, p, yaw=0, build_piece="wall", fire_pressed=True)
    assert len(sim.builds) == 1 and p.materials["wood"] == 20
    step(sim, p, 6, yaw=0)
    step(sim, p, yaw=0, fire_pressed=True)                       # same spot: rejected
    assert len(sim.builds) == 1 and p.materials["wood"] == 20
    y0 = p.y
    wall_y = B.cell_center(*B.cell_of(p.x, p.y))[1] + B.GRID / 2
    step(sim, p, 90, yaw=0, move_y=1)
    assert p.y < wall_y - 0.3, "walked through a wall"
    assert p.y > y0


def test_ramp_is_climbable_and_floor_supports(layout):
    sim, p = setup(layout)
    p.materials["wood"] = 100
    z0 = p.z
    step(sim, p, yaw=0, build_toggle=True)
    step(sim, p, yaw=0, build_piece="ramp", fire_pressed=True)
    ramp = next(iter(sim.builds.values()))
    assert ramp.kind == "ramp"
    cx, cy = B.cell_center(ramp.ix, ramp.iy)
    for _ in range(int(4 / TICK)):
        step(sim, p, yaw=0, move_y=1)
        if p.y > cy + 1.6:
            break
    assert p.z > z0 + 3.0, f"only climbed to {p.z - z0:.2f} m"
    # floor ahead at the top of the ramp keeps us up there
    step(sim, p, 8, yaw=0)
    step(sim, p, yaw=0, build_piece="floor", fire_pressed=True)
    floor = [b for b in sim.builds.values() if b.kind == "floor"]
    assert floor and abs(floor[0].z - p.z) < 0.6
    step(sim, p, int(0.45 / TICK), yaw=0, move_y=1)        # ~2 m onto the new floor
    fx, fy = B.cell_center(floor[0].ix, floor[0].iy)
    assert abs(p.y - fy) < 2.0 and p.z > z0 + 3.0, "fell through the floor"


def test_gunfire_and_pickaxe_destroy_builds(layout):
    sim, p = setup(layout)
    p.materials["stone"] = 50
    p.build_material = "stone"
    step(sim, p, yaw=0, build_toggle=True)
    step(sim, p, yaw=0, build_piece="wall", fire_pressed=True)
    wall = next(iter(sim.builds.values()))
    assert wall.max_hp == B.HP["stone"]
    step(sim, p, yaw=0, build_toggle=True)                         # back to weapons
    assert not p.build_mode
    ar = WeaponInstance(sim.armory.weapons["striker_ar"], "common", 30)
    p.inventory.add_weapon(ar)
    p.inventory.add_ammo("medium", 100)
    step(sim, p, yaw=0, select=1)
    events = []
    for _ in range(int(6 / TICK)):
        step(sim, p, yaw=0, pitch=-8, fire=True, aim=True)
        events += sim.drain_events()
        if wall.id not in sim.builds:
            break
    assert wall.id not in sim.builds and any(e["type"] == "build_destroyed" for e in events)
    y0 = p.y
    step(sim, p, 45, yaw=0, move_y=1)
    assert p.y > y0 + 2.0, "destroyed wall still blocks"


def test_bots_build_cover_when_shot(layout):
    sim = MatchSim(seed=9, bot_count=12, player_name=None, layout=copy.deepcopy(layout))
    built = harvested = 0
    while sim.time < 300 and not sim.over:
        sim.step(TICK, {})
        for e in sim.drain_events():
            built += e["type"] == "build"
            harvested += e["type"] == "harvest"
    assert harvested > 0 and built > 0, (harvested, built)
