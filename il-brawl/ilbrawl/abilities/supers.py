"""Super abilities. Each handler receives (world, brawler, target_x, target_y, spec)."""
import math
import random

from ilbrawl.combat import attacks
from ilbrawl.combat import damage as dmg
from ilbrawl.config import TILE
from ilbrawl.gameplay.entities import AreaEffect, Deployable, Projectile


def clamp_target(b, tx, ty, max_tiles):
    dx, dy = tx - b.x, ty - b.y
    d = math.hypot(dx, dy)
    rng = max_tiles * TILE
    if d > rng and d > 0:
        return b.x + dx / d * rng, b.y + dy / d * rng
    return tx, ty


def _snipe(world, b, tx, ty, s):
    a = math.atan2(ty - b.y, tx - b.x)
    spec = dict(s, type="single", pierce=True, shape="beam")
    world.add_projectile(Projectile(b, b.x, b.y, a, spec, s["damage"] * b.level_mult, True))
    world.emit("shot", x=b.x, y=b.y, angle=a, who=b, sound="laser", color=s.get("color"))


def _dash(world, b, tx, ty, s):
    a = math.atan2(ty - b.y, tx - b.x)
    b.dash = {"dx": math.cos(a), "dy": math.sin(a), "left": s.get("distance", 5) * TILE, "speed": 820,
              "damage": s["damage"] * b.level_mult, "knock": s.get("knockback", 300), "hit": set()}
    b.facing = a
    world.emit("dash", x=b.x, y=b.y, who=b)


def _heal_zone(world, b, tx, ty, s):
    tx, ty = clamp_target(b, tx, ty, s.get("range", 7))
    world.add_area(AreaEffect("heal_zone", b, tx, ty, s["radius"] * TILE, s["duration"], s))


def _blink(world, b, tx, ty, s):
    tx, ty = clamp_target(b, tx, ty, s.get("range", 5))
    tx, ty = world.map.free_point_near(tx, ty)
    ox, oy = b.x, b.y
    b.x, b.y = world.map.resolve_circle(tx, ty, b.radius)
    world.emit("blink", x0=ox, y0=oy, x=b.x, y=b.y, who=b, color=s.get("color"))
    r = s.get("radius", 1.8) * TILE
    for t in world.damageable_enemies(b.team):
        if math.hypot(t.x - b.x, t.y - b.y) <= r + t.radius:
            dmg.apply_damage(world, b, t, s["damage"] * b.level_mult)
    world.emit("explosion", x=b.x, y=b.y, radius=r, color=s.get("color", (255, 90, 160)), small=True)


def _meteor(world, b, tx, ty, s):
    spec = dict(s, type="lob", speed=520, radius=20, shape="meteor")
    attacks.fire_lob(world, b, tx, ty, spec, s["damage"] * b.level_mult, True, 0.0)


def _slow_field(world, b, tx, ty, s):
    tx, ty = clamp_target(b, tx, ty, s.get("range", 8))
    world.add_area(AreaEffect("slow_field", b, tx, ty, s["radius"] * TILE, s["duration"], s))


def _turret(world, b, tx, ty, s, kind="turret"):
    tx, ty = clamp_target(b, tx, ty, s.get("range", 3))
    tx, ty = world.map.free_point_near(tx, ty)
    tx, ty = world.map.resolve_circle(tx, ty, 18)
    d = Deployable(kind, b, tx, ty, s)
    world.add_deployable(d)


def _heal_totem(world, b, tx, ty, s):
    _turret(world, b, tx, ty, s, "totem")


def _decoy(world, b, tx, ty, s):
    _turret(world, b, tx, ty, s, "decoy")
    b.invis_t = 1.5
    b.invis_speed = 1.15


def _nova_ring(world, b, tx, ty, s):
    n = s.get("count", 16)
    spec = dict(s, type="single", pierce=True, shape="flame")
    for i in range(n):
        a = i * 2 * math.pi / n
        world.add_projectile(Projectile(b, b.x, b.y, a, spec, s["damage"] * b.level_mult, True))
    world.emit("explosion", x=b.x, y=b.y, radius=TILE * 1.5, color=s.get("color"), small=True)


def _stealth(world, b, tx, ty, s):
    b.invis_t = s.get("duration", 4)
    b.invis_speed = s.get("speed_mult", 1.3)
    dmg.apply_heal(world, b, b, s.get("heal", 0) * b.level_mult)


def _shield_aura(world, b, tx, ty, s):
    r = s.get("radius", 3.5) * TILE
    for ally in world.brawlers:
        if ally.alive and ally.team == b.team and math.hypot(ally.x - b.x, ally.y - b.y) <= r:
            ally.shield_t = s.get("duration", 4)
            ally.shield_amt = s.get("reduction", 0.5)
            dmg.apply_heal(world, b, ally, s.get("heal", 0) * b.level_mult)
    world.emit("ring", x=b.x, y=b.y, radius=r, color=s.get("color"))


def _pull(world, b, tx, ty, s):
    tx, ty = clamp_target(b, tx, ty, s.get("range", 7))
    world.add_area(AreaEffect("pull", b, tx, ty, s["radius"] * TILE, s["duration"], s))


def _stun_wave(world, b, tx, ty, s):
    a = math.atan2(ty - b.y, tx - b.x)
    spec = dict(s, type="wave", pierce=True, shape="shock")
    world.add_projectile(Projectile(b, b.x, b.y, a, spec, s["damage"] * b.level_mult, True))
    world.emit("shot", x=b.x, y=b.y, angle=a, who=b, sound="whoosh", color=s.get("color"))


def _rain(world, b, tx, ty, s):
    tx, ty = clamp_target(b, tx, ty, s.get("range", 9))
    world.add_area(AreaEffect("rain", b, tx, ty, s.get("spread", 2.4) * TILE, s.get("duration", 1.2), s))


def _rage(world, b, tx, ty, s):
    b.rage_t = s.get("duration", 5)
    b.rage = s
    b.ammo = float(b.ammo_max)


def _wall(world, b, tx, ty, s):
    tx, ty = clamp_target(b, tx, ty, s.get("range", 6))
    a = math.atan2(ty - b.y, tx - b.x)
    px, py = -math.sin(a), math.cos(a)  # perpendicular
    n = s.get("length", 5)
    occupied = {world.map.to_tile(o.x, o.y) for o in world.brawlers if o.alive}
    placed = 0
    for i in range(n):
        off = (i - (n - 1) / 2) * TILE
        cx, cy = world.map.to_tile(tx + px * off, ty + py * off)
        if (cx, cy) in occupied:
            continue
        if world.map.add_temp_wall(cx, cy, s.get("duration", 8)):
            placed += 1
    world.emit("wall", x=tx, y=ty, who=b)


HANDLERS = {
    "snipe": _snipe, "dash": _dash, "heal_zone": _heal_zone, "blink": _blink, "meteor": _meteor,
    "slow_field": _slow_field, "turret": _turret, "heal_totem": _heal_totem, "decoy": _decoy,
    "nova_ring": _nova_ring, "stealth": _stealth, "shield_aura": _shield_aura, "pull": _pull,
    "stun_wave": _stun_wave, "rain": _rain, "rage": _rage, "wall": _wall,
}


def activate(world, b, tx, ty):
    if not b.alive or not b.super_ready or b.stun_t > 0 or b.dash is not None:
        return False
    s = b.sup
    h = HANDLERS.get(s["type"])
    if h is None:
        return False
    b.super_charge = 0.0
    b.stats.supers += 1
    b.since_attack = 0.0
    b.reveal_t = max(b.reveal_t, 0.8)
    b.facing = math.atan2(ty - b.y, tx - b.x)
    h(world, b, tx, ty, s)
    world.emit("super", x=b.x, y=b.y, who=b, stype=s["type"])
    return True


def super_range_tiles(sdef):
    """Approximate effective range used by aiming indicators and AI."""
    t = sdef["type"]
    if t in ("dash",):
        return sdef.get("distance", 5)
    if t in ("shield_aura", "nova_ring", "stealth", "rage"):
        return sdef.get("radius", sdef.get("range", 4)) if t != "rage" else 6
    return sdef.get("range", 6)


def update_area(world, a, dt):
    """Tick an area effect created by a super."""
    s = a.spec
    a.left -= dt
    a.timer += dt
    owner = a.owner
    if a.kind == "heal_zone":
        for ally in world.brawlers:
            if ally.alive and ally.team == a.team and math.hypot(ally.x - a.x, ally.y - a.y) <= a.radius:
                dmg.apply_heal(world, owner, ally, s["heal_per_sec"] * owner.level_mult * dt)
    elif a.kind == "slow_field":
        for t in world.damageable_enemies(a.team):
            if math.hypot(t.x - a.x, t.y - a.y) <= a.radius:
                if hasattr(t, "slow_t"):
                    t.slow_t = max(t.slow_t, 0.25)
                    t.slow_amt = max(t.slow_amt, s.get("slow", 0.5))
                dmg.apply_damage(world, owner, t, s.get("dps", 200) * owner.level_mult * dt)
    elif a.kind == "pull":
        for t in world.damageable_enemies(a.team):
            if not hasattr(t, "kx"):
                continue
            dx, dy = a.x - t.x, a.y - t.y
            d = math.hypot(dx, dy)
            if d <= a.radius + 10 and d > 4:
                step = min(d, s.get("pull", 250) * dt)
                nx, ny = t.x + dx / d * step, t.y + dy / d * step
                t.x, t.y = world.map.resolve_circle(nx, ny, t.radius)
                dmg.apply_damage(world, owner, t, s.get("dps", 200) * owner.level_mult * dt)
        if a.left <= 0:
            for t in world.damageable_enemies(a.team):
                if math.hypot(t.x - a.x, t.y - a.y) <= a.radius + t.radius:
                    dmg.apply_damage(world, owner, t, s.get("final_damage", 800) * owner.level_mult)
            world.emit("explosion", x=a.x, y=a.y, radius=a.radius, color=a.color)
    elif a.kind == "rain":
        n = s.get("count", 6)
        interval = a.duration / n
        while a.timer >= interval and a.spec.get("_fired", 0) < n:
            a.timer -= interval
            a.spec = dict(a.spec, _fired=a.spec.get("_fired", 0) + 1)
            ang = random.uniform(0, 2 * math.pi)
            rr = random.uniform(0, a.radius)
            ex, ey = a.x + math.cos(ang) * rr, a.y + math.sin(ang) * rr
            world.explode(owner, ex, ey, s.get("explode_radius", 1.3) * TILE, s["damage"] * owner.level_mult,
                          s.get("color", (255, 160, 60)), 0.0)
    if a.left <= 0:
        a.alive = False
