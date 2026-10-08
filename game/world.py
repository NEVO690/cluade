"""Endless procedural city.

The world is a queue of 40 m *chunks* generated just beyond the draw
distance and dropped as soon as they are behind the camera.  Each chunk owns
its buildings, decor, structures, obstacles and collectibles, so memory use
stays flat no matter how far you run.

Obstacles are generated in *rows*.  A guaranteed "safe lane" walks through
every row (it may only shift one lane at a time and never into a train),
and every hard blocker must have a reachable escape lane - so the generator
can never produce an impossible pattern.
"""
import math
import random
from collections import deque

from . import settings as S
from .collectibles import Collectible, COIN, GEM, TOKEN, POWERUP
from .obstacles import Obstacle, LOW, HIGH, BLOCK, TRAIN, RAMP, CAR
from .render import draw_poly
from .scenery import (Building, Decor, Structure, SpriteBank, random_ad, tree_color, zone_colors,
                      NEON_TEXTS, NEON_COLORS, STATION_NAMES)
from .utils import lerp, clamp, shade

ZONE_BLEND = 45.0
PASSABLE = {"empty", "low", "high", "ramp", "car", "mcar", "reserved"}
LATERAL_BLOCK = {"train", "train_front", "moving", "ramp"}
HARD_BLOCK = {"block", "train_front", "moving"}


class ZoneSchedule:
    """Sequence of zones along z.  Zones rotate through the unlocked set."""

    def __init__(self, zones, unlocked_ids, rnd):
        self.zones = [z for z in zones if z["id"] in unlocked_ids] or [zones[0]]
        self.rnd = rnd
        self.segments = []
        self._bag = []
        self._append(self.zones[0], 0.0)

    def _append(self, zone, start):
        lo, hi = zone["length"]
        self.segments.append((start, start + self.rnd.uniform(lo, max(lo, hi)), zone))

    def _next_zone(self, prev):
        if len(self.zones) == 1:
            return self.zones[0]
        if not self._bag:
            self._bag = [z for z in self.zones if z is not prev]
            self.rnd.shuffle(self._bag)
        return self._bag.pop()

    def ensure(self, z):
        while self.segments[-1][1] < z:
            self._append(self._next_zone(self.segments[-1][2]), self.segments[-1][1])
        # forget segments far behind
        while len(self.segments) > 3 and self.segments[1][1] < z - 2000:
            self.segments.pop(0)

    def index_at(self, z):
        for i in range(len(self.segments) - 1, -1, -1):
            if self.segments[i][0] <= z:
                return i
        return 0

    def zone_at(self, z):
        """Return (zone, next_zone_or_None, blend 0..1)."""
        self.ensure(z + ZONE_BLEND * 2)
        i = self.index_at(z)
        start, end, zone = self.segments[i]
        if z > end - ZONE_BLEND and i + 1 < len(self.segments):
            t = (z - (end - ZONE_BLEND)) / ZONE_BLEND
            return zone, self.segments[i + 1][2], clamp(t, 0.0, 1.0)
        return zone, None, 0.0

    def zone_id_at(self, z):
        zone, nxt, t = self.zone_at(z)
        return nxt["id"] if nxt is not None and t > 0.5 else zone["id"]


class Chunk:
    __slots__ = ("index", "z0", "z1", "max_z", "zone", "tunnel", "buildings", "decor", "structures",
                 "obstacles", "collectibles")

    def __init__(self, index, z0, z1, zone):
        self.index = index
        self.z0 = z0
        self.z1 = z1
        self.max_z = z1
        self.zone = zone
        self.tunnel = False
        self.buildings = []
        self.decor = []
        self.structures = []
        self.obstacles = []
        self.collectibles = []


def default_speed(z):
    return S.START_SPEED + (S.MAX_SPEED - S.START_SPEED) * (1 - math.exp(-max(0.0, z) / S.SPEED_RAMP_DISTANCE))


class World:
    def __init__(self, gamedata, quality, unlocked_zone_ids, assets, event=None, seed=None,
                 spawn_obstacles=True, speed_fn=None, sprites=None):
        self.gamedata = gamedata
        self.quality = quality
        self.rnd = random.Random(seed)
        self.schedule = ZoneSchedule(gamedata.zones, unlocked_zone_ids, self.rnd)
        self.event = event
        self.spawn_obstacles = spawn_obstacles
        self.speed_fn = speed_fn or default_speed
        self.sprites = sprites or SpriteBank(assets)
        self.chunks = deque()
        self.next_chunk_index = 0
        self.movers = []
        self.sky_coins = []
        self.sky_next_z = 0.0
        self.sky_lane = 1
        self.player_z = 0.0
        # row generator state
        self.next_row_z = S.START_SAFE_DISTANCE
        self.prev_cells = ["empty"] * 3
        self.safe_lane = 1
        self.lane_block_until = [0.0, 0.0, 0.0]
        self.lane_reserved_until = [0.0, 0.0, 0.0]
        self.lane_block_kind = ["train"] * 3
        # scenery state
        self.building_cursor = {-1: 0.0, 1: 0.0}
        self.tunnel_until = 0.0
        self.station_until = 0.0
        self.next_lamp_z = 6.0
        self.powerups = [(p["id"], p["spawn_weight"]) for p in gamedata.powerups if p["spawn_weight"] > 0]
        self.rows_generated = 0

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def difficulty(self, z):
        return clamp((z - 100.0) / 5500.0, 0.0, 1.0)

    def update(self, dt, player_z, cam_z, draw_distance, move_movers=True):
        self.player_z = player_z
        horizon = cam_z + draw_distance + S.CHUNK_LENGTH
        self.schedule.ensure(horizon + 400)
        while self.next_chunk_index * S.CHUNK_LENGTH < horizon:
            self._generate_chunk()
        while self.chunks and self.chunks[0].max_z < cam_z - 4:
            self.chunks.popleft()
        if move_movers:
            for m in self.movers:
                m.update(dt)
        if self.movers:
            self.movers = [m for m in self.movers if m.z1 > cam_z - 5 and m.alive]
        if self.sky_coins:
            self.sky_coins = [c for c in self.sky_coins if c.alive and c.z > cam_z]

    def _generate_chunk(self):
        idx = self.next_chunk_index
        self.next_chunk_index += 1
        z0 = idx * S.CHUNK_LENGTH
        z1 = z0 + S.CHUNK_LENGTH
        zone, _, _ = self.schedule.zone_at(z0 + S.CHUNK_LENGTH / 2)
        ch = Chunk(idx, z0, z1, zone)
        rnd = self.rnd
        # --- structures -------------------------------------------------
        if z0 < self.tunnel_until:
            ch.tunnel = True
        elif z0 > 150 and zone.get("tunnels", 0) > 0 and rnd.random() < zone["tunnels"] * 0.45:
            length = rnd.choice([80.0, 120.0, 160.0])
            self.tunnel_until = z0 + length
            ch.tunnel = True
            ch.structures.append(Structure("tunnel", z0, z0 + length,
                                           {"portal": True, "name": rnd.choice(STATION_NAMES) + " TUNNEL"}))
        station = False
        if not ch.tunnel:
            if zone.get("stations") and (z0 < self.station_until or (z0 > 60 and rnd.random() < 0.3)):
                if z0 >= self.station_until:
                    self.station_until = z0 + S.CHUNK_LENGTH * rnd.choice([1, 2])
                    ch.structures.append(Structure("station", z0, self.station_until, {"name": rnd.choice(STATION_NAMES)}))
                station = True
            if rnd.random() < zone.get("bridges", 0) * 0.35 and not station:
                zb = z0 + rnd.uniform(5, 30)
                ch.structures.append(Structure("bridge", zb, zb + 5.0,
                                               {"color": rnd.choice([(150, 150, 160), (120, 110, 100), (90, 100, 120)]),
                                                "name": rnd.choice(["CITY LINE", "EXPRESSWAY", "RIVER RD", "SKY LOOP", "HARBOR WAY"])}))
            elif rnd.random() < 0.12:
                ch.structures.append(Structure("gantry", z0 + rnd.uniform(5, 35), 0,
                                               {"states": [rnd.randint(0, 1) for _ in range(3)]}))
                ch.structures[-1].z1 = ch.structures[-1].z0 + 0.4
        # --- buildings ---------------------------------------------------
        b = zone["buildings"]
        for side in (-1, 1):
            cursor = max(self.building_cursor[side], z0)
            water_side = (zone.get("water") == "right" and side > 0) or (zone.get("water") == "left" and side < 0)
            while cursor < z1:
                if ch.tunnel:
                    cursor = z1
                    break
                w = rnd.uniform(*b["width"]) if b["width"][0] < b["width"][1] else b["width"][0]
                if water_side:
                    cursor += w
                    continue
                gap = rnd.uniform(0.5, 4.0)
                inner = S.SIDEWALK_HALF + (2.8 if station else 2.0) + rnd.uniform(0, 1.5)
                depth = rnd.uniform(*b["depth"])
                x0, x1 = (inner, inner + depth) if side > 0 else (-inner - depth, -inner)
                h = rnd.uniform(*b["height"])
                ch.buildings.append(Building(side, x0, x1, cursor, cursor + w, h, rnd.choice(b["palette"]),
                                             b["style"], zone, rnd))
                cursor += w + gap
            self.building_cursor[side] = cursor
        # --- decor --------------------------------------------------------
        if not ch.tunnel and not station:
            self._generate_decor(ch, zone)
        # --- obstacles & collectibles -------------------------------------
        if self.spawn_obstacles:
            while self.next_row_z < z1:
                self._generate_row(self.next_row_z, ch)
        self.chunks.append(ch)

    def _generate_decor(self, ch, zone):
        rnd = self.rnd
        dens = self.quality.get("decor_density", 1.0)
        decor = zone.get("decor", {})
        sx = S.SIDEWALK_HALF - 0.7
        # street lamps at a regular rhythm
        if decor.get("lamp", 0) > 0:
            while self.next_lamp_z < ch.z1:
                z = self.next_lamp_z
                if z >= ch.z0:
                    for side in (-1, 1):
                        if zone.get("water") == "right" and side > 0:
                            continue
                        ch.decor.append(Decor("lamp", side * sx, z + (0 if side < 0 else 10)))
                self.next_lamp_z += 20.0 / max(0.4, decor["lamp"] * 1.2)
        else:
            self.next_lamp_z = ch.z1
        z = ch.z0 + rnd.uniform(1, 5)
        while z < ch.z1:
            side = rnd.choice((-1, 1))
            x = side * (sx - 0.4)
            water = zone.get("water") == "right" and side > 0
            r = rnd.random()
            if self.event and rnd.random() < 0.22:
                kind = self.event["theme"].get("decor", "")
                if kind == "flags":
                    ch.decor.append(Decor("flags", 0.0, z))
                elif kind:
                    ch.decor.append(Decor(kind, x, z))
            elif water:
                if rnd.random() < decor.get("bollard", 0) * dens:
                    ch.decor.append(Decor("bollard", side * (S.SIDEWALK_HALF - 0.3), z))
            else:
                choices = [(k, v) for k, v in decor.items() if k not in ("lamp",) and v > 0]
                total = sum(v for _, v in choices)
                if choices and r < min(0.95, total * 0.5) * dens:
                    pick = rnd.uniform(0, total)
                    kind = choices[-1][0]
                    for k, v in choices:
                        pick -= v
                        if pick <= 0:
                            kind = k
                            break
                    if kind == "tree":
                        ch.decor.append(Decor("tree", x, z, tree_color(zone)))
                    elif kind == "billboard":
                        ch.decor.append(Decor("billboard", side * (S.SIDEWALK_HALF - 0.4), z, random_ad(rnd)))
                    elif kind == "neon_sign":
                        ch.decor.append(Decor("neon_sign", side * (S.SIDEWALK_HALF + 0.4), z,
                                              (rnd.choice(NEON_TEXTS), rnd.choice(NEON_COLORS))))
                    elif kind == "chimney":
                        ch.decor.append(Decor("chimney", side * (S.SIDEWALK_HALF + 26 + rnd.uniform(0, 10)), z))
                    elif kind == "crane":
                        ch.decor.append(Decor("crane", side * (S.SIDEWALK_HALF + 18), z))
                    elif kind in ("bench", "barrels", "bollard"):
                        ch.decor.append(Decor(kind, x, z))
            z += rnd.uniform(6, 12)

    # ------------------------------------------------------------------
    def _pick_kind(self, weights, d):
        w = dict(weights)
        if d < 0.1:
            w["moving_train"] = 0
        if d < 0.05:
            w["moving_car"] = 0
        # trains become more common as difficulty grows
        w["train"] = w.get("train", 0) * (0.6 + d)
        w["block"] = w.get("block", 0) * (0.7 + d * 0.6)
        total = sum(max(0, v) for v in w.values())
        if total <= 0:
            return "low"
        pick = self.rnd.uniform(0, total)
        for k, v in w.items():
            pick -= max(0, v)
            if pick <= 0:
                return k
        return "low"

    def _generate_row(self, z, ch):
        rnd = self.rnd
        self.rows_generated += 1
        d = self.difficulty(z)
        zone, _, _ = self.schedule.zone_at(z)
        style = zone.get("obstacle_style", "downtown")
        speed = self.speed_fn(z)
        spacing = max(speed * 0.62, lerp(32.0, 17.0, d) + rnd.uniform(-2.0, 6.0), 13.0)

        cells = [None, None, None]
        for lane in range(3):
            if self.lane_block_until[lane] > z:
                cells[lane] = "train"
            elif self.lane_reserved_until[lane] > z:
                cells[lane] = "reserved"

        # --- move the guaranteed safe lane ---------------------------------
        options = []
        for l in (self.safe_lane - 1, self.safe_lane, self.safe_lane + 1):
            if 0 <= l < 3 and cells[l] is None:
                if l != self.safe_lane and self.prev_cells[l] in LATERAL_BLOCK:
                    continue
                options.append(l)
        if not options:
            options = [l for l in range(3) if cells[l] is None] or [self.safe_lane]
        if self.safe_lane in options and rnd.random() < 0.6:
            safe = self.safe_lane
        else:
            safe = rnd.choice(options)
        self.safe_lane = safe

        w = zone.get("obstacles", {})
        if cells[safe] is None:
            r = rnd.random()
            if r < lerp(0.6, 0.35, d):
                cells[safe] = "empty"
            else:
                cells[safe] = "low" if rnd.random() < (w.get("low", 1) / max(1, w.get("low", 1) + w.get("high", 1))) else "high"

        for lane in range(3):
            if cells[lane] is not None:
                continue
            if rnd.random() < lerp(0.55, 0.2, d):
                cells[lane] = "empty"
                continue
            k = self._pick_kind(w, d)
            if k == "train":
                cells[lane] = "ramp" if rnd.random() < 0.5 else "train_front"
            elif k == "moving_train":
                cells[lane] = "moving"
            elif k == "moving_car":
                cells[lane] = "mcar"
            else:
                cells[lane] = k  # low / high / block / car

        # --- escape rule: every hard blocker needs a reachable open neighbour
        for lane in range(3):
            if cells[lane] in HARD_BLOCK:
                ok = False
                for adj in (lane - 1, lane + 1):
                    if 0 <= adj < 3 and cells[adj] in PASSABLE and self.prev_cells[adj] not in LATERAL_BLOCK:
                        ok = True
                if not ok:
                    cells[lane] = "low"
        # never three low/high obstacles at once early on
        if d < 0.2 and all(c in ("low", "high") for c in cells):
            cells[(safe + 1) % 3] = "empty"

        # --- instantiate obstacles ----------------------------------------
        def add(ob, mover=False):
            if mover:
                self.movers.append(ob)
            else:
                ch.obstacles.append(ob)
                ch.max_z = max(ch.max_z, ob.z1)

        variant = rnd.randrange(12)
        ramp_lanes = []
        for lane, cell in enumerate(cells):
            if cell == "low":
                add(Obstacle(LOW, lane, z, style=style))
            elif cell == "high":
                add(Obstacle(HIGH, lane, z, style=style))
            elif cell == "block":
                add(Obstacle(BLOCK, lane, z, style=style))
            elif cell == "car":
                add(Obstacle(CAR, lane, z, style=style, variant=rnd.randrange(12)))
            elif cell in ("ramp", "train_front"):
                length = rnd.choice([18.0, 24.0, 24.0, 30.0, 36.0])
                tz = z
                if cell == "ramp":
                    ramp = Obstacle(RAMP, lane, z, style=style)
                    add(ramp)
                    tz = ramp.z1
                    ramp_lanes.append((lane, tz, length))
                tr = Obstacle(TRAIN, lane, tz, length=length, style=style, variant=variant + lane)
                tr.has_ramp = cell == "ramp"
                add(tr)
                self.lane_block_until[lane] = tz + length + 3.0
            elif cell in ("moving", "mcar"):
                is_train = cell == "moving"
                vt = rnd.uniform(7.0, 11.0) if is_train else rnd.uniform(3.0, 5.0)
                length = rnd.choice([18.0, 24.0]) if is_train else None
                dist = max(10.0, z - self.player_z)
                spawn = z + dist * vt / max(1.0, speed)
                ob = Obstacle(TRAIN if is_train else CAR, lane, spawn, length=length, vel=-vt, style=style,
                              variant=rnd.randrange(12))
                add(ob, mover=True)
                body = ob.z1 - ob.z0
                eff = body * speed / (speed + vt) + 4.0
                self.lane_block_until[lane] = z + eff
                self.lane_reserved_until[lane] = ob.z1 + 6.0

        # --- collectibles ----------------------------------------------------
        coin_lane = safe
        cz = []
        if rnd.random() < 0.8:
            cell = cells[coin_lane]
            x = S.LANE_X[coin_lane]
            if cell == "low":
                for k in range(-2, 3):
                    zz = z + k * 2.4
                    y = 0.9 + 1.25 * (1 - (k / 2.6) ** 2)
                    cz.append((x, y, zz))
            elif cell == "high":
                cz.append((x, 0.55, z))
            n = int((spacing - 6) / 2.6)
            for k in range(n):
                cz.append((x, 0.9, z + 4 + k * 2.6))
        for lane, tz, length in ramp_lanes:
            if rnd.random() < 0.65:
                x = S.LANE_X[lane]
                zz = tz - 5
                while zz < tz + length - 1:
                    h = 3.3 if zz >= tz else 3.3 * (zz - (tz - 7)) / 7
                    cz.append((x, h + 0.9, zz))
                    zz += 2.6
        for x, y, zz in cz:
            ch.collectibles.append(Collectible(COIN, x, y, zz))

        free = [l for l in range(3) if cells[l] in ("empty", "low", "high")]
        mid = z + spacing * 0.5
        if free and self.powerups and rnd.random() < 0.05 + 0.02 * d:
            lane = rnd.choice(free)
            pid = self._weighted(self.powerups)
            self._remove_coins_near(ch, S.LANE_X[lane], mid, 1.6)
            ch.collectibles.append(Collectible(POWERUP, S.LANE_X[lane], 1.2, mid, pid))
        elif free and rnd.random() < 0.012 + 0.006 * d:
            lane = rnd.choice(free)
            self._remove_coins_near(ch, S.LANE_X[lane], mid, 1.6)
            ch.collectibles.append(Collectible(GEM, S.LANE_X[lane], 1.0, mid))
        if self.event and free and rnd.random() < self.event["currency"]["spawn_chance"]:
            lane = rnd.choice(free)
            tz = z + spacing * 0.3
            self._remove_coins_near(ch, S.LANE_X[lane], tz, 1.6)
            ch.collectibles.append(Collectible(TOKEN, S.LANE_X[lane], 1.0, tz))

        # remember what the player faces at this row (trains continue as "train")
        self.prev_cells = ["train" if c in ("ramp", "train_front", "moving") else c for c in cells]
        self.next_row_z = z + spacing

    def _weighted(self, pairs):
        total = sum(w for _, w in pairs)
        pick = self.rnd.uniform(0, total)
        for pid, w in pairs:
            pick -= w
            if pick <= 0:
                return pid
        return pairs[-1][0]

    @staticmethod
    def _remove_coins_near(ch, x, z, radius):
        ch.collectibles = [c for c in ch.collectibles if not (abs(c.x - x) < 0.5 and abs(c.z - z) < radius)]

    # ------------------------------------------------------------------
    # Sky coins (Jet Boost)
    # ------------------------------------------------------------------
    def spawn_sky_coins(self, player, remaining):
        height = player.flight_height + 0.9
        start = max(self.sky_next_z, player.z + 14)
        end = player.z + min(remaining * self.speed_fn(player.z), 150)
        while start < end:
            if int(start / 36) != int((start - 2.6) / 36) and self.rnd.random() < 0.6:
                self.sky_lane = clamp(self.sky_lane + self.rnd.choice((-1, 1)), 0, 2)
            self.sky_coins.append(Collectible(COIN, S.LANE_X[self.sky_lane], height, start))
            start += 2.6
        self.sky_next_z = start

    def clear_sky_coins_after(self, z):
        self.sky_coins = [c for c in self.sky_coins if c.z < z]
        self.sky_next_z = 0.0

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def obstacles_near(self, z0, z1):
        for ch in self.chunks:
            if ch.z0 > z1 + 1:
                break
            if ch.max_z < z0:
                continue
            for ob in ch.obstacles:
                if ob.alive and ob.z1 >= z0 and ob.z0 <= z1:
                    yield ob
        for ob in self.movers:
            if ob.alive and ob.z1 >= z0 and ob.z0 <= z1:
                yield ob

    def collectibles_near(self, z0, z1):
        for ch in self.chunks:
            if ch.z0 > z1 + 40:
                break
            if ch.z1 + 40 < z0:
                continue
            for c in ch.collectibles:
                if c.alive and z0 <= c.z <= z1:
                    yield c
        for c in self.sky_coins:
            if c.alive and z0 <= c.z <= z1:
                yield c

    def ground_height(self, x, z, prev_feet):
        """Highest walkable surface under (x, z) that the feet can stand on."""
        best = 0.0
        surface = None
        for ob in self.obstacles_near(z - 0.1, z + 0.1):
            if not ob.walkable or abs(ob.x - x) > S.LANE_HALF:
                continue
            if ob.z0 <= z <= ob.z1:
                top = ob.top_at(z)
                if top > best and top <= prev_feet + S.STEP_HEIGHT:
                    best = top
                    surface = ob
        return best, surface

    def clear_ahead(self, z, ahead=40.0, behind=6.0):
        """Remove obstacles around z (used when reviving)."""
        for ob in list(self.obstacles_near(z - behind, z + ahead)):
            ob.alive = False
        for ob in self.movers:
            if ob.z0 < z + ahead + 60:
                ob.alive = False

    def chunk_index_at(self, z):
        return int(z // S.CHUNK_LENGTH)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, r, crender, cam_z):
        q = self.quality
        far = cam_z + r.draw_distance
        for ch in self.chunks:
            if ch.z0 > far:
                break
            if ch.max_z < cam_z:
                continue
            night = ch.zone.get("night", False)
            for b in ch.buildings:
                b.queue(r, q, night)
            for d in ch.decor:
                d.queue(r, self.sprites, night, ch.zone)
            for s in ch.structures:
                s.queue(r, self.sprites, night, ch.zone)
            for ob in ch.obstacles:
                ob.queue_draw(r, q, night)
            for c in ch.collectibles:
                crender.queue(r, c)
        zone_now, _, _ = self.schedule.zone_at(cam_z + 20)
        for ob in self.movers:
            ob.queue_draw(r, q, zone_now.get("night", False))
        for c in self.sky_coins:
            crender.queue(r, c)

    def in_tunnel(self, z):
        for ch in self.chunks:
            if ch.z0 <= z < ch.z1:
                return ch.tunnel
        return False

    def draw_ground(self, r, cam):
        surf = r.surface
        seg = self.quality.get("segment", 6.0)
        zn = cam.z + S.NEAR_PLANE
        zfar = cam.z + r.draw_distance
        F, hx, hy, cx, cy = cam.focal, cam.hx, cam.hy, cam.x, cam.y
        W = surf.get_width()
        za0, zb0, t0 = self.schedule.zone_at(zfar)
        fog_far = zone_colors(za0, zb0, t0)["fog"]
        horizon_y = int(hy + cy * F / (zfar - cam.z)) - 1
        surf.fill(fog_far, (0, int(hy) - 2, W, max(0, horizon_y - int(hy) + 4)))
        poly = draw_poly
        fog = r.fog
        tunnel_ranges = [(ch.z0, ch.z1) for ch in self.chunks if ch.tunnel]

        def X(x, s):
            return hx + (x - cx) * s

        z = math.floor(zn / seg) * seg
        rail_offsets = (-0.72, 0.72)
        ties = self.quality.get("ties", True)
        while z < zfar:
            za = max(z, zn)
            zb = min(z + seg, zfar)
            if zb <= za:
                z += seg
                continue
            da = za - cam.z
            db = zb - cam.z
            sa = F / da
            sb = F / db
            ya = hy + cy * sa
            yb = hy + cy * sb
            dm = (da + db) * 0.5
            zone_a, zone_b, t = self.schedule.zone_at((za + zb) * 0.5)
            col = zone_colors(zone_a, zone_b, t)
            stripe = int(z / seg) % 2 == 0
            k = 1.0 if stripe else 0.93
            in_tun = any(a <= za < b for a, b in tunnel_ranges)
            if in_tun:
                k *= 0.55
            ground = fog(shade(col["ground"], k), dm)
            surf.fill(ground, (0, yb, W, ya - yb + 1.5))
            water = zone_a.get("water") if t < 0.5 else (zone_b or zone_a).get("water")
            if water and not in_tun:
                wc = zone_a.get("water_color") or (40, 110, 170)
                wcol = fog(shade(wc, 1.0 if stripe else 0.94), dm)
                if water == "right":
                    poly(surf, wcol, ((X(S.SIDEWALK_HALF + 1.5, sa), ya), (W + 5, ya), (W + 5, yb), (X(S.SIDEWALK_HALF + 1.5, sb), yb)))
                else:
                    poly(surf, wcol, ((-5, ya), (X(-S.SIDEWALK_HALF - 1.5, sa), ya), (X(-S.SIDEWALK_HALF - 1.5, sb), yb), (-5, yb)))
            sw = fog(shade(col["sidewalk"], k), dm)
            poly(surf, sw, ((X(-S.SIDEWALK_HALF, sa), ya), (X(S.SIDEWALK_HALF, sa), ya),
                            (X(S.SIDEWALK_HALF, sb), yb), (X(-S.SIDEWALK_HALF, sb), yb)))
            road = fog(shade(col["road"], k), dm)
            poly(surf, road, ((X(-S.ROAD_HALF, sa), ya), (X(S.ROAD_HALF, sa), ya),
                              (X(S.ROAD_HALF, sb), yb), (X(-S.ROAD_HALF, sb), yb)))
            # sleepers
            if ties and da < 60:
                tie = fog(shade(col["ties"], 0.6 if in_tun else 1.0), dm)
                tz = math.ceil(za / 1.6) * 1.6
                while tz < zb:
                    ta = tz - cam.z
                    tb = ta + 0.4
                    s1 = F / ta
                    s2 = F / tb
                    y1 = hy + cy * s1
                    y2 = hy + cy * s2
                    for lx in S.LANE_X:
                        poly(surf, tie, ((X(lx - 1.0, s1), y1), (X(lx + 1.0, s1), y1), (X(lx + 1.0, s2), y2), (X(lx - 1.0, s2), y2)))
                    tz += 1.6
            z += seg
        # rails: long strips (a few fog steps) drawn on top of the ground segments
        rz = zn
        step = 18.0
        while rz < zfar:
            za, zb = rz, min(rz + step, zfar)
            da, db = za - cam.z, zb - cam.z
            sa, sb = F / da, F / db
            ya, yb = hy + cy * sa, hy + cy * sb
            zone_a, zone_b, t = self.schedule.zone_at((za + zb) * 0.5)
            rail = fog(zone_colors(zone_a, zone_b, t)["rail"], (da + db) * 0.5)
            for lx in S.LANE_X:
                for off in rail_offsets:
                    x0 = lx + off - 0.05
                    x1 = lx + off + 0.05
                    poly(surf, rail, ((X(x0, sa), ya), (X(x1, sa), ya), (X(x1, sb), yb), (X(x0, sb), yb)))
            rz += step
            step *= 1.6
