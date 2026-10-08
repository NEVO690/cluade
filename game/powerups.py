"""Modular power-up system.

A power-up is described in ``data/powerups.json`` and its behaviour is an
*effect class* registered here with ``@register("<effect>")``.

To add a new power-up:
  1. add an entry to ``data/powerups.json`` (id, name, effect, durations ...)
  2. if its ``effect`` is new, write a subclass of :class:`PowerUpEffect`
     below, decorated with ``@register("your_effect")``.  Override the
     modifier attributes and/or the ``on_start/on_update/on_end`` hooks.

The game asks :class:`PowerUpManager` for combined modifiers every frame
(magnet radius, score multiplier, jump multiplier, flying, invincible ...).
"""
from .utils import log

EFFECT_TYPES = {}


def register(name):
    def deco(cls):
        EFFECT_TYPES[name] = cls
        cls.effect_name = name
        return cls
    return deco


class PowerUpEffect:
    effect_name = "base"
    magnet_radius = 0.0
    score_mult = 1.0
    jump_mult = 1.0
    speed_mult = 1.0
    invincible = False
    flying = False
    absorbs_hit = False

    def __init__(self, definition, duration):
        self.definition = definition
        self.params = definition.get("params", {})
        self.duration = duration
        self.remaining = duration

    def on_start(self, session):
        pass

    def on_update(self, session, dt):
        pass

    def on_end(self, session):
        pass

    def refresh(self, duration):
        self.duration = max(self.duration, duration)
        self.remaining = max(self.remaining, duration)


@register("magnet")
class MagnetEffect(PowerUpEffect):
    def __init__(self, definition, duration):
        super().__init__(definition, duration)
        self.magnet_radius = float(self.params.get("radius", 8.0))


@register("jet")
class JetEffect(PowerUpEffect):
    flying = True
    invincible = True

    def on_start(self, session):
        session.player.start_flight(float(self.params.get("height", 7.5)))
        session.world.spawn_sky_coins(session.player, self.remaining)

    def on_update(self, session, dt):
        # keep a coin trail ahead of the player while flying
        session.world.spawn_sky_coins(session.player, self.remaining)

    def on_end(self, session):
        session.player.end_flight()
        session.world.clear_sky_coins_after(session.player.z + 25)
        session.grant_invulnerability(2.0)


@register("shield")
class ShieldEffect(PowerUpEffect):
    absorbs_hit = True


@register("score_mult")
class ScoreMultiplierEffect(PowerUpEffect):
    def __init__(self, definition, duration):
        super().__init__(definition, duration)
        self.score_mult = float(self.params.get("mult", 2.0))


@register("super_jump")
class SuperJumpEffect(PowerUpEffect):
    def __init__(self, definition, duration):
        super().__init__(definition, duration)
        self.jump_mult = float(self.params.get("jump_mult", 1.5))


@register("speed")
class SpeedBoostEffect(PowerUpEffect):
    invincible = True

    def __init__(self, definition, duration):
        super().__init__(definition, duration)
        self.speed_mult = float(self.params.get("speed_mult", 1.45))
        self.score_mult = float(self.params.get("score_bonus", 1.5))

    def on_end(self, session):
        session.grant_invulnerability(1.5)


@register("board")
class BoardEffect(PowerUpEffect):
    """Riding a board: absorbs one crash; board perks add small bonuses."""
    absorbs_hit = True

    def __init__(self, definition, duration):
        super().__init__(definition, duration)
        perk = self.params.get("perk", {})
        kind, value = perk.get("type"), float(perk.get("value", 0))
        if kind == "magnet":
            self.magnet_radius = value
        elif kind == "jump_bonus":
            self.jump_mult = 1.0 + value
        elif kind == "score_bonus":
            self.score_mult = 1.0 + value
        self.coin_bonus = value if kind == "coin_bonus" else 0.0

    def on_start(self, session):
        session.player.board_active = True

    def on_end(self, session):
        session.player.board_active = False


class PowerUpManager:
    def __init__(self, gamedata, economy, duration_bonus=0.0):
        self.gamedata = gamedata
        self.economy = economy
        self.duration_bonus = duration_bonus
        self.active = {}

    def duration_for(self, pid):
        d = self.gamedata.powerup_by_id.get(pid)
        if not d:
            return 0.0
        level = self.economy.upgrade_level(pid) if d.get("upgradeable") else 0
        durs = d["durations"]
        return durs[min(level, len(durs) - 1)] * (1.0 + self.duration_bonus)

    def activate(self, pid, session, duration=None, definition=None):
        definition = definition or self.gamedata.powerup_by_id.get(pid)
        if definition is None:
            log.warning("Unknown power-up '%s'", pid)
            return None
        cls = EFFECT_TYPES.get(definition.get("effect"))
        if cls is None:
            log.warning("Power-up '%s' uses unknown effect '%s'", pid, definition.get("effect"))
            return None
        duration = duration if duration is not None else self.duration_for(pid)
        if pid in self.active:
            self.active[pid].refresh(duration)
            return self.active[pid]
        eff = cls(definition, duration)
        self.active[pid] = eff
        eff.on_start(session)
        return eff

    def update(self, dt, session):
        for pid in list(self.active):
            eff = self.active.get(pid)
            if eff is None:
                continue
            eff.remaining -= dt
            eff.on_update(session, dt)
            if eff.remaining <= 0:
                self.deactivate(pid, session)

    def deactivate(self, pid, session):
        eff = self.active.pop(pid, None)
        if eff is not None:
            eff.on_end(session)

    def clear(self, session):
        for pid in list(self.active):
            self.deactivate(pid, session)

    def has(self, pid):
        return pid in self.active

    def consume_hit_absorber(self, session):
        """Use up a shield/board to survive a crash. Returns the id used or None."""
        for pid in ("shield", "board"):
            eff = self.active.get(pid)
            if eff is not None and eff.absorbs_hit:
                self.deactivate(pid, session)
                return pid
        for pid, eff in list(self.active.items()):
            if eff.absorbs_hit:
                self.deactivate(pid, session)
                return pid
        return None

    # --- combined modifiers -------------------------------------------------
    @property
    def magnet_radius(self):
        return max((e.magnet_radius for e in self.active.values()), default=0.0)

    @property
    def score_mult(self):
        m = 1.0
        for e in self.active.values():
            m *= e.score_mult
        return m

    @property
    def jump_mult(self):
        return max((e.jump_mult for e in self.active.values()), default=1.0)

    @property
    def speed_mult(self):
        return max((e.speed_mult for e in self.active.values()), default=1.0)

    @property
    def invincible(self):
        return any(e.invincible for e in self.active.values())

    @property
    def flying(self):
        return any(e.flying for e in self.active.values())

    @property
    def protected(self):
        return any(e.absorbs_hit for e in self.active.values())

    @property
    def coin_bonus(self):
        return sum(getattr(e, "coin_bonus", 0.0) for e in self.active.values())

    def hud_entries(self):
        """[(definition, remaining, duration)] for the HUD timers."""
        return [(e.definition, e.remaining, e.duration) for e in self.active.values()]
