"""Damage, healing, kill handling and super charge."""
from ilbrawl.gameplay.entities import Brawler, Deployable


def credit_of(src):
    """The brawler that gets credit (kills, stats, charge) for an attack source."""
    if isinstance(src, Deployable):
        return src.owner
    return src


def apply_damage(world, src, target, amount, charge=0.0, kind="hit"):
    """Deal damage from src (Brawler/Deployable/None) to target (Brawler/Deployable). Returns dealt amount."""
    if not target.alive or amount <= 0:
        return 0
    attacker = credit_of(src) if src is not None else None
    if isinstance(target, Brawler):
        if target.spawn_protect > 0:
            return 0
        if target.shield_t > 0:
            amount *= 1.0 - target.shield_amt
        target.since_hurt = 0.0
        target.reveal_t = max(target.reveal_t, 1.0)
        if target.invis_t > 0:
            target.invis_t = min(target.invis_t, 0.4)
        target.last_damager = attacker
    amount = min(amount, target.hp)
    target.hp -= amount
    target.hit_flash = 0.12
    if attacker is not None and attacker is not target:
        attacker.stats.damage += amount
        if charge > 0 and isinstance(attacker, Brawler) and attacker.alive:
            was_ready = attacker.super_ready
            attacker.super_charge = min(1.0, attacker.super_charge + charge)
            if attacker.super_ready and not was_ready:
                world.emit("super_ready", who=attacker)
    world.emit("damage", x=target.x, y=target.y, amount=int(amount), target=target, src=attacker)
    if target.hp <= 0:
        kill(world, target, attacker)
    return amount


def apply_heal(world, src, target, amount, charge=0.0):
    if not target.alive or amount <= 0 or target.hp >= target.max_hp:
        return 0
    healed = min(amount, target.max_hp - target.hp)
    target.hp += healed
    healer = credit_of(src) if src is not None else None
    if healer is not None:
        healer.stats.healing += healed
        if charge > 0 and isinstance(healer, Brawler) and healer is not target:
            was_ready = healer.super_ready
            healer.super_charge = min(1.0, healer.super_charge + charge)
            if healer.super_ready and not was_ready:
                world.emit("super_ready", who=healer)
    world.emit("heal", x=target.x, y=target.y, amount=int(healed), target=target)
    return healed


def kill(world, target, attacker):
    target.alive = False
    target.hp = 0
    if isinstance(target, Brawler):
        target.stats.deaths += 1
        target.dash = None
        target.burst = []
        if attacker is not None and attacker is not target and attacker.team != target.team:
            attacker.stats.kills += 1
        world.emit("death", x=target.x, y=target.y, victim=target, killer=attacker)
        world.mode.on_death(target, attacker)
    else:
        world.emit("destroyed", x=target.x, y=target.y, obj=target)


def damage_tiles_in_radius(world, x, y, radius, amount, src=None):
    from ilbrawl.config import TILE
    tm = world.map
    x0, x1 = int((x - radius) // TILE), int((x + radius) // TILE)
    y0, y1 = int((y - radius) // TILE), int((y + radius) // TILE)
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            cx, cy = (tx + 0.5) * TILE, (ty + 0.5) * TILE
            if (cx - x) ** 2 + (cy - y) ** 2 <= (radius + TILE * 0.5) ** 2:
                world.hit_tile(tx, ty, amount)
