"""Turns a JSON course description (data/maps/*.json) into a simulated CourseWorld.

Course file format (all lengths in metres, Z up, course runs along +Y):

  id, name, description, difficulty, order        metadata
  fall_rule      "respawn" (back to checkpoint) or "eliminate"
  time_limit     seconds before the round is closed
  kill_z         falling below this height counts as a fall
  bounds         [minx, miny, maxx, maxy]; leaving them also counts as a fall
  theme          colours used by the renderer
  spawn          {x, y, top, cols, rows, spacing}
  elements       list of course pieces, see BUILDERS below
  checkpoints    list of {x0, x1, y0, y1, top, spawn: {x, y}}
  finish         {x, y, w, l, top}
  route          main bot route: [[x, y, z, half_width, [tags]], ...]
  alt_routes     optional extra routes (e.g. a lower level)
"""

import json
import math
import os

from ..sim.obstacles import (BouncePad, MovingPlatform, PendulumHammer, Pusher, Ramp,
                             Solid, Sweeper, VanishingTile)
from ..sim.route import Route, Waypoint
from ..sim.world import Checkpoint, CourseWorld, Zone


class MapFormatError(ValueError):
    pass


def _req(d, key, where):
    if key not in d:
        raise MapFormatError("%s: missing required field '%s'" % (where, key))
    return d[key]


def _num(d, key, where, default=None):
    v = d.get(key, default)
    if v is None:
        raise MapFormatError("%s: missing required number '%s'" % (where, key))
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
        raise MapFormatError("%s: '%s' must be a finite number" % (where, key))
    return float(v)


def _box_center(e, where, default_h=1.0):
    top = _num(e, "top", where)
    h = _num(e, "h", where, default_h)
    return (_num(e, "x", where), _num(e, "y", where), top - h * 0.5), (
        _num(e, "w", where), _num(e, "l", where), h)


class _Builder:
    def __init__(self, world):
        self.world = world
        self.counter = 0
        self.decor = []

    def next_id(self, e, prefix):
        self.counter += 1
        return e.get("id") or "%s_%d" % (prefix, self.counter)

    # Each builder receives the element dict and a location string for errors.
    def platform(self, e, where):
        c, s = _box_center(e, where)
        self.world.add_solid(Solid(self.next_id(e, "plat"), c, s, e.get("style")))

    def ramp(self, e, where):
        z0, z1 = _num(e, "z0", where), _num(e, "z1", where)
        h = _num(e, "h", where, 1.0)
        bottom = min(z0, z1) - h
        top = max(z0, z1)
        c = (_num(e, "x", where), _num(e, "y", where), (bottom + top) * 0.5)
        s = (_num(e, "w", where), _num(e, "l", where), top - bottom)
        self.world.add_solid(Ramp(self.next_id(e, "ramp"), c, s, z0, z1, e.get("style")))

    def hurdle(self, e, where):
        base = _num(e, "top", where)
        height = _num(e, "height", where)
        x, y = _num(e, "x", where), _num(e, "y", where)
        w, l = _num(e, "w", where), _num(e, "l", where)
        style = dict(e.get("style") or {})
        style.setdefault("role", "hurdle")
        self.world.add_solid(Solid(self.next_id(e, "hurdle"), (x, y, base + height * 0.5),
                                   (w, l, height), style))
        self._zone(x, y, w, l + 1.2, base + height - 0.2, "hurdle")

    def gap_zone(self, e, where):
        self._zone(_num(e, "x", where), _num(e, "y", where), _num(e, "w", where),
                   _num(e, "l", where), _num(e, "min_z", where), "gap")

    def _zone(self, x, y, w, l, min_z, kind):
        zid = "zone_%d" % len(self.world.obstacle_zones)
        self.world.obstacle_zones.append(
            Zone(zid, x - w / 2, y - l / 2, min_z, x + w / 2, y + l / 2, min_z + 30.0, kind=kind))

    def moving(self, e, where):
        c, s = _box_center(e, where, 0.6)
        off = e.get("offset")
        if not (isinstance(off, list) and len(off) == 3):
            raise MapFormatError("%s: 'offset' must be [dx, dy, dz]" % where)
        self.world.add_solid(MovingPlatform(
            self.next_id(e, "mover"), c, s, [float(v) for v in off], _num(e, "period", where),
            math.radians(_num(e, "phase", where, 0.0)), e.get("style")))

    def pusher(self, e, where):
        c, s = _box_center(e, where, 1.6)
        off = e.get("offset")
        if not (isinstance(off, list) and len(off) == 3):
            raise MapFormatError("%s: 'offset' must be [dx, dy, dz]" % where)
        self.world.add_solid(Pusher(
            self.next_id(e, "pusher"), c, s, [float(v) for v in off], _num(e, "period", where),
            math.radians(_num(e, "phase", where, 0.0)), _num(e, "knock", where, 9.0),
            e.get("style")))

    def bounce(self, e, where):
        c, s = _box_center(e, where, 0.4)
        self.world.add_solid(BouncePad(self.next_id(e, "pad"), c, s, _num(e, "bounce", where, 16.0),
                                       e.get("style")))

    def tile(self, e, where):
        c, s = _box_center(e, where, 0.5)
        self.world.add_solid(VanishingTile(self.next_id(e, "tile"), c, s,
                                           _num(e, "warn", where, 0.7), _num(e, "gone", where, 4.0),
                                           e.get("style")))

    def tile_grid(self, e, where):
        x0, y0 = _num(e, "x0", where), _num(e, "y0", where)
        cols, rows = int(_num(e, "cols", where)), int(_num(e, "rows", where))
        tw, tl = _num(e, "tw", where, 2.0), _num(e, "tl", where, 2.0)
        gap = _num(e, "gap", where, 0.3)
        top, h = _num(e, "top", where), _num(e, "h", where, 0.5)
        warn, gone = _num(e, "warn", where, 0.7), _num(e, "gone", where, 4.0)
        holes = {tuple(hv) for hv in e.get("holes", [])}
        prefix = e.get("id") or "grid%d" % self.counter
        self.counter += 1
        for r in range(rows):
            for c in range(cols):
                if (c, r) in holes:
                    continue
                center = (x0 + c * (tw + gap), y0 + r * (tl + gap), top - h / 2)
                self.world.add_solid(VanishingTile("%s_%d_%d" % (prefix, c, r), center, (tw, tl, h),
                                                   warn, gone, e.get("style")))

    def hammer(self, e, where):
        pivot = _req(e, "pivot", where)
        self.world.add_hazard(PendulumHammer(
            self.next_id(e, "hammer"), [float(v) for v in pivot], _num(e, "length", where),
            _num(e, "amplitude", where), _num(e, "period", where),
            math.radians(_num(e, "phase", where, 0.0)), _num(e, "head_radius", where, 0.65),
            _num(e, "head_half_len", where, 0.9), e.get("axis", "y"), e.get("style")))

    def sweeper(self, e, where):
        self.world.add_hazard(Sweeper(
            self.next_id(e, "sweeper"), (_num(e, "x", where), _num(e, "y", where)),
            _num(e, "z", where), _num(e, "length", where), _num(e, "speed", where),
            int(_num(e, "arms", where, 2)), math.radians(_num(e, "phase", where, 0.0)),
            _num(e, "radius", where, 0.28), e.get("style")))

    def decor(self, e, where):
        self.decor.append(e)


BUILDERS = {name for name in dir(_Builder) if not name.startswith("_") and name != "next_id"}


def _parse_route(raw, where, s_ref=None):
    if not isinstance(raw, list) or len(raw) < 2:
        raise MapFormatError("%s: a route needs at least two waypoints" % where)
    pts = []
    for i, w in enumerate(raw):
        if not isinstance(w, list) or len(w) < 4:
            raise MapFormatError("%s[%d]: waypoint must be [x, y, z, half_width, tags?]" % (where, i))
        tags = w[4] if len(w) > 4 else []
        pts.append(Waypoint(float(w[0]), float(w[1]), float(w[2]), float(w[3]), tags))
    route = Route(pts)
    if s_ref is not None:
        # Align an alternative route's distances with the main route.
        offset, _, _, _ = s_ref.project(pts[0].x, pts[0].y, pts[0].z)
        for p in pts:
            p.s += offset
        route.length += offset
    return route


def spawn_grid(spawn, count):
    """Start positions: rows of `cols` players, rows going backwards from spawn.y."""
    cols = int(spawn.get("cols", 4))
    spacing = float(spawn.get("spacing", 2.2))
    out = []
    for i in range(count):
        r, c = divmod(i, cols)
        stagger = 0.25 * spacing if r % 2 else 0.0  # odd rows shifted so nobody hides behind
        x = spawn["x"] + (c - (cols - 1) / 2.0) * spacing + stagger
        y = spawn["y"] - r * spacing
        out.append((x, y, spawn["top"]))
    return out


class LoadedMap:
    """A parsed course definition.  `build_world()` gives a fresh simulation each round."""

    def __init__(self, data, path=None):
        self.data = data
        self.path = path
        where = path or data.get("id", "<map>")
        self.id = _req(data, "id", where)
        self.name = _req(data, "name", where)
        self.description = data.get("description", "")
        self.difficulty = data.get("difficulty", "normal")
        self.order = int(data.get("order", 99))
        self.fall_rule = data.get("fall_rule", "respawn")
        if self.fall_rule not in ("respawn", "eliminate"):
            raise MapFormatError("%s: fall_rule must be 'respawn' or 'eliminate'" % where)
        self.time_limit = _num(data, "time_limit", where, 120.0)
        self.theme = data.get("theme", {})
        self.spawn = _req(data, "spawn", where)
        for k in ("x", "y", "top"):
            _num(self.spawn, k, where + ".spawn")
        if not isinstance(data.get("elements"), list) or not data["elements"]:
            raise MapFormatError("%s: 'elements' must be a non-empty list" % where)
        for i, e in enumerate(data["elements"]):
            t = e.get("type") if isinstance(e, dict) else None
            if t not in BUILDERS:
                raise MapFormatError("%s.elements[%d]: unknown element type %r" % (where, i, t))
        _req(data, "finish", where)
        _req(data, "route", where)
        self.decor = []
        self.build_world()  # validates the whole file once at load time

    def build_world(self):
        d = self.data
        where = self.path or self.id
        world = CourseWorld(self.id, self.name)
        world.fall_rule = self.fall_rule
        world.time_limit = self.time_limit
        world.kill_z = _num(d, "kill_z", where, -12.0)
        if "bounds" in d:
            b = d["bounds"]
            world.bounds = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        builder = _Builder(world)
        for i, e in enumerate(d["elements"]):
            getattr(builder, e["type"])(e, "%s.elements[%d]" % (where, i))
        self.decor = builder.decor

        sp = self.spawn
        world.checkpoints.append(Checkpoint(0, -1e9, -1e9, -1e9, 1e9, 1e9, 1e9,
                                            spawn_grid(sp, 16), 0.0))
        for i, cp in enumerate(d.get("checkpoints", []), start=1):
            w = "%s.checkpoints[%d]" % (where, i - 1)
            top = _num(cp, "top", w)
            spawn = dict(cp.get("spawn", {}))
            spawn.setdefault("x", (cp["x0"] + cp["x1"]) / 2.0)
            spawn.setdefault("y", cp["y0"] + 1.5)
            spawn.setdefault("top", top)
            spawn.setdefault("cols", 4)
            spawn.setdefault("spacing", 1.6)
            world.checkpoints.append(Checkpoint(
                i, _num(cp, "x0", w), _num(cp, "y0", w), top - 0.5, _num(cp, "x1", w),
                _num(cp, "y1", w), top + 4.0, spawn_grid(spawn, 8), 0.0))
        f = d["finish"]
        fw, fl, ftop = _num(f, "w", where), _num(f, "l", where), _num(f, "top", where)
        fx, fy = _num(f, "x", where), _num(f, "y", where)
        world.finish = Zone("finish", fx - fw / 2, fy - fl / 2, ftop - 0.5, fx + fw / 2, fy + fl / 2,
                            ftop + 6.0)
        world.route = _parse_route(d["route"], where + ".route")
        world.alt_routes = [_parse_route(r, "%s.alt_routes[%d]" % (where, i), world.route)
                            for i, r in enumerate(d.get("alt_routes", []))]
        world.reset()
        return world

    def spawn_points(self, count):
        return spawn_grid(self.spawn, count)


def load_map_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise MapFormatError("%s: invalid JSON (%s)" % (path, exc)) from exc
    return LoadedMap(data, os.path.basename(path))
