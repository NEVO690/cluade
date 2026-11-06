"""Tile map: parsing, collision, destructible tiles and objective markers (pure logic)."""
import math

from ilbrawl.config import TILE

FLOOR = "."
WALL = "#"
BUSH = "B"
CRATE = "C"
BARREL = "X"
WATER = "W"
POWERBOX = "P"

WALK_SOLID = {WALL, CRATE, BARREL, WATER, POWERBOX}
SHOT_SOLID = {WALL, CRATE, BARREL, POWERBOX}
DESTRUCTIBLE_HP = {CRATE: 1800, BARREL: 1200, POWERBOX: 2600}
MARKERS = {"1", "2", "S", "G", "O", "Z", "A", "R"}
ALL_TILES = [FLOOR, WALL, BUSH, CRATE, BARREL, WATER, POWERBOX, "1", "2", "S", "G", "O", "Z", "A", "R"]


class TileMap:
    def __init__(self, mapdef):
        rows = mapdef["tiles"]
        self.id = mapdef.get("id", "custom")
        self.theme = mapdef.get("theme", "meadow")
        self.h = len(rows)
        self.w = max(len(r) for r in rows)
        self.grid = []
        self.spawns = {"1": [], "2": [], "S": []}
        self.gem_mines = []
        self.orb_spawns = []
        self.zones = []
        self.goals = {"A": set(), "R": set()}
        self.hp = {}
        for y, row in enumerate(rows):
            row = row.ljust(self.w, FLOOR)
            out = []
            for x, c in enumerate(row):
                center = ((x + 0.5) * TILE, (y + 0.5) * TILE)
                if c in ("1", "2", "S"):
                    self.spawns[c].append(center)
                elif c == "G":
                    self.gem_mines.append(center)
                elif c == "O":
                    self.orb_spawns.append(center)
                elif c == "Z":
                    self.zones.append(center)
                elif c in ("A", "R"):
                    self.goals[c].add((x, y))
                tile = c if c not in MARKERS else FLOOR
                if tile not in (FLOOR, WALL, BUSH, CRATE, BARREL, WATER, POWERBOX):
                    tile = FLOOR
                if tile in DESTRUCTIBLE_HP:
                    self.hp[(x, y)] = DESTRUCTIBLE_HP[tile]
                out.append(tile)
            self.grid.append(out)
        self.pw = self.w * TILE
        self.ph = self.h * TILE
        self.temp_walls = {}     # (x, y) -> seconds remaining
        self.dirty = set()       # tiles whose look changed (renderer redraws them)

    # ------------------------------------------------------------ queries
    def in_bounds(self, tx, ty):
        return 0 <= tx < self.w and 0 <= ty < self.h

    def tile(self, tx, ty):
        if not self.in_bounds(tx, ty):
            return WALL
        return self.grid[ty][tx]

    @staticmethod
    def to_tile(px, py):
        return int(px // TILE), int(py // TILE)

    def walk_blocked(self, tx, ty):
        if not self.in_bounds(tx, ty):
            return True
        return self.grid[ty][tx] in WALK_SOLID or (tx, ty) in self.temp_walls

    def shot_blocked(self, tx, ty):
        if not self.in_bounds(tx, ty):
            return True
        return self.grid[ty][tx] in SHOT_SOLID or (tx, ty) in self.temp_walls

    def is_bush_at(self, px, py):
        tx, ty = self.to_tile(px, py)
        return self.in_bounds(tx, ty) and self.grid[ty][tx] == BUSH

    def point_shot_blocked(self, px, py):
        return self.shot_blocked(int(px // TILE), int(py // TILE))

    # ------------------------------------------------------------ modification
    def damage_tile(self, tx, ty, amount):
        """Returns the destroyed tile char, or None."""
        if (tx, ty) not in self.hp:
            return None
        self.hp[(tx, ty)] -= amount
        if self.hp[(tx, ty)] <= 0:
            del self.hp[(tx, ty)]
            old = self.grid[ty][tx]
            self.grid[ty][tx] = FLOOR
            self.dirty.add((tx, ty))
            return old
        return None

    def add_temp_wall(self, tx, ty, duration):
        if self.in_bounds(tx, ty) and self.grid[ty][tx] in (FLOOR, BUSH):
            self.temp_walls[(tx, ty)] = duration
            return True
        return False

    def update(self, dt):
        if self.temp_walls:
            for k in list(self.temp_walls):
                self.temp_walls[k] -= dt
                if self.temp_walls[k] <= 0:
                    del self.temp_walls[k]

    # ------------------------------------------------------------ collision helpers
    def resolve_circle(self, x, y, r):
        """Push a circle out of all walking-solid tiles it overlaps."""
        for _ in range(3):
            moved = False
            x0, x1 = int((x - r) // TILE), int((x + r) // TILE)
            y0, y1 = int((y - r) // TILE), int((y + r) // TILE)
            for ty in range(y0, y1 + 1):
                for tx in range(x0, x1 + 1):
                    if not self.walk_blocked(tx, ty):
                        continue
                    rx, ry = tx * TILE, ty * TILE
                    cx = min(max(x, rx), rx + TILE)
                    cy = min(max(y, ry), ry + TILE)
                    dx, dy = x - cx, y - cy
                    d2 = dx * dx + dy * dy
                    if d2 >= r * r:
                        continue
                    if d2 > 1e-6:
                        d = math.sqrt(d2)
                        push = r - d
                        x += dx / d * push
                        y += dy / d * push
                    else:
                        # centre inside the tile: push out along the shallowest axis
                        left, right = x - rx, rx + TILE - x
                        top, bottom = y - ry, ry + TILE - y
                        m = min(left, right, top, bottom)
                        if m == left:
                            x = rx - r
                        elif m == right:
                            x = rx + TILE + r
                        elif m == top:
                            y = ry - r
                        else:
                            y = ry + TILE + r
                    moved = True
            if not moved:
                break
        x = min(max(x, r), self.pw - r)
        y = min(max(y, r), self.ph - r)
        return x, y

    def line_clear(self, x0, y0, x1, y1, shots=True):
        d = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(d / (TILE / 4)))
        check = self.shot_blocked if shots else self.walk_blocked
        for i in range(1, steps):
            t = i / steps
            if check(int((x0 + (x1 - x0) * t) // TILE), int((y0 + (y1 - y0) * t) // TILE)):
                return False
        return True

    def free_point_near(self, px, py, max_r=6):
        tx, ty = self.to_tile(px, py)
        if not self.walk_blocked(tx, ty):
            return px, py
        for r in range(1, max_r + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    if not self.walk_blocked(tx + dx, ty + dy):
                        return (tx + dx + 0.5) * TILE, (ty + dy + 0.5) * TILE
        return px, py

    def goal_team_at(self, px, py):
        """Which goal (0 for 'A' = team 1's goal, 1 for 'R') contains the point, or None."""
        t = self.to_tile(px, py)
        if t in self.goals["A"]:
            return 0
        if t in self.goals["R"]:
            return 1
        return None
