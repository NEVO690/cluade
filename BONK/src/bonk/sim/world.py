"""The simulated course: colliders, hazards, zones and fast spatial queries."""

import math

from .constants import CHAR_RADIUS


class Zone:
    """Axis-aligned trigger volume (checkpoint, finish line, obstacle counter...)."""

    def __init__(self, zid, minx, miny, minz, maxx, maxy, maxz, **data):
        self.id = zid
        self.minx, self.miny, self.minz = minx, miny, minz
        self.maxx, self.maxy, self.maxz = maxx, maxy, maxz
        self.data = data

    def contains(self, x, y, z):
        return (self.minx <= x <= self.maxx and self.miny <= y <= self.maxy
                and self.minz <= z <= self.maxz)


class Checkpoint(Zone):
    def __init__(self, index, minx, miny, minz, maxx, maxy, maxz, spawns, yaw=0.0):
        super().__init__("cp%d" % index, minx, miny, minz, maxx, maxy, maxz)
        self.index = index
        self.spawns = spawns  # list of (x, y, z)
        self.yaw = yaw

    def spawn_for(self, slot):
        return self.spawns[slot % len(self.spawns)]


class SpatialGrid:
    """Buckets objects by the Y cells their sweep bounds cover (courses are long in Y)."""

    def __init__(self, cell=4.0):
        self.cell = cell
        self.buckets = {}
        self._query = 0

    def insert(self, obj):
        b = obj.sweep_bounds()
        for c in range(int(math.floor(b[1] / self.cell)), int(math.floor(b[4] / self.cell)) + 1):
            self.buckets.setdefault(c, []).append(obj)

    def query(self, miny, maxy):
        self._query += 1
        q = self._query
        out = []
        for c in range(int(math.floor(miny / self.cell)), int(math.floor(maxy / self.cell)) + 1):
            for obj in self.buckets.get(c, ()):
                if obj._stamp != q:
                    obj._stamp = q
                    out.append(obj)
        return out


class CourseWorld:
    def __init__(self, map_id, name):
        self.map_id = map_id
        self.name = name
        self.solids = []
        self.dynamic = []  # solids that need update()
        self.hazards = []
        self.checkpoints = []
        self.finish = None
        self.obstacle_zones = []
        self.route = None
        self.kill_z = -12.0
        self.bounds = (-60.0, -30.0, 60.0, 400.0)  # minx, miny, maxx, maxy
        self.time_limit = 120.0
        self.fall_rule = "respawn"  # or "eliminate"
        self.solid_grid = SpatialGrid()
        self.hazard_grid = SpatialGrid()
        self.t = 0.0
        self._by_id = {}

    # ------------------------------------------------------------ building
    def add_solid(self, solid):
        self.solids.append(solid)
        self._by_id[solid.id] = solid
        if solid.moving or solid.kind == "tile":
            self.dynamic.append(solid)
        self.solid_grid.insert(solid)
        return solid

    def add_hazard(self, hazard):
        self.hazards.append(hazard)
        self._by_id[hazard.id] = hazard
        self.hazard_grid.insert(hazard)
        return hazard

    def get(self, oid):
        return self._by_id.get(oid)

    @property
    def tiles(self):
        return [s for s in self.dynamic if s.kind == "tile"]

    # ------------------------------------------------------------ simulation
    def update(self, t, dt):
        self.t = t
        for s in self.dynamic:
            s.update(t, dt)
        for h in self.hazards:
            h.update(t, dt)

    def reset(self):
        self.t = 0.0
        for s in self.dynamic:
            if s.kind == "tile":
                s.triggered_at = None
                s.state = s.SOLID
            s.update(0.0, 0.0)
            s.dx = s.dy = s.dz = 0.0

    # ------------------------------------------------------------ queries
    def solids_near(self, y, margin=1.5):
        return self.solid_grid.query(y - margin, y + margin)

    def hazards_near(self, y, margin=1.5):
        return self.hazard_grid.query(y - margin, y + margin)

    def ground_probe(self, x, y, z_from, max_drop=50.0, radius=0.12):
        """Highest walkable surface under (x, y) between z_from and z_from - max_drop.

        Returns (height, solid) or (None, None).
        """
        best_h, best_s = None, None
        for s in self.solid_grid.query(y - radius, y + radius):
            if not s.is_solid():
                continue
            if x + radius < s.minx or x - radius > s.maxx or y + radius < s.miny or y - radius > s.maxy:
                continue
            h = s.top_at(min(max(x, s.minx), s.maxx), min(max(y, s.miny), s.maxy))
            if h <= z_from + 1e-3 and h >= z_from - max_drop and (best_h is None or h > best_h):
                best_h, best_s = h, s
        return best_h, best_s

    def wall_probe(self, x, y, z_feet, dx, dy, dist, step=0.32, radius=CHAR_RADIUS):
        """First solid blocking horizontal movement from (x, y) along (dx, dy).

        Returns (distance, solid, top_height) or (None, None, None).  Solids
        lower than `step` above the feet do not block (they are climbed).
        """
        best = (None, None, None)
        steps = max(2, int(dist / 0.25))
        cands = [s for s in self.solids_near(y + dy * dist * 0.5, dist + 1.0)
                 if s.is_solid() and s.maxz > z_feet + step and s.minz < z_feet + 1.4]
        if not cands:
            return best
        for i in range(1, steps + 1):
            d = dist * i / steps
            px, py = x + dx * d, y + dy * d
            for s in cands:
                if (s.minx - radius * 0.8 <= px <= s.maxx + radius * 0.8
                        and s.miny - radius * 0.8 <= py <= s.maxy + radius * 0.8):
                    top = s.top_at(px, py)
                    if top > z_feet + step:
                        return d, s, top
        return best

    def out_of_bounds(self, x, y, z):
        minx, miny, maxx, maxy = self.bounds
        return z < self.kill_z or x < minx or x > maxx or y < miny or y > maxy

    def checkpoint_at(self, x, y, z):
        found = None
        for cp in self.checkpoints:
            if cp.contains(x, y, z):
                found = cp
        return found
