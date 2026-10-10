"""XGUN - battle royale in one Python file.

Runs with plain Python 3.8+ and nothing to install (it only uses tkinter, which
ships with Python on Windows and macOS). Paste it into IDLE, VS Code, PyCharm,
Thonny or Pydroid, save it as xgun.py and run it.

Controls
  W A S D  move            Mouse   aim            Left click  shoot / swing / use
  Shift    sprint          R       reload         E           pick up, hold to open chests
  1        pickaxe         2-6     items          Q           build a wall (10 wood)
  Space    jump out of the drop ship              M           big map
  Enter    play again      Esc     quit

Drop from the ship, loot weapons, shields and heals, chop trees for wood, build
walls for cover and be the last one standing against the AI bots while the
storm closes in.
"""
import math
import os
import random
import time
import tkinter as tk

# ------------------------------------------------------------------ settings
WIN_W, WIN_H = 1100, 700
WORLD = 3200
ISLAND_R = 1300
BOTS = 19
PLAYER_R = 12
WALK, SPRINT = 190.0, 290.0
FPS = 60

RARITY = ["common", "uncommon", "rare", "epic", "legendary"]
RARITY_COL = {"common": "#b9bfd0", "uncommon": "#3ddc6e", "rare": "#3fa9ff", "epic": "#b46cff", "legendary": "#ffb627"}
RARITY_MULT = {"common": 1.0, "uncommon": 1.05, "rare": 1.1, "epic": 1.16, "legendary": 1.22}
WEAPONS = {
    #          damage rate  mag  reload spread pellets range  ammo      auto
    "AR":      (30, 5.5, 30, 2.2, 3.0, 1, 900, "medium", True),
    "SMG":     (17, 12.0, 30, 2.0, 6.0, 1, 600, "light", True),
    "Shotgun": (10, 1.1, 5, 3.8, 11.0, 9, 300, "shells", False),
    "Sniper":  (100, 0.6, 4, 3.0, 0.6, 1, 1700, "heavy", False),
    "Pistol":  (24, 6.5, 16, 1.4, 3.5, 1, 700, "light", False),
}
WEAPON_WEIGHT = {"AR": 26, "SMG": 20, "Shotgun": 20, "Pistol": 18, "Sniper": 9}
AMMO = {"light": (30, 300), "medium": (30, 300), "heavy": (6, 40), "shells": (8, 60)}
AMMO_COL = {"light": "#8cbcff", "medium": "#73e67f", "heavy": "#ff7366", "shells": "#ffcc4d"}
HEALS = {  # name: (health, shield, cap, use time, stack, rarity)
    "Bandage": (15, 0, 75, 3.0, 15, "common"),
    "Medkit": (100, 0, 100, 7.0, 3, "uncommon"),
    "Shield": (0, 50, 100, 5.0, 3, "rare"),
    "Mini Shield": (0, 25, 50, 2.0, 6, "uncommon"),
}
STORM = [(60, 40, 850, 1), (45, 35, 520, 2), (35, 30, 290, 4), (30, 25, 140, 6), (25, 20, 50, 8), (20, 20, 0, 12)]
NAMES = ["Kestrel", "Ozzie", "Mira", "Juno", "Pixel", "Rook", "Tango", "Nova", "Cinder", "Wren", "Bishop", "Sable",
         "Echo", "Fable", "Gizmo", "Halo", "Indigo", "Jett", "Koda", "Lumen", "Moss", "Nyx", "Orbit", "Pike"]
TOWNS = ["Neon Plaza", "Harbor Point", "Pinewood Lodge", "Sunset Dunes", "Maple Row", "Ridge Watch", "Rustyard"]


def clamp(v, a, b):
    return max(a, min(b, v))


def weighted(table):
    total = sum(table.values())
    r = random.uniform(0, total)
    for k, w in table.items():
        r -= w
        if r <= 0:
            return k
    return next(iter(table))


def seg_circle(x0, y0, x1, y1, cx, cy, r):
    """Distance along the segment where it first enters the circle, or None."""
    dx, dy = x1 - x0, y1 - y0
    fx, fy = x0 - cx, y0 - cy
    a = dx * dx + dy * dy
    if a == 0:
        return None
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    t = (-b - math.sqrt(disc)) / (2 * a)
    if 0 <= t <= 1:
        return t
    return None


def seg_rect(x0, y0, x1, y1, r):
    """Slab test: fraction along the segment where it hits rect (x0, y0, x1, y1), or None."""
    tmin, tmax = 0.0, 1.0
    for o, d, lo, hi in ((x0, x1 - x0, r[0], r[2]), (y0, y1 - y0, r[1], r[3])):
        if abs(d) < 1e-9:
            if o < lo or o > hi:
                return None
        else:
            t1, t2 = (lo - o) / d, (hi - o) / d
            if t1 > t2:
                t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin


# ------------------------------------------------------------------ world
class Island:
    def __init__(self):
        self.shape = []
        k1, k2, k3 = random.uniform(0, 6), random.uniform(0, 6), random.uniform(0, 6)
        for i in range(96):
            a = i / 96 * math.tau
            r = ISLAND_R * (1 + 0.09 * math.sin(3 * a + k1) + 0.06 * math.sin(5 * a + k2) + 0.04 * math.sin(9 * a + k3))
            self.shape.append((a, r))
        self.walls = []        # [x0, y0, x1, y1, kind, hp]  (hp None = indestructible)
        self.floors = []       # (x0, y0, x1, y1, colour)
        self.trees = []        # [x, y, r, kind, hp]
        self.towns = []
        self.chest_spots = []
        self.loot_spots = []
        self._towns()
        self._nature()

    def radius_at(self, a):
        i = int((a % math.tau) / math.tau * 96) % 96
        a0, r0 = self.shape[i]
        _a1, r1 = self.shape[(i + 1) % 96]
        f = ((a % math.tau) - a0) / (math.tau / 96)
        return r0 + (r1 - r0) * f

    def on_land(self, x, y, margin=0):
        return math.hypot(x, y) < self.radius_at(math.atan2(y, x)) - margin

    def _house(self, cx, cy, w, h, door_side):
        t = 12
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        self.floors.append((x0, y0, x1, y1, random.choice(["#8f7a62", "#7d8796", "#937469", "#7f8f72"])))
        door = 70
        sides = {
            "n": [(x0, y0, x1, y0 + t)], "s": [(x0, y1 - t, x1, y1)],
            "w": [(x0, y0, x0 + t, y1)], "e": [(x1 - t, y0, x1, y1)],
        }
        for side, rects in sides.items():
            for r in rects:
                if side == door_side:
                    if side in "ns":
                        mid = (r[0] + r[2]) / 2
                        self.walls.append([r[0], r[1], mid - door / 2, r[3], "house", None])
                        self.walls.append([mid + door / 2, r[1], r[2], r[3], "house", None])
                    else:
                        mid = (r[1] + r[3]) / 2
                        self.walls.append([r[0], r[1], r[2], mid - door / 2, "house", None])
                        self.walls.append([r[0], mid + door / 2, r[2], r[3], "house", None])
                else:
                    self.walls.append([r[0], r[1], r[2], r[3], "house", None])
        self.chest_spots.append((cx + random.uniform(-w / 4, w / 4), cy + random.uniform(-h / 4, h / 4)))
        for _ in range(2):
            self.loot_spots.append((cx + random.uniform(-w / 3, w / 3), cy + random.uniform(-h / 3, h / 3)))

    def _towns(self):
        a0 = random.uniform(0, math.tau)
        spots = [(random.uniform(-60, 60), random.uniform(-60, 60))]
        for i in range(6):
            a = a0 + i * math.tau / 6 + random.uniform(-0.25, 0.25)
            d = random.uniform(620, 820)
            spots.append((math.cos(a) * d, math.sin(a) * d))
        for i, (tx, ty) in enumerate(spots):
            self.towns.append((TOWNS[i], tx, ty))
            placed = []
            for _ in range(60):
                if len(placed) >= (5 if i == 0 else 4):
                    break
                w, h = random.choice([(220, 170), (180, 180), (260, 150), (160, 220)])
                cx, cy = tx + random.uniform(-230, 230), ty + random.uniform(-230, 230)
                box = (cx - w / 2 - 50, cy - h / 2 - 50, cx + w / 2 + 50, cy + h / 2 + 50)
                if any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in placed):
                    continue
                if not self.on_land(cx, cy, 260):
                    continue
                placed.append(box)
                self._house(cx, cy, w, h, random.choice("nsew"))
            for _ in range(6):
                self.loot_spots.append((tx + random.uniform(-300, 300), ty + random.uniform(-300, 300)))
        self.town_boxes = [(f[0] - 40, f[1] - 40, f[2] + 40, f[3] + 40) for f in self.floors]

    def _nature(self):
        tries = 0
        while len(self.trees) < 330 and tries < 6000:
            tries += 1
            x, y = random.uniform(-ISLAND_R, ISLAND_R), random.uniform(-ISLAND_R, ISLAND_R)
            if not self.on_land(x, y, 90):
                continue
            if any(b[0] < x < b[2] and b[1] < y < b[3] for b in self.town_boxes):
                continue
            if random.random() < 0.78:
                self.trees.append([x, y, random.uniform(16, 22), "tree", 150])
            else:
                self.trees.append([x, y, random.uniform(18, 28), "rock", 220])
        for _ in range(40):
            x, y = random.uniform(-ISLAND_R, ISLAND_R), random.uniform(-ISLAND_R, ISLAND_R)
            if self.on_land(x, y, 120):
                self.loot_spots.append((x, y))


# ------------------------------------------------------------------ entities
class Fighter:
    def __init__(self, fid, name, bot):
        self.id, self.name, self.bot = fid, name, bot
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.angle = 0.0
        self.hp, self.shield = 100.0, 0.0
        self.state = "ship"          # ship / glide / ground / dead
        self.glide = 0.0
        self.slots = [None] * 5      # weapon dicts or heal dicts
        self.sel = 0                 # 0 = pickaxe
        self.ammo = {k: 0 for k in AMMO}
        self.wood = 0
        self.cool = 0.0
        self.reload = 0.0
        self.use = 0.0
        self.open_t = 0.0
        self.kills = 0
        self.damage = 0
        self.place = 0
        self.killer = None
        self.last_hit = -99.0
        self.storm_t = 0.0
        self.death_t = 0.0
        self.flash = 0.0

    @property
    def alive(self):
        return self.state != "dead"

    def current(self):
        return None if self.sel == 0 else self.slots[self.sel - 1]


class Game:
    def __init__(self, ui=None):
        self.ui = ui
        self.island = Island()
        self.time = 0.0
        self.items = []              # dicts: kind weapon/ammo/heal
        self.chests = [{"x": x, "y": y, "open": False} for x, y in self.island.chest_spots]
        self.fx = []                 # tracers / effects
        self.feed = []
        self.over = False
        self.winner = None
        a = random.uniform(0, math.tau)
        off = random.uniform(-400, 400)
        nx, ny = -math.sin(a), math.cos(a)
        self.ship_a = (math.cos(a) * 1700 + nx * off, math.sin(a) * 1700 + ny * off)
        self.ship_b = (-math.cos(a) * 1700 + nx * off, -math.sin(a) * 1700 + ny * off)
        self.ship_t = 0.0
        self.ship_len = math.dist(self.ship_a, self.ship_b) / 180.0
        self.storm = {"phase": 0, "x": 0.0, "y": 0.0, "r": 1900.0, "tx": 0.0, "ty": 0.0, "tr": STORM[0][2],
                      "timer": STORM[0][0], "shrink": False, "dps": 1, "sx": 0.0, "sy": 0.0, "sr": 1900.0}
        self._next_storm()
        self.fighters = [Fighter(0, "You", False)]
        names = random.sample(NAMES, BOTS)
        for i in range(BOTS):
            f = Fighter(i + 1, "BOT " + names[i], True)
            f.jump_at = random.uniform(2, self.ship_len * 0.8)
            town = random.choice(self.island.towns)
            f.drop = (town[1] + random.uniform(-200, 200), town[2] + random.uniform(-200, 200))
            f.goal = None
            f.goal_t = 0.0
            f.target = None
            f.think = random.uniform(0, 0.3)
            f.strafe = 1
            f.strafe_t = 0.0
            f.stuck = 0.0
            f.last_pos = (0, 0)
            f.detour = 0.0
            self.fighters.append(f)
        self.player = self.fighters[0]
        for x, y in self.island.loot_spots:
            if random.random() < 0.8:
                self.spawn_random(x, y)

    # -------------------------------------------------------------- loot
    def roll_weapon(self, better=False):
        name = weighted(WEAPON_WEIGHT)
        weights = [45, 30, 17, 6, 2] if not better else [15, 32, 30, 16, 7]
        rarity = random.choices(RARITY, weights)[0]
        if name == "Sniper" and rarity in ("common", "uncommon"):
            rarity = "rare"
        return {"kind": "weapon", "name": name, "rarity": rarity, "mag": WEAPONS[name][2]}

    def drop(self, item, x, y):
        item = dict(item)
        item["x"], item["y"], item["t"] = x, y, self.time
        self.items.append(item)

    def spawn_random(self, x, y, better=False):
        r = random.random()
        if r < 0.45 or better:
            w = self.roll_weapon(better)
            self.drop(w, x, y)
            ammo = WEAPONS[w["name"]][7]
            self.drop({"kind": "ammo", "ammo": ammo, "n": AMMO[ammo][0] * (2 if better else 1)}, x + 22, y + 10)
        if r >= 0.45 and r < 0.75 or better:
            name = random.choice(list(HEALS))
            self.drop({"kind": "heal", "name": name, "n": 1 if HEALS[name][4] <= 3 else 3}, x - 20, y + 6)
        if r >= 0.75:
            ammo = random.choice(list(AMMO))
            self.drop({"kind": "ammo", "ammo": ammo, "n": AMMO[ammo][0]}, x, y)

    # -------------------------------------------------------------- storm
    def _next_storm(self):
        s = self.storm
        for _ in range(60):
            max_off = max(0.0, s["r"] - s["tr"]) * (0.8 if s["phase"] else 0.3)
            a, d = random.uniform(0, math.tau), max_off * math.sqrt(random.random())
            x, y = s["x"] + math.cos(a) * d, s["y"] + math.sin(a) * d
            if self.island.on_land(x, y, 60):
                s["tx"], s["ty"] = x, y
                return
        s["tx"], s["ty"] = s["x"], s["y"]

    def update_storm(self, dt):
        s = self.storm
        if s["phase"] >= len(STORM):
            return
        s["timer"] -= dt
        wait, shrink, _r, dps = STORM[s["phase"]]
        if s["shrink"]:
            t = 1 - max(0.0, s["timer"]) / shrink
            s["r"] = s["sr"] + (s["tr"] - s["sr"]) * t
            s["x"] = s["sx"] + (s["tx"] - s["sx"]) * t
            s["y"] = s["sy"] + (s["ty"] - s["sy"]) * t
            if s["timer"] <= 0:
                s["shrink"] = False
                s["phase"] += 1
                if s["phase"] < len(STORM):
                    s["timer"] = STORM[s["phase"]][0]
                    s["tr"] = STORM[s["phase"]][2]
                    self._next_storm()
        elif s["timer"] <= 0:
            s["shrink"], s["dps"] = True, dps
            s["sx"], s["sy"], s["sr"] = s["x"], s["y"], s["r"]
            s["timer"] = shrink
            self.message("THE STORM IS CLOSING", 3)

    def in_storm(self, x, y):
        s = self.storm
        return math.hypot(x - s["x"], y - s["y"]) > s["r"]

    def message(self, text, secs=3):
        if self.ui:
            self.ui.show_message(text, secs)

    # -------------------------------------------------------------- physics
    def blocked_rects(self, x, y, r):
        for w in self.island.walls:
            if w[0] - r < x < w[2] + r and w[1] - r < y < w[3] + r:
                yield w

    def move(self, f, dx, dy):
        nx, ny = f.x + dx, f.y + dy
        r = PLAYER_R
        for _ in range(2):
            for w in self.blocked_rects(nx, ny, r):
                cx, cy = clamp(nx, w[0], w[2]), clamp(ny, w[1], w[3])
                ddx, ddy = nx - cx, ny - cy
                d = math.hypot(ddx, ddy)
                if d < r:
                    if d < 1e-6:
                        pen = [(nx - w[0] + r, -1, 0), (w[2] - nx + r, 1, 0), (ny - w[1] + r, 0, -1), (w[3] - ny + r, 0, 1)]
                        p, sx, sy = min(pen)
                        nx += sx * p
                        ny += sy * p
                    else:
                        nx += ddx / d * (r - d)
                        ny += ddy / d * (r - d)
            for t in self.island.trees:
                ddx, ddy = nx - t[0], ny - t[1]
                d = math.hypot(ddx, ddy)
                if d < t[2] + r and d > 1e-6:
                    nx += ddx / d * (t[2] + r - d)
                    ny += ddy / d * (t[2] + r - d)
        if not self.island.on_land(nx, ny, -120):     # shallow water ring, no further
            return
        moved = math.hypot(nx - f.x, ny - f.y)
        f.x, f.y = nx, ny
        return moved

    def ray(self, shooter, x0, y0, a, rng):
        """Hitscan: returns (end x, end y, victim, wall, tree)."""
        x1, y1 = x0 + math.cos(a) * rng, y0 + math.sin(a) * rng
        best, hit = 1.0, (None, None, None)
        for w in self.island.walls:
            if min(x0, x1) > w[2] or max(x0, x1) < w[0] or min(y0, y1) > w[3] or max(y0, y1) < w[1]:
                continue
            t = seg_rect(x0, y0, x1, y1, w)
            if t is not None and t < best:
                best, hit = t, (None, w, None)
        for tr in self.island.trees:
            if abs(tr[0] - x0) > rng + 30 or abs(tr[1] - y0) > rng + 30:
                continue
            t = seg_circle(x0, y0, x1, y1, tr[0], tr[1], tr[2])
            if t is not None and t < best:
                best, hit = t, (None, None, tr)
        for f in self.fighters:
            if f is shooter or f.state != "ground":
                continue
            t = seg_circle(x0, y0, x1, y1, f.x, f.y, PLAYER_R + 1)
            if t is not None and t < best:
                best, hit = t, (f, None, None)
        return (x0 + (x1 - x0) * best, y0 + (y1 - y0) * best) + hit

    def los(self, a, b):
        ex, ey, victim, wall, tree = self.ray(a, a.x, a.y, math.atan2(b.y - a.y, b.x - a.x), math.dist((a.x, a.y), (b.x, b.y)))
        return victim is b or (wall is None and tree is None)

    # -------------------------------------------------------------- combat
    def hurt(self, v, attacker, amount, storm=False):
        if not v.alive or amount <= 0:
            return
        v.last_hit = self.time
        v.flash = 0.25
        if not storm and v.shield > 0:
            absorbed = min(v.shield, amount)
            v.shield -= absorbed
            amount -= absorbed
        v.hp -= amount
        if attacker is not None and attacker is not v:
            attacker.damage += int(amount)
        if v.hp <= 0:
            self.kill(v, attacker)

    def kill(self, v, k):
        if self.over:
            return
        v.place = sum(1 for f in self.fighters if f.alive)
        v.state = "dead"
        v.hp = 0
        v.death_t = self.time
        v.killer = k
        if k is not None and k is not v:
            k.kills += 1
            self.feed.append((self.time, f"{k.name} eliminated {v.name}", k is self.player or v is self.player))
        else:
            self.feed.append((self.time, f"{v.name} was lost in the storm", v is self.player))
        for i, s in enumerate(v.slots):
            if s:
                a = i * 1.25
                self.drop(s, v.x + math.cos(a) * 28, v.y + math.sin(a) * 28)
        for j, (kind, n) in enumerate(v.ammo.items()):
            if n > 0:
                a = j * 1.6 + 0.4
                self.drop({"kind": "ammo", "ammo": kind, "n": n}, v.x + math.cos(a) * 46, v.y + math.sin(a) * 46)
        if v.wood:
            self.drop({"kind": "wood", "n": v.wood}, v.x, v.y)
        v.slots = [None] * 5
        v.ammo = {k2: 0 for k2 in AMMO}
        v.wood = 0
        alive = [f for f in self.fighters if f.alive]
        if len(alive) <= 1:
            self.over = True
            self.winner = alive[0] if alive else None
            if alive:
                alive[0].place = 1

    def shoot(self, f):
        w = f.current()
        if f.cool > 0 or f.reload > 0 or f.use > 0 or f.state != "ground":
            return
        if w is None:                                   # pickaxe swing
            f.cool = 1 / 1.8
            ex, ey, victim, wall, tree = self.ray(f, f.x, f.y, f.angle, 42)
            if victim:
                self.hurt(victim, f, 20)
            elif tree:
                tree[4] -= 50
                f.wood = min(999, f.wood + (12 if tree[3] == "tree" else 9))
                if tree[4] <= 0:
                    self.island.trees.remove(tree)
            elif wall and wall[5] is not None:
                self.damage_wall(wall, 50)
            self.fx.append(["swing", f.x, f.y, f.angle, self.time])
            return
        if w["kind"] != "weapon":
            if w["kind"] == "heal":
                self.start_use(f, w)
            return
        dmg, rate, mag, rel, spread, pellets, rng, ammo, auto = WEAPONS[w["name"]]
        if w["mag"] <= 0:
            self.start_reload(f)
            return
        w["mag"] -= 1
        f.cool = 1 / rate
        moving = math.hypot(f.vx, f.vy) > 30
        sp = math.radians(spread + (2.5 if moving else 0))
        for _ in range(pellets):
            a = f.angle + random.gauss(0, sp / 2)
            ex, ey, victim, wall, tree = self.ray(f, f.x + math.cos(f.angle) * 14, f.y + math.sin(f.angle) * 14, a, rng)
            if victim:
                d = math.dist((f.x, f.y), (victim.x, victim.y))
                fall = 1.0 if d < rng * 0.35 else max(0.55, 1 - (d - rng * 0.35) / rng)
                self.hurt(victim, f, dmg * RARITY_MULT[w["rarity"]] * fall)
                if f is self.player and self.ui:
                    self.ui.hit_marker()
            elif wall is not None and wall[5] is not None:
                self.damage_wall(wall, dmg * (1.5 if w["name"] == "Shotgun" else 1))
            self.fx.append(["tracer", f.x + math.cos(f.angle) * 14, f.y + math.sin(f.angle) * 14, ex, ey, self.time,
                            RARITY_COL[w["rarity"]]])
        if self.ui and math.dist((f.x, f.y), (self.player.x, self.player.y)) < 900:
            self.ui.sound("shot")

    def damage_wall(self, wall, amount):
        wall[5] -= amount
        if wall[5] <= 0 and wall in self.island.walls:
            self.island.walls.remove(wall)

    def start_reload(self, f):
        w = f.current()
        if not w or w["kind"] != "weapon" or f.reload > 0:
            return
        need = WEAPONS[w["name"]][2] - w["mag"]
        if need > 0 and f.ammo[WEAPONS[w["name"]][7]] > 0:
            f.reload = WEAPONS[w["name"]][3]

    def start_use(self, f, h):
        hp, sh, cap, t, _stack, _r = HEALS[h["name"]]
        if (hp and f.hp >= cap) or (sh and f.shield >= cap):
            if f is self.player and self.ui:
                self.ui.notice("Already full for this item")
            return
        f.use = t
        f.use_slot = f.sel

    def finish_use(self, f):
        h = f.current()
        if not h or h["kind"] != "heal" or f.sel != getattr(f, "use_slot", -1):
            return
        hp, sh, cap, _t, _s, _r = HEALS[h["name"]]
        if hp:
            f.hp = min(100.0, max(f.hp, min(cap, f.hp + hp)))
        if sh:
            f.shield = min(100.0, max(f.shield, min(cap, f.shield + sh)))
        h["n"] -= 1
        if h["n"] <= 0:
            f.slots[f.sel - 1] = None
            f.sel = 0

    def build(self, f):
        if f.wood < 10 or f.state != "ground" or f.cool > 0:
            if f is self.player and self.ui and f.wood < 10:
                self.ui.notice("Need 10 wood - hit trees with the pickaxe")
            return
        cx, cy = f.x + math.cos(f.angle) * 46, f.y + math.sin(f.angle) * 46
        horizontal = abs(math.sin(f.angle)) > abs(math.cos(f.angle))
        w, h = (90, 14) if horizontal else (14, 90)
        rect = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
        if any(rect[0] < o[2] and rect[2] > o[0] and rect[1] < o[3] and rect[3] > o[1] for o in self.island.walls):
            return
        for g in self.fighters:
            if g.state == "ground" and rect[0] - PLAYER_R < g.x < rect[2] + PLAYER_R and rect[1] - PLAYER_R < g.y < rect[3] + PLAYER_R:
                return
        f.wood -= 10
        f.cool = 0.2
        self.island.walls.append(rect + ["build", 150])

    def pickup(self, f, item):
        if item["kind"] == "ammo":
            cap = AMMO[item["ammo"]][1]
            take = min(item["n"], cap - f.ammo[item["ammo"]])
            if take <= 0:
                return False
            f.ammo[item["ammo"]] += take
            item["n"] -= take
            if item["n"] <= 0:
                self.items.remove(item)
            return True
        if item["kind"] == "wood":
            f.wood = min(999, f.wood + item["n"])
            self.items.remove(item)
            return True
        if item["kind"] == "heal":
            for s in f.slots:
                if s and s["kind"] == "heal" and s["name"] == item["name"] and s["n"] < HEALS[item["name"]][4]:
                    s["n"] += item["n"]
                    self.items.remove(item)
                    return True
        clean = {k: v for k, v in item.items() if k not in ("x", "y", "t")}
        if None in f.slots:
            i = f.slots.index(None)
            f.slots[i] = clean
            if f.sel == 0:
                f.sel = i + 1
        elif f.sel > 0:
            old = f.slots[f.sel - 1]
            f.slots[f.sel - 1] = clean
            self.drop(old, f.x, f.y)
        else:
            if f is self.player and self.ui:
                self.ui.notice("Inventory full - select a slot to swap")
            return False
        self.items.remove(item)
        if f is self.player and self.ui:
            self.ui.sound("pickup")
        return True

    def near_item(self, f, r=42):
        best, bd = None, r
        for it in self.items:
            d = math.hypot(it["x"] - f.x, it["y"] - f.y)
            if d < bd:
                best, bd = it, d
        return best

    def near_chest(self, f, r=46):
        for c in self.chests:
            if not c["open"] and math.hypot(c["x"] - f.x, c["y"] - f.y) < r:
                return c
        return None

    def open_chest(self, c):
        c["open"] = True
        self.spawn_random(c["x"] + 30, c["y"], better=True)
        if self.ui:
            self.ui.sound("chest")

    # -------------------------------------------------------------- per tick
    def ship_pos(self):
        t = min(1.0, self.ship_t / self.ship_len)
        return (self.ship_a[0] + (self.ship_b[0] - self.ship_a[0]) * t, self.ship_a[1] + (self.ship_b[1] - self.ship_a[1]) * t)

    def step(self, dt, inp):
        if self.over:
            return
        self.time += dt
        self.ship_t += dt
        self.update_storm(dt)
        for f in self.fighters:
            if not f.alive:
                continue
            control = inp if f is self.player else self.think(f, dt)
            self.update_fighter(f, control, dt)
        self.fx = [e for e in self.fx if self.time - e[-2 if e[0] == "tracer" else -1] < 0.12]
        self.feed = [e for e in self.feed if self.time - e[0] < 8][-6:]

    def update_fighter(self, f, c, dt):
        f.flash = max(0.0, f.flash - dt)
        if f.state == "ship":
            f.x, f.y = self.ship_pos()
            if (c.get("jump") and self.ship_t > 1.5) or self.ship_t > self.ship_len * 0.9:
                f.state, f.glide = "glide", 5.0
            return
        f.angle = c.get("angle", f.angle)
        mx, my = c.get("mx", 0), c.get("my", 0)
        n = math.hypot(mx, my)
        if n > 1:
            mx, my = mx / n, my / n
        if f.state == "glide":
            f.glide -= dt
            f.x += mx * 420 * dt
            f.y += my * 420 * dt
            if f.glide <= 0:
                f.state = "ground"
                f.x, f.y = clamp(f.x, -WORLD / 2, WORLD / 2), clamp(f.y, -WORLD / 2, WORLD / 2)
                for _ in range(40):                      # don't land inside a wall or tree
                    if not list(self.blocked_rects(f.x, f.y, PLAYER_R)) and not any(
                            math.hypot(f.x - t[0], f.y - t[1]) < t[2] + PLAYER_R for t in self.island.trees):
                        break
                    f.x += random.uniform(-30, 30)
                    f.y += random.uniform(-30, 30)
            return
        speed = SPRINT if c.get("sprint") and f.use <= 0 else WALK
        if f.use > 0:
            speed *= 0.4
        if not self.island.on_land(f.x, f.y):
            speed *= 0.55
        f.vx += (mx * speed - f.vx) * min(1.0, dt * 12)
        f.vy += (my * speed - f.vy) * min(1.0, dt * 12)
        self.move(f, f.vx * dt, f.vy * dt)
        f.cool = max(0.0, f.cool - dt)
        sel = c.get("select")
        if sel is not None and sel != f.sel and 0 <= sel <= 5:
            f.sel, f.reload, f.use = sel, 0.0, 0.0
            f.cool = max(f.cool, 0.2)
        if f.reload > 0:
            f.reload -= dt
            if f.reload <= 0:
                w = f.current()
                if w and w["kind"] == "weapon":
                    ammo = WEAPONS[w["name"]][7]
                    take = min(WEAPONS[w["name"]][2] - w["mag"], f.ammo[ammo])
                    w["mag"] += take
                    f.ammo[ammo] -= take
        elif c.get("reload"):
            self.start_reload(f)
        if f.use > 0:
            f.use -= dt
            if f.use <= 0:
                self.finish_use(f)
        w = f.current()
        auto = w is not None and w["kind"] == "weapon" and WEAPONS[w["name"]][8]
        if c.get("fire_pressed") or (c.get("fire") and (auto or w is None)):
            if w and w["kind"] == "heal":
                if c.get("fire_pressed") and f.use <= 0:
                    self.start_use(f, w)
            else:
                self.shoot(f)
        if c.get("build"):
            self.build(f)
        if c.get("interact"):
            ch = self.near_chest(f)
            if ch:
                f.open_t += dt
                if f.open_t >= 0.6:
                    self.open_chest(ch)
                    f.open_t = 0
            elif c.get("interact_pressed"):
                it = self.near_item(f)
                if it and it["kind"] != "ammo":
                    self.pickup(f, it)
        else:
            f.open_t = 0
        for it in list(self.items):                    # ammo and wood are picked up automatically
            if it["kind"] in ("ammo", "wood") and math.hypot(it["x"] - f.x, it["y"] - f.y) < 26:
                self.pickup(f, it)
        if self.in_storm(f.x, f.y):
            f.storm_t += dt
            if f.storm_t >= 1:
                f.storm_t -= 1
                self.hurt(f, None, self.storm["dps"], storm=True)
        else:
            f.storm_t = 0

    # -------------------------------------------------------------- bots
    def weapons_of(self, f):
        return [(s, i + 1) for i, s in enumerate(f.slots) if s and s["kind"] == "weapon"
                and (s["mag"] > 0 or f.ammo[WEAPONS[s["name"]][7]] > 0)]

    def think(self, f, dt):
        c = {"angle": f.angle}
        if f.state == "ship":
            sx, sy = self.ship_pos()
            c["jump"] = math.hypot(sx - f.drop[0], sy - f.drop[1]) < 500 or self.ship_t > f.jump_at
            return c
        if f.state == "glide":
            dx, dy = f.drop[0] - f.x, f.drop[1] - f.y
            d = math.hypot(dx, dy)
            if d > 20:
                c["mx"], c["my"] = dx / d, dy / d
            return c
        f.think -= dt
        if f.think <= 0:
            f.think = 0.3
            best, bd = None, 520
            for o in self.fighters:
                if o is f or o.state != "ground":
                    continue
                d = math.hypot(o.x - f.x, o.y - f.y)
                if d < bd and self.los(f, o):
                    best, bd = o, d
            f.target = best
        weapons = self.weapons_of(f)
        # heal up when nobody is around
        if not f.target and self.time - f.last_hit > 4 and f.use <= 0:
            for i, s in enumerate(f.slots):
                if s and s["kind"] == "heal":
                    hp, sh, cap = HEALS[s["name"]][:3]
                    if (hp and f.hp < min(cap, 80)) or (sh and f.shield < cap):
                        if f.sel != i + 1:
                            c["select"] = i + 1
                        else:
                            c["fire_pressed"] = True
                        return c
        if f.use > 0:
            return c
        t = f.target
        if t and t.alive and (weapons or math.hypot(t.x - f.x, t.y - f.y) < 120):
            dx, dy = t.x - f.x, t.y - f.y
            d = math.hypot(dx, dy)
            if weapons:
                best = max(weapons, key=lambda wi: self.score_weapon(wi[0], d))
                if f.sel != best[1]:
                    c["select"] = best[1]
                    return c
            err = 0.11 * (1 + d / 700)
            c["angle"] = math.atan2(dy, dx) + math.sin(self.time * 2.1 + f.id) * err
            w = f.current()
            ideal = 60 if not w else (110 if w["name"] == "Shotgun" else 650 if w["name"] == "Sniper" else 300)
            f.strafe_t -= dt
            if f.strafe_t <= 0:
                f.strafe, f.strafe_t = random.choice((-1, 1)), random.uniform(0.5, 1.5)
            fwd = 1 if d > ideal + 60 else (-0.7 if d < ideal - 60 else 0)
            ux, uy = dx / d, dy / d
            c["mx"] = ux * fwd - uy * f.strafe * 0.8
            c["my"] = uy * fwd + ux * f.strafe * 0.8
            if w and w["kind"] == "weapon":
                if w["mag"] > 0:
                    c["fire"] = True
                    c["fire_pressed"] = (int(self.time * 5) % 2) == 0
                else:
                    c["reload"] = True
            elif d < 45:
                c["fire"] = True
            if f.wood >= 10 and self.time - f.last_hit < 0.4 and random.random() < 0.05 and d > 120:
                c["build"] = True
            return c
        # storm, then loot, then wander
        s = self.storm
        inside = s["r"] - math.hypot(f.x - s["x"], f.y - s["y"])
        if inside < 60 or (s["shrink"] and inside < 200):
            f.goal = ("move", s["tx"] if s["shrink"] else s["x"], s["ty"] if s["shrink"] else s["y"], None)
        elif not f.goal or f.goal[0] == "wander" or self.time - f.goal_t > 12:
            self.bot_loot_goal(f, weapons)
        if not f.goal:
            a, d = random.uniform(0, math.tau), random.uniform(0, max(50, s["r"] * 0.6))
            f.goal = ("wander", s["x"] + math.cos(a) * d, s["y"] + math.sin(a) * d, None)
            f.goal_t = self.time
        if weapons and not (f.current() and f.current()["kind"] == "weapon"):
            c["select"] = weapons[0][1]
        kind, gx, gy, ref = f.goal
        dx, dy = gx - f.x, gy - f.y
        d = math.hypot(dx, dy)
        if kind == "chop" and d < 48:
            c["angle"] = math.atan2(dy, dx)
            c["select"] = 0
            c["fire"] = True
            if f.wood >= 60 or ref not in self.island.trees:
                f.goal = None
            return c
        if kind == "loot" and d < 30:
            if isinstance(ref, dict) and "open" in ref:
                c["interact"] = True
                if ref["open"]:
                    f.goal = None
            else:
                c["interact"] = c["interact_pressed"] = True
                f.goal = None
            return c
        if d < 25:
            f.goal = None
            return c
        ang = math.atan2(dy, dx)
        if f.detour > 0:
            f.detour -= dt
            ang += f.detour_dir
        c["angle"] = ang
        c["mx"], c["my"] = math.cos(ang), math.sin(ang)
        c["sprint"] = d > 300
        f.stuck += dt
        if f.stuck > 1.0:
            if math.dist((f.x, f.y), f.last_pos) < 40:
                f.detour, f.detour_dir = 0.9, random.choice((-1.3, 1.3))
                f.fails = getattr(f, "fails", 0) + 1
                if f.fails > 3:
                    f.goal, f.fails = None, 0
                    if ref is not None:
                        f.ignore = getattr(f, "ignore", set()) | {id(ref)}
            else:
                f.fails = 0
            f.stuck, f.last_pos = 0.0, (f.x, f.y)
        return c

    def score_weapon(self, w, d):
        dmg, rate, _m, _r, _s, pellets, rng, _a, _auto = WEAPONS[w["name"]]
        s = dmg * pellets * min(rate, 4) * RARITY_MULT[w["rarity"]]
        if w["name"] == "Shotgun":
            s *= 1.6 if d < 160 else 0.25
        if w["name"] == "Sniper":
            s *= 2 if d > 500 else 0.5
        if d > rng:
            s *= 0.2
        return s * (1 if w["mag"] else 0.5)

    def bot_loot_goal(self, f, weapons):
        ignore = getattr(f, "ignore", set())
        best, bd = None, 700
        full = None not in f.slots
        for ch in self.chests:
            if not ch["open"] and id(ch) not in ignore:
                d = math.hypot(ch["x"] - f.x, ch["y"] - f.y) * 0.7
                if d < bd:
                    best, bd = ("loot", ch["x"], ch["y"], ch), d
        for it in self.items:
            if id(it) in ignore:
                continue
            if it["kind"] == "weapon" and (full or len(weapons) >= 2):
                continue
            if it["kind"] == "heal" and full:
                continue
            if it["kind"] == "ammo" and not any(WEAPONS[s["name"]][7] == it["ammo"] for s, _i in weapons):
                continue
            d = math.hypot(it["x"] - f.x, it["y"] - f.y) * (0.6 if it["kind"] == "weapon" else 1)
            if d < bd:
                best, bd = ("loot", it["x"], it["y"], it), d
        if best is None and f.wood < 40:
            for t in self.island.trees:
                if t[3] == "tree" and abs(t[0] - f.x) < 300 and abs(t[1] - f.y) < 300 and id(t) not in ignore:
                    best = ("chop", t[0], t[1], t)
                    break
        f.goal = best
        f.goal_t = self.time


# ------------------------------------------------------------------ window, input and drawing
class App:
    def __init__(self, root):
        self.root = root
        root.title("XGUN - battle royale")
        self.cv = tk.Canvas(root, width=WIN_W, height=WIN_H, bg="#0b3550", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.keys = set()
        self.pressed = set()
        self.mouse = (WIN_W / 2, WIN_H / 2 - 100)
        self.mouse_down = False
        self.msg, self.msg_until = "", 0.0
        self.note, self.note_until = "", 0.0
        self.hit_until = 0.0
        self.big_map = False
        self.state = "menu"
        self.game = None
        self.last = time.perf_counter()
        root.bind("<KeyPress>", self.key_down)
        root.bind("<KeyRelease>", self.key_up)
        self.cv.bind("<Motion>", lambda e: setattr(self, "mouse", (e.x, e.y)))
        self.cv.bind("<ButtonPress-1>", self.click)
        self.cv.bind("<ButtonRelease-1>", lambda e: setattr(self, "mouse_down", False))
        root.bind("<Configure>", self.resize)
        self.w, self.h = WIN_W, WIN_H
        self.loop()

    # ---------------------------------------------------------- input
    def resize(self, e):
        if e.widget is self.root:
            self.w, self.h = max(600, e.width), max(400, e.height)

    def key_down(self, e):
        k = e.keysym.lower()
        if k not in self.keys:
            self.pressed.add(k)
        self.keys.add(k)
        if k == "escape":
            self.root.destroy()
        if k == "return" and self.state in ("menu", "over"):
            self.start()

    def key_up(self, e):
        self.keys.discard(e.keysym.lower())

    def click(self, e):
        self.mouse_down = True
        self.pressed.add("mouse")
        if self.state in ("menu", "over"):
            self.start()

    def start(self):
        self.game = Game(self)
        self.state = "play"
        self.show_message("DROP SHIP LAUNCHED", 4)

    def show_message(self, text, secs):
        self.msg, self.msg_until = text, time.time() + secs

    def notice(self, text):
        self.note, self.note_until = text, time.time() + 2

    def hit_marker(self):
        self.hit_until = time.time() + 0.12

    def sound(self, _name):
        pass                                          # tkinter has no portable audio

    def gather(self):
        k, g = self.keys, self.game
        p = g.player
        cx, cy = self.w / 2, self.h / 2
        c = {"mx": ("d" in k) - ("a" in k), "my": ("s" in k) - ("w" in k),
             "sprint": "shift_l" in k or "shift_r" in k,
             "angle": math.atan2(self.mouse[1] - cy, self.mouse[0] - cx),
             "fire": self.mouse_down, "fire_pressed": "mouse" in self.pressed,
             "reload": "r" in self.pressed, "interact": "e" in k, "interact_pressed": "e" in self.pressed,
             "jump": "space" in self.pressed, "build": "q" in self.pressed}
        for i in range(6):
            if str(i + 1) in self.pressed:
                c["select"] = i
        if "m" in self.pressed:
            self.big_map = not self.big_map
        if p.state == "ship":
            c["mx"] = c["my"] = 0
        return c

    # ---------------------------------------------------------- main loop
    def loop(self):
        now = time.perf_counter()
        dt = min(0.05, now - self.last)
        self.last = now
        if self.state == "play":
            g = self.game
            c = self.gather()
            steps = max(1, int(dt / (1 / 120)) + 1)
            for i in range(steps):
                if i:
                    c["fire_pressed"] = c["reload"] = c["jump"] = c["build"] = c["interact_pressed"] = False
                    c.pop("select", None)
                g.step(dt / steps, c)
            if g.over or (not g.player.alive and g.time - g.player.death_t > 2.5):
                if not getattr(g, "end_time", None):
                    g.end_time = time.time()
                if time.time() - g.end_time > (3 if g.over and g.winner is g.player else 0.5):
                    self.state = "over"
        self.pressed.clear()
        self.draw()
        self.root.after(max(1, int(1000 / FPS - (time.perf_counter() - now) * 1000)), self.loop)

    # ---------------------------------------------------------- drawing
    def draw(self):
        cv = self.cv
        cv.delete("all")
        if self.state == "menu" or self.game is None:
            return self.draw_menu()
        g = self.game
        p = g.player
        focus = p
        if not p.alive:
            alive = [f for f in g.fighters if f.alive]
            focus = p.killer if p.killer is not None and p.killer.alive else (alive[0] if alive else p)
        camx, camy = focus.x - self.w / 2, focus.y - self.h / 2
        if focus.state == "ship":
            camx, camy = g.ship_pos()[0] - self.w / 2, g.ship_pos()[1] - self.h / 2
        sx = lambda x: x - camx
        sy = lambda y: y - camy
        view = (camx - 60, camy - 60, camx + self.w + 60, camy + self.h + 60)
        vis = lambda x, y, r=0: view[0] - r < x < view[2] + r and view[1] - r < y < view[3] + r
        # island
        isl = g.island
        for scale, col in ((1.0, "#e6d29b"), (0.94, "#5fa04a")):
            pts = []
            for a, r in isl.shape:
                pts += [sx(math.cos(a) * r * scale), sy(math.sin(a) * r * scale)]
            cv.create_polygon(pts, fill=col, outline="")
        for name, tx, ty in isl.towns:
            if vis(tx, ty, 300):
                cv.create_oval(sx(tx - 290), sy(ty - 290), sx(tx + 290), sy(ty + 290), fill="#8e9184", outline="")
        for f0 in isl.floors:
            if vis((f0[0] + f0[2]) / 2, (f0[1] + f0[3]) / 2, 200):
                cv.create_rectangle(sx(f0[0]), sy(f0[1]), sx(f0[2]), sy(f0[3]), fill=f0[4], outline="")
        for name, tx, ty in isl.towns:
            if vis(tx, ty, 300):
                cv.create_text(sx(tx), sy(ty) - 260, text=name.upper(), fill="#ffffff", font=("Segoe UI", 12, "bold"))
        # chests and items
        for ch in g.chests:
            if vis(ch["x"], ch["y"]):
                x, y = sx(ch["x"]), sy(ch["y"])
                if not ch["open"]:
                    cv.create_oval(x - 22, y - 22, x + 22, y + 22, fill="", outline="#ffd45a", width=2)
                cv.create_rectangle(x - 13, y - 9, x + 13, y + 9, fill="#8a5a2b" if ch["open"] else "#d9a52b", outline="#4a2e12", width=2)
        for it in g.items:
            if not vis(it["x"], it["y"]):
                continue
            x, y = sx(it["x"]), sy(it["y"])
            if it["kind"] == "weapon":
                col = RARITY_COL[it["rarity"]]
                cv.create_oval(x - 13, y - 13, x + 13, y + 13, fill="", outline=col, width=2)
                cv.create_rectangle(x - 10, y - 3, x + 10, y + 3, fill="#2b2f3a", outline=col)
                cv.create_text(x, y + 20, text=it["name"], fill=col, font=("Segoe UI", 8, "bold"))
            elif it["kind"] == "heal":
                col = "#3fa9ff" if HEALS[it["name"]][1] else "#ff5b6b"
                cv.create_oval(x - 9, y - 9, x + 9, y + 9, fill=col, outline="#ffffff")
                cv.create_text(x, y, text="+", fill="#ffffff", font=("Segoe UI", 10, "bold"))
            elif it["kind"] == "ammo":
                cv.create_rectangle(x - 6, y - 5, x + 6, y + 5, fill=AMMO_COL[it["ammo"]], outline="#20242e")
            else:
                cv.create_rectangle(x - 8, y - 5, x + 8, y + 5, fill="#b7834f", outline="#5b3c1e")
        # characters
        for f in g.fighters:
            if f.state in ("ship",) or not vis(f.x, f.y):
                continue
            x, y = sx(f.x), sy(f.y)
            if f.state == "dead":
                if g.time - f.death_t < 5:
                    cv.create_text(x, y, text="x", fill="#ff4d5e", font=("Segoe UI", 14, "bold"))
                continue
            if f.state == "glide":
                cv.create_oval(x - 8, y + 10, x + 8, y + 16, fill="#2c3e2a", outline="")
                cv.create_polygon(x - 26, y - 14, x, y - 26, x + 26, y - 14, x, y - 20, fill="#ffb627", outline="#7a4b00")
            body = "#ffffff" if f.flash > 0 else ("#ffc23d" if f is p else "#e04e5a")
            cv.create_oval(x - PLAYER_R, y - PLAYER_R, x + PLAYER_R, y + PLAYER_R, fill=body, outline="#1b1d2a", width=2)
            hx, hy = x + math.cos(f.angle) * 18, y + math.sin(f.angle) * 18
            w = f.current()
            cv.create_line(x + math.cos(f.angle) * 8, y + math.sin(f.angle) * 8, hx, hy,
                           fill="#20242e" if w is None or w["kind"] != "weapon" else RARITY_COL[w["rarity"]], width=4)
            if f is not p:
                cv.create_text(x, y - 22, text=f.name, fill="#ffffff", font=("Segoe UI", 8))
                cv.create_rectangle(x - 14, y - 16, x - 14 + 28 * max(0, f.hp) / 100, y - 14, fill="#2ee59d", outline="")
        # trees and walls on top (so you can hide)
        for t in isl.trees:
            if vis(t[0], t[1], 30):
                x, y, r = sx(t[0]), sy(t[1]), t[2]
                if t[3] == "tree":
                    cv.create_oval(x - r * 1.8, y - r * 1.8, x + r * 1.8, y + r * 1.8, fill="#2f7d3a", outline="#245f2d")
                    cv.create_oval(x - r * 0.9, y - r * 1.2, x + r * 0.5, y + r * 0.2, fill="#3f9a48", outline="")
                else:
                    cv.create_oval(x - r, y - r * 0.8, x + r, y + r * 0.8, fill="#8f8b80", outline="#5e5b54", width=2)
        for wl in isl.walls:
            if vis((wl[0] + wl[2]) / 2, (wl[1] + wl[3]) / 2, 150):
                col = "#3a3f4b" if wl[4] == "house" else ("#c48a4f" if wl[5] > 75 else "#8f5a35")
                cv.create_rectangle(sx(wl[0]), sy(wl[1]), sx(wl[2]), sy(wl[3]), fill=col, outline="#1c1f26")
        # tracers
        for e in g.fx:
            if e[0] == "tracer":
                cv.create_line(sx(e[1]), sy(e[2]), sx(e[3]), sy(e[4]), fill=e[6], width=2)
            else:
                _k, x0, y0, a, _t = e
                cv.create_arc(sx(x0) - 34, sy(y0) - 34, sx(x0) + 34, sy(y0) + 34, start=-math.degrees(a) - 40, extent=80,
                              style="arc", outline="#ffffff", width=2)
        # drop ship
        if g.ship_t < g.ship_len + 3:
            shx, shy = g.ship_pos()
            a = math.atan2(g.ship_b[1] - g.ship_a[1], g.ship_b[0] - g.ship_a[0])
            pts = []
            for px, py in ((40, 0), (-30, -14), (-20, 0), (-30, 14)):
                pts += [sx(shx + px * math.cos(a) - py * math.sin(a)), sy(shy + px * math.sin(a) + py * math.cos(a))]
            cv.create_polygon(pts, fill="#dfe3ee", outline="#6b3cf0", width=3)
            wing = [sx(shx - 34 * math.sin(a)), sy(shy + 34 * math.cos(a)), sx(shx + 34 * math.sin(a)), sy(shy - 34 * math.cos(a))]
            cv.create_line(*wing, fill="#dfe3ee", width=10)
        # storm (shade everything outside the circle)
        s = g.storm
        r = s["r"]
        cx, cy = sx(s["x"]), sy(s["y"])
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#b46cff", width=4)
        band = 2400                                   # a very thick ring = everything outside the safe zone
        R = r + band / 2
        cv.create_oval(cx - R, cy - R, cx + R, cy + R, outline="#7d3cc8", width=band, outlinestipple="gray50")
        self.draw_hud(g, p)

    def draw_hud(self, g, p):
        cv, W, H = self.cv, self.w, self.h
        font = ("Segoe UI", 10, "bold")
        # vitals
        cv.create_rectangle(16, H - 76, 296, H - 16, fill="#141829", outline="")
        cv.create_rectangle(26, H - 66, 26 + 200 * p.shield / 100, H - 52, fill="#3fa9ff", outline="")
        cv.create_rectangle(26, H - 44, 26 + 200 * clamp(p.hp, 0, 100) / 100, H - 28, fill="#2ee59d", outline="")
        cv.create_rectangle(26, H - 66, 226, H - 52, outline="#39405a")
        cv.create_rectangle(26, H - 44, 226, H - 28, outline="#39405a")
        cv.create_text(260, H - 59, text=int(p.shield), fill="#ffffff", font=font)
        cv.create_text(260, H - 36, text=int(clamp(p.hp, 0, 100)), fill="#ffffff", font=("Segoe UI", 13, "bold"))
        # slots
        for i in range(6):
            x0 = W - 16 - (6 - i) * 62
            s = p.slots[i - 1] if i else None
            sel = p.sel == i
            col = "#2b3048"
            if s and s["kind"] == "weapon":
                col = RARITY_COL[s["rarity"]]
            elif s and s["kind"] == "heal":
                col = RARITY_COL[HEALS[s["name"]][5]]
            cv.create_rectangle(x0, H - 72, x0 + 56, H - 16, fill="#141829", outline="#ffffff" if sel else col, width=3 if sel else 2)
            label = "Pickaxe" if i == 0 else (s["name"] if s else "")
            cv.create_text(x0 + 28, H - 44, text=label, fill="#e9ebf5", font=("Segoe UI", 8, "bold"), width=52)
            cv.create_text(x0 + 7, H - 64, text=str(i + 1), fill="#7a809c", font=("Segoe UI", 8))
            if s and s["kind"] == "heal":
                cv.create_text(x0 + 48, H - 24, text=s["n"], fill="#ffffff", font=("Segoe UI", 9, "bold"))
        w = p.current()
        if w and w["kind"] == "weapon":
            ammo = WEAPONS[w["name"]][7]
            txt = "RELOADING" if p.reload > 0 else f"{w['mag']} / {p.ammo[ammo]}"
            cv.create_text(W - 20, H - 92, text=txt, anchor="e", fill="#ffffff", font=("Segoe UI", 18, "bold"))
            cv.create_text(W - 20, H - 116, text=f"{w['rarity'].title()} {w['name']}", anchor="e", fill=RARITY_COL[w["rarity"]], font=font)
        elif w and w["kind"] == "heal":
            cv.create_text(W - 20, H - 92, text="USING..." if p.use > 0 else "Click to use", anchor="e", fill="#ffffff", font=font)
        cv.create_text(W - 20, H - 140, text=f"WOOD {p.wood}   [Q] build wall", anchor="e", fill="#e9ebf5", font=("Segoe UI", 9, "bold"))
        # minimap
        self.draw_map(g, p, W - 196, 16, 180, False)
        alive = sum(1 for f in g.fighters if f.alive)
        s = g.storm
        cv.create_text(W - 106, 210, text=f"{alive} ALIVE  •  {p.kills} ELIMS", fill="#ffffff", font=font)
        stxt = "Final circle" if s["phase"] >= len(STORM) else ("Storm closing " if s["shrink"] else "Storm shrinks in ") + \
            f"{int(s['timer']) // 60}:{int(s['timer']) % 60:02d}"
        cv.create_text(W - 106, 228, text=stxt, fill="#c9b8ff", font=("Segoe UI", 9))
        # feed
        for i, (_t, text, mine) in enumerate(reversed(g.feed)):
            cv.create_text(18, 20 + i * 20, text=text, anchor="w", fill="#ffc23d" if mine else "#ffffff", font=("Segoe UI", 9, "bold"))
        # prompt, messages
        if p.state == "ground":
            ch = g.near_chest(p)
            it = g.near_item(p)
            prompt = None
            if ch:
                prompt = "Hold E to open chest"
            elif it and it["kind"] in ("weapon", "heal"):
                prompt = f"E  pick up {it.get('rarity', '').title()} {it['name']}".replace("  ", " ")
            if prompt:
                cv.create_text(W / 2, H / 2 + 60, text=prompt, fill="#ffffff", font=font)
                if ch and p.open_t > 0:
                    cv.create_rectangle(W / 2 - 50, H / 2 + 74, W / 2 - 50 + 100 * p.open_t / 0.6, H / 2 + 79, fill="#ffc23d", outline="")
        if time.time() < self.msg_until:
            cv.create_text(W / 2, H * 0.2, text=self.msg, fill="#ffffff", font=("Segoe UI", 22, "bold"))
        if time.time() < self.note_until:
            cv.create_text(W / 2, H - 120, text=self.note, fill="#ffc23d", font=font)
        if p.state == "ship":
            cv.create_text(W / 2, H * 0.28, text="Press SPACE to jump", fill="#ffc23d", font=("Segoe UI", 14, "bold"))
        elif p.state == "glide":
            cv.create_text(W / 2, H * 0.28, text=f"Gliding - steer with WASD  ({p.glide:.1f}s)", fill="#ffc23d", font=font)
        if p.alive and g.in_storm(p.x, p.y):
            cv.create_text(W / 2, H * 0.34, text="YOU ARE IN THE STORM", fill="#d6b8ff", font=font)
        # crosshair / hit marker
        mx, my = self.mouse
        if p.state == "ground":
            cv.create_oval(mx - 10, my - 10, mx + 10, my + 10, outline="#ffffff")
            cv.create_line(mx - 3, my, mx + 3, my, fill="#ffffff")
            if time.time() < self.hit_until:
                cv.create_line(mx - 12, my - 12, mx + 12, my + 12, fill="#ff4d5e", width=3)
                cv.create_line(mx - 12, my + 12, mx + 12, my - 12, fill="#ff4d5e", width=3)
        if self.big_map:
            size = min(W, H) - 120
            self.draw_map(g, p, (W - size) / 2, (H - size) / 2, size, True)
        if self.state == "over":
            self.draw_over(g, p)

    def draw_map(self, g, p, x0, y0, size, big):
        cv = self.cv
        span = WORLD if big else 900
        cx, cy = (0, 0) if big else (p.x, p.y)
        k = size / span
        tx = lambda x: x0 + size / 2 + (x - cx) * k
        ty = lambda y: y0 + size / 2 + (y - cy) * k
        cv.create_rectangle(x0, y0, x0 + size, y0 + size, fill="#0b3550", outline="#3a4466", width=2)
        pts = []
        for a, r in g.island.shape:
            pts += [clamp(tx(math.cos(a) * r), x0, x0 + size), clamp(ty(math.sin(a) * r), y0, y0 + size)]
        cv.create_polygon(pts, fill="#5fa04a", outline="#e6d29b", width=2)
        s = g.storm
        cv.create_oval(tx(s["x"] - s["r"]), ty(s["y"] - s["r"]), tx(s["x"] + s["r"]), ty(s["y"] + s["r"]), outline="#b46cff", width=2)
        cv.create_oval(tx(s["tx"] - s["tr"]), ty(s["ty"] - s["tr"]), tx(s["tx"] + s["tr"]), ty(s["ty"] + s["tr"]), outline="#ffffff", dash=(4, 3))
        if big:
            for name, x, y in g.island.towns:
                cv.create_text(tx(x), ty(y), text=name, fill="#ffffff", font=("Segoe UI", 9, "bold"))
            cv.create_line(tx(g.ship_a[0]), ty(g.ship_a[1]), tx(g.ship_b[0]), ty(g.ship_b[1]), fill="#ffffff", dash=(3, 5))
        px, py = (g.ship_pos() if p.state == "ship" else (p.x, p.y))
        cv.create_oval(tx(px) - 5, ty(py) - 5, tx(px) + 5, ty(py) + 5, fill="#ffc23d", outline="#000000")
        # the map frame hides anything drawn outside it
        cv.create_rectangle(x0, y0, x0 + size, y0 + size, outline="#3a4466", width=2)

    def draw_over(self, g, p):
        cv, W, H = self.cv, self.w, self.h
        cv.create_rectangle(W / 2 - 260, H / 2 - 130, W / 2 + 260, H / 2 + 130, fill="#141829", outline="#6b3cf0", width=3)
        won = g.winner is p
        place = 1 if won else p.place
        cv.create_text(W / 2, H / 2 - 70, text="VICTORY ROYALE" if won else f"#{place}", fill="#ffc23d" if won else "#ffffff",
                       font=("Segoe UI", 34, "bold"))
        killer = p.killer.name if p.killer is not None else "the storm"
        sub = f"Last one standing out of {len(g.fighters)}" if won else f"Eliminated by {killer}  •  #{place} of {len(g.fighters)}"
        cv.create_text(W / 2, H / 2 - 20, text=sub, fill="#c3c7dc", font=("Segoe UI", 12))
        cv.create_text(W / 2, H / 2 + 20, text=f"{p.kills} eliminations   •   {p.damage} damage", fill="#ffffff", font=("Segoe UI", 13, "bold"))
        cv.create_text(W / 2, H / 2 + 75, text="Press ENTER or click to play again   •   ESC to quit", fill="#ffc23d", font=("Segoe UI", 11, "bold"))

    def draw_menu(self):
        cv, W, H = self.cv, self.w, self.h
        cv.create_rectangle(0, 0, W, H, fill="#0a0d1c", outline="")
        for i in range(40):
            x, y = (i * 137) % W, (i * 89) % H
            cv.create_oval(x, y, x + 3, y + 3, fill="#3a3f66", outline="")
        cv.create_text(W / 2 - 75, H * 0.26, text="X", anchor="e", fill="#ffffff", font=("Segoe UI", 80, "bold"))
        cv.create_text(W / 2 - 70, H * 0.26, text="GUN", anchor="w", fill="#00c2ff", font=("Segoe UI", 80, "bold"))
        cv.create_text(W / 2, H * 0.40, text="Battle royale  •  you vs 19 AI bots", fill="#a3a8c8", font=("Segoe UI", 14))
        lines = ["W A S D  move      Mouse  aim      Left click  shoot / use",
                 "Shift  sprint      R  reload      E  pick up / hold to open chests",
                 "1  pickaxe (chop trees for wood)      2-6  items      Q  build a wall",
                 "SPACE  jump out of the drop ship      M  map      ESC  quit"]
        for i, line in enumerate(lines):
            cv.create_text(W / 2, H * 0.52 + i * 26, text=line, fill="#e9ebf5", font=("Consolas", 12))
        cv.create_rectangle(W / 2 - 120, H * 0.78, W / 2 + 120, H * 0.78 + 56, fill="#ffc23d", outline="")
        cv.create_text(W / 2, H * 0.78 + 28, text="CLICK TO PLAY", fill="#1d1400", font=("Segoe UI", 18, "bold"))


def self_test(seconds=400):
    """Plays a whole match with bots only (no window) and prints a summary."""
    random.seed(7)
    g = Game(None)
    g.player.state = "dead"                          # spectator
    g.player.hp = 0
    steps = 0
    while not g.over and g.time < seconds:
        g.step(1 / 30, {})
        steps += 1
    alive = [f for f in g.fighters if f.alive]
    print(f"self-test: {g.time:.0f}s, over={g.over}, alive={len(alive)}, kills={sum(f.kills for f in g.fighters)}, "
          f"chests opened={sum(c['open'] for c in g.chests)}/{len(g.chests)}, walls built={sum(1 for w in g.island.walls if w[4] == 'build')}")
    return g


if __name__ == "__main__":
    if os.environ.get("XGUN_SELFTEST"):
        self_test()
    else:
        root = tk.Tk()
        root.geometry(f"{WIN_W}x{WIN_H}")
        App(root)
        root.mainloop()
