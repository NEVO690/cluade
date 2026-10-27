"""Character state shared by human players, bots and network players."""

import math
from dataclasses import dataclass

from .constants import RESPAWN_GRACE, STUN_TIME


class MoveState:
    """Gameplay movement states.  Animations are chosen *from* these, never the other way round."""

    IDLE = "IDLE"
    WALK = "WALK"
    RUN = "RUN"
    JUMP = "JUMP"
    FALL = "FALL"
    LAND = "LAND"
    TUMBLE = "TUMBLE"  # knocked back by an obstacle
    RESPAWNING = "RESPAWNING"
    ELIMINATED = "ELIMINATED"
    VICTORY = "VICTORY"  # crossed the finish line / won

    ALL = (IDLE, WALK, RUN, JUMP, FALL, LAND, TUMBLE, RESPAWNING, ELIMINATED, VICTORY)


@dataclass
class InputCommand:
    """What a controller (keyboard, gamepad, bot, network) asks a character to do this tick.

    move_x / move_y are a *world-space* wish direction with length <= 1.
    jump is "held"; the physics detects the press edge itself so a held key
    cannot produce repeated jumps.
    """

    move_x: float = 0.0
    move_y: float = 0.0
    jump: bool = False
    walk: bool = False

    def sanitized(self):
        """Clamp to legal values (used by the server for untrusted network input)."""
        mx = float(self.move_x) if math.isfinite(self.move_x) else 0.0
        my = float(self.move_y) if math.isfinite(self.move_y) else 0.0
        m = math.hypot(mx, my)
        if m > 1.0:
            mx, my = mx / m, my / m
        return InputCommand(mx, my, bool(self.jump), bool(self.walk))


IDLE_COMMAND = InputCommand()


class Character:
    """Physical body + race bookkeeping for one participant."""

    def __init__(self, cid, name, skin_id="classic", is_bot=False, slot=0):
        self.id = cid
        self.name = name
        self.skin_id = skin_id
        self.is_bot = is_bot
        self.slot = slot
        # Physics
        self.x = self.y = self.z = 0.0
        self.vx = self.vy = self.vz = 0.0
        self.yaw = 0.0  # radians, 0 = facing +Y
        self.grounded = False
        self.ground = None  # solid currently stood on
        self.air_time = 0.0
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.jump_held = False
        self.jumped = False  # current airborne phase started with a jump
        self.land_timer = 0.0
        self.stun = 0.0
        self.grace = 0.0
        self.knock_vx = self.knock_vy = 0.0
        self._hit_cooldowns = {}
        self.state = MoveState.IDLE
        self.wish_speed = 0.0
        # Race bookkeeping
        self.active = True  # takes part in the current round's simulation
        self.finished = False
        self.finish_time = None
        self.finish_place = None
        self.celebrate = False  # qualified/won: play the victory animation
        self.eliminated = False
        self.eliminated_at = None
        self.elim_reason = None
        self.respawn_timer = 0.0
        self.checkpoint = 0
        self.progress = 0.0  # metres along the course (for standings)
        self.best_progress = 0.0
        # Stats for the match report
        self.stat_jumps = 0
        self.stat_obstacles = 0
        self.stat_falls = 0
        self.stat_hits = 0
        self.stat_bonks = 0
        self._zones_cleared = set()
        self.events = []  # per-tick events for effects/sound: (kind, data)

    # ---------------------------------------------------------------- helpers
    @property
    def alive(self):
        return self.active and not self.eliminated and not self.finished

    @property
    def speed(self):
        return math.hypot(self.vx, self.vy)

    def place_at(self, x, y, z, yaw=0.0):
        self.x, self.y, self.z = x, y, z
        self.vx = self.vy = self.vz = 0.0
        self.knock_vx = self.knock_vy = 0.0
        self.yaw = yaw
        self.grounded = False
        self.ground = None
        self.air_time = 0.0
        self.stun = 0.0
        self.jumped = False
        self.jump_buffer = 0.0

    def reset_for_round(self):
        self.active = True
        self.finished = False
        self.finish_time = None
        self.finish_place = None
        self.celebrate = False
        self.eliminated = False
        self.eliminated_at = None
        self.elim_reason = None
        self.respawn_timer = 0.0
        self.checkpoint = 0
        self.progress = 0.0
        self.best_progress = 0.0
        self.grace = 0.0
        self._hit_cooldowns.clear()
        self._zones_cleared.clear()
        self.state = MoveState.IDLE
        self.events.clear()

    def hit_by(self, source_id, t, nx, ny, hvx, hvy, knock, lift):
        """Knock-back from a hazard.  (nx, ny) points away from the hazard."""
        last = self._hit_cooldowns.get(source_id, -99.0)
        if t - last < 0.35:
            return
        self._hit_cooldowns[source_id] = t
        if self.grace > 0.0:
            # Just respawned: get pushed but not stunned.
            self.vx, self.vy = nx * 3.0, ny * 3.0
            return
        # Combine the hazard's own motion with a push away from it.
        hs = math.hypot(hvx, hvy)
        if hs > 0.5:
            dx, dy = hvx / hs, hvy / hs
            dx, dy = dx * 0.7 + nx * 0.3, dy * 0.7 + ny * 0.3
        else:
            dx, dy = nx, ny
        dl = math.hypot(dx, dy) or 1.0
        power = max(knock, min(hs * 1.1, knock * 1.6))
        self.knock_vx = dx / dl * power
        self.knock_vy = dy / dl * power
        self.vx, self.vy = self.knock_vx, self.knock_vy
        self.vz = max(self.vz, lift)
        self.grounded = False
        self.ground = None
        self.stun = STUN_TIME
        self.jumped = False
        self.stat_hits += 1
        self.events.append(("hit", source_id))

    def start_respawn_grace(self):
        self.grace = RESPAWN_GRACE

    def snapshot(self):
        """Compact state used by the network protocol and the renderer."""
        return {
            "id": self.id,
            "x": round(self.x, 3), "y": round(self.y, 3), "z": round(self.z, 3),
            "yaw": round(self.yaw, 3),
            "vx": round(self.vx, 2), "vy": round(self.vy, 2), "vz": round(self.vz, 2),
            "st": self.state,
            "g": self.grounded,
            "fin": self.finished,
            "elim": self.eliminated,
            "prog": round(self.progress, 1),
        }
