"""Gameplay entities (pure logic, no rendering)."""
import math

from ilbrawl.config import TILE

BRAWLER_RADIUS = 21


class Intent:
    """What a controller (player input or AI) wants a brawler to do this tick."""
    __slots__ = ("mx", "my", "ax", "ay", "attack", "super", "autoaim")

    def __init__(self):
        self.mx = self.my = 0.0
        self.ax = self.ay = 0.0
        self.attack = False
        self.super = False
        self.autoaim = False


class Stats:
    def __init__(self):
        self.kills = 0
        self.deaths = 0
        self.damage = 0.0
        self.healing = 0.0
        self.supers = 0
        self.gems = 0
        self.goals = 0
        self.zone_time = 0.0

    def as_dict(self):
        return dict(self.__dict__)


class Brawler:
    _next_id = 1

    def __init__(self, cdef, level, team, name, is_player=False, skin=None, level_bonus=0.06):
        self.id = Brawler._next_id
        Brawler._next_id += 1
        self.cdef = cdef
        self.char_id = cdef["id"]
        self.level = level
        self.team = team
        self.name = name
        self.is_player = is_player
        self.skin = skin
        self.style = cdef["style"]
        mult = 1.0 + level_bonus * (level - 1)
        self.level_mult = mult
        self.base_hp = cdef["hp"] * mult
        self.max_hp = self.base_hp
        self.hp = self.max_hp
        self.speed = cdef["speed"]
        self.ammo_max = cdef.get("ammo", 3)
        self.ammo = float(self.ammo_max)
        self.reload_time = cdef["reload"]
        self.hits_to_super = cdef.get("hits_to_super", 4)
        self.attack = cdef["attack"]
        self.sup = cdef["super"]
        self.radius = BRAWLER_RADIUS
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.kx = self.ky = 0.0          # knockback velocity
        self.facing = 0.0
        self.alive = True
        self.respawn_timer = None
        self.super_charge = 0.0
        self.attack_cd = 0.0
        self.since_hurt = 99.0
        self.since_attack = 99.0
        self.reveal_t = 0.0
        self.slow_t = 0.0
        self.slow_amt = 0.0
        self.stun_t = 0.0
        self.shield_t = 0.0
        self.shield_amt = 0.0
        self.invis_t = 0.0
        self.invis_speed = 1.0
        self.rage_t = 0.0
        self.rage = None
        self.burst = []                  # pending burst shots: [time_left, angle]
        self.dash = None
        self.cubes = 0
        self.gems = 0
        self.carrying_orb = False
        self.stats = Stats()
        self.hit_flash = 0.0
        self.attack_anim = 0.0
        self.spawn_protect = 0.0
        self.controller = None
        self.last_damager = None
        self.walk_phase = 0.0

    # ------------------------------------------------------------ derived
    @property
    def damage_mult(self):
        m = self.level_mult * (1 + 0.1 * self.cubes)
        if self.rage_t > 0 and self.rage:
            m *= self.rage.get("damage_mult", 1.0)
        return m

    @property
    def move_speed(self):
        s = self.speed
        if self.slow_t > 0:
            s *= 1.0 - self.slow_amt
        if self.rage_t > 0 and self.rage:
            s *= self.rage.get("speed_mult", 1.0)
        if self.invis_t > 0:
            s *= self.invis_speed
        if self.carrying_orb:
            s *= 0.92
        return s

    @property
    def reload_mult(self):
        if self.rage_t > 0 and self.rage:
            return self.rage.get("reload_mult", 1.0)
        return 1.0

    @property
    def attack_range_px(self):
        return self.attack.get("range", 5) * TILE

    @property
    def super_ready(self):
        return self.super_charge >= 1.0

    @property
    def hp_frac(self):
        return max(0.0, self.hp / self.max_hp)

    def dist_to(self, other):
        return math.hypot(other.x - self.x, other.y - self.y)

    def add_cube(self):
        self.cubes += 1
        self.max_hp = self.base_hp * (1 + 0.1 * self.cubes)
        self.hp = min(self.max_hp, self.hp + self.base_hp * 0.1)

    def reset_for_spawn(self, x, y):
        self.x, self.y = x, y
        self.hp = self.max_hp
        self.alive = True
        self.respawn_timer = None
        self.ammo = float(self.ammo_max)
        self.kx = self.ky = 0.0
        self.slow_t = self.stun_t = self.shield_t = self.invis_t = self.rage_t = 0.0
        self.dash = None
        self.burst = []
        self.carrying_orb = False
        self.spawn_protect = 1.5
        self.since_hurt = self.since_attack = 99.0


class Projectile:
    __slots__ = ("owner", "team", "x", "y", "vx", "vy", "speed", "radius", "damage", "range_left", "pierce",
                 "bounces", "boomerang", "returning", "heal", "slow", "stun", "knockback", "lob", "shape", "color",
                 "hit", "alive", "is_super", "charge", "explode_radius", "age", "origin", "travelled", "max_range",
                 "breaks_tiles")

    def __init__(self, owner, x, y, angle, spec, damage, is_super=False, charge=0.0):
        self.owner = owner
        self.team = owner.team
        self.x, self.y = x, y
        self.speed = spec.get("speed", 700)
        self.vx = math.cos(angle) * self.speed
        self.vy = math.sin(angle) * self.speed
        self.radius = spec.get("radius", 8)
        self.damage = damage
        self.max_range = spec.get("range", 6) * TILE
        self.range_left = self.max_range
        self.pierce = spec.get("pierce", False)
        self.bounces = spec.get("bounces", 0)
        self.boomerang = spec.get("type") == "boomerang"
        self.returning = False
        self.heal = spec.get("heal", 0) * getattr(owner, "level_mult", 1.0)
        self.slow = spec.get("slow", 0)
        self.stun = spec.get("stun", 0)
        self.knockback = spec.get("knockback", 0)
        self.lob = None
        self.shape = spec.get("shape", "bolt")
        self.color = tuple(spec.get("color", (255, 255, 255)))
        self.hit = set()
        self.alive = True
        self.is_super = is_super
        self.charge = charge
        self.explode_radius = spec.get("explode_radius", 0) * TILE
        self.age = 0.0
        self.origin = (x, y)
        self.travelled = 0.0
        self.breaks_tiles = True


class Deployable:
    """Turret / healing totem / decoy placed by a super."""
    _next_id = 10000

    def __init__(self, kind, owner, x, y, spec):
        self.id = Deployable._next_id
        Deployable._next_id += 1
        self.kind = kind
        self.owner = owner
        self.team = owner.team
        self.x, self.y = x, y
        lm = owner.level_mult
        self.max_hp = spec.get("hp", 2000) * lm
        self.hp = self.max_hp
        self.spec = spec
        self.life = spec.get("duration", 10)
        self.timer = 0.0
        self.radius = 20
        self.alive = True
        self.facing = 0.0
        self.hit_flash = 0.0
        self.char_id = owner.char_id
        self.style = owner.style
        self.level_mult = lm
        self.stats = owner.stats

    @property
    def hp_frac(self):
        return max(0.0, self.hp / self.max_hp)


class AreaEffect:
    def __init__(self, kind, owner, x, y, radius, duration, spec):
        self.kind = kind
        self.owner = owner
        self.team = owner.team
        self.x, self.y = x, y
        self.radius = radius
        self.duration = duration
        self.left = duration
        self.spec = spec
        self.timer = 0.0
        self.alive = True
        self.color = tuple(spec.get("color", (255, 255, 255)))


class Pickup:
    def __init__(self, kind, x, y, vx=0.0, vy=0.0, delay=0.4):
        self.kind = kind  # 'gem' or 'cube'
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.delay = delay
        self.alive = True
        self.age = 0.0


class Orb:
    def __init__(self, x, y):
        self.home = (x, y)
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.carrier = None
        self.block_id = None
        self.block_t = 0.0
        self.radius = 16

    def reset(self):
        self.x, self.y = self.home
        self.vx = self.vy = 0.0
        if self.carrier:
            self.carrier.carrying_orb = False
        self.carrier = None
