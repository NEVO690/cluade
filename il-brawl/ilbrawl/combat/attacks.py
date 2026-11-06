"""Main attack patterns: single, spread, burst, flame, wave, bounce, boomerang, lob and melee."""
import math

from ilbrawl.combat import damage as dmg
from ilbrawl.config import TILE
from ilbrawl.gameplay.entities import Projectile

ATTACK_COOLDOWN = 0.28


def projectile_count(spec):
    t = spec["type"]
    if t in ("spread", "flame", "burst"):
        return spec.get("count", 1)
    return 1


def can_attack(b):
    return b.alive and b.ammo >= 1.0 and b.attack_cd <= 0 and b.stun_t <= 0 and b.dash is None


def fire(world, b, tx, ty):
    """Fire b's main attack toward world point (tx, ty). Returns True if fired."""
    if b.carrying_orb and world.orb is not None:
        if b.attack_cd <= 0 and b.stun_t <= 0:
            world.throw_orb(b, tx, ty)
            b.attack_cd = 0.35
            return True
        return False
    if not can_attack(b):
        return False
    spec = b.attack
    angle = math.atan2(ty - b.y, tx - b.x)
    b.facing = angle
    b.ammo -= 1.0
    b.attack_cd = ATTACK_COOLDOWN
    b.since_attack = 0.0
    b.reveal_t = 1.2
    b.attack_anim = 0.18
    if b.invis_t > 0:
        b.invis_t = 0.0
    dmg_mult = b.damage_mult
    count = projectile_count(spec)
    charge = 1.0 / (b.hits_to_super * count)
    t = spec["type"]
    muzzle = b.radius + 6
    sx, sy = b.x + math.cos(angle) * muzzle * 0.5, b.y + math.sin(angle) * muzzle * 0.5
    world.emit("shot", x=sx, y=sy, angle=angle, who=b, sound=spec.get("sound", "shoot"), color=spec.get("color"))
    if t in ("single", "wave", "bounce", "boomerang"):
        world.add_projectile(Projectile(b, sx, sy, angle, spec, spec["damage"] * dmg_mult, False, charge))
    elif t in ("spread", "flame"):
        n = spec.get("count", 3)
        spread = math.radians(spec.get("spread", 20))
        for i in range(n):
            a = angle + (spread * (i / (n - 1) - 0.5) if n > 1 else 0)
            p = Projectile(b, sx, sy, a, spec, spec["damage"] * dmg_mult, False, charge)
            if t == "flame":
                p.max_range = p.range_left = spec["range"] * TILE * (0.85 + 0.15 * (1 - abs(i / max(1, n - 1) - 0.5) * 2))
            world.add_projectile(p)
    elif t == "burst":
        n = spec.get("count", 3)
        delay = spec.get("delay", 0.1)
        world.add_projectile(Projectile(b, sx, sy, angle, spec, spec["damage"] * dmg_mult, False, charge))
        for i in range(1, n):
            b.burst.append([delay * i, angle, charge])
        b.attack_cd = max(ATTACK_COOLDOWN, delay * n + 0.12)
    elif t == "lob":
        fire_lob(world, b, tx, ty, spec, spec["damage"] * dmg_mult, False, charge)
    elif t == "melee":
        melee(world, b, angle, spec, spec["damage"] * dmg_mult, 1.0 / b.hits_to_super)
    return True


def fire_burst_shot(world, b, angle, charge):
    spec = b.attack
    sx, sy = b.x + math.cos(angle) * b.radius * 0.6, b.y + math.sin(angle) * b.radius * 0.6
    world.add_projectile(Projectile(b, sx, sy, angle, spec, spec["damage"] * b.damage_mult, False, charge))
    world.emit("shot", x=sx, y=sy, angle=angle, who=b, sound=spec.get("sound", "shoot"), color=spec.get("color"))


def fire_lob(world, owner, tx, ty, spec, damage, is_super, charge, src=None):
    src = src or owner
    rng = spec.get("range", 7) * TILE
    dx, dy = tx - src.x, ty - src.y
    d = math.hypot(dx, dy)
    if d > rng:
        tx, ty = src.x + dx / d * rng, src.y + dy / d * rng
        d = rng
    d = max(d, TILE * 0.8)
    angle = math.atan2(dy, dx) if (dx or dy) else 0
    p = Projectile(owner, src.x, src.y, angle, spec, damage, is_super, charge)
    p.team = src.team
    duration = max(0.35, d / spec.get("speed", 520))
    p.lob = {"sx": src.x, "sy": src.y, "tx": tx, "ty": ty, "t": 0.0, "dur": duration, "h": 40 + d * 0.18}
    p.explode_radius = spec.get("explode_radius", 1.2) * TILE
    world.add_projectile(p)
    return p


def melee(world, b, angle, spec, damage, charge):
    rng = spec.get("range", 2) * TILE
    arc = math.radians(spec.get("arc", 100))
    world.emit("melee", x=b.x, y=b.y, angle=angle, arc=arc, range=rng, color=spec.get("color"), who=b)
    for t in world.damageable_enemies(b.team):
        dx, dy = t.x - b.x, t.y - b.y
        d = math.hypot(dx, dy)
        if d - t.radius > rng:
            continue
        diff = (math.atan2(dy, dx) - angle + math.pi) % (2 * math.pi) - math.pi
        if abs(diff) > arc / 2 and d > t.radius + b.radius:
            continue
        if not world.map.line_clear(b.x, b.y, t.x, t.y):
            continue
        dmg.apply_damage(world, b, t, damage, charge)
        if spec.get("knockback"):
            world.knock(t, dx / max(d, 1), dy / max(d, 1), spec["knockback"])
    # melee also smashes cover in front
    hx, hy = b.x + math.cos(angle) * rng * 0.7, b.y + math.sin(angle) * rng * 0.7
    world.hit_tile(int(hx // TILE), int(hy // TILE), damage)
