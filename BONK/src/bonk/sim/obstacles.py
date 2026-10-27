"""Course elements: things you stand on (solids) and things that knock you away (hazards).

Every moving element is a pure function of the course clock ``t`` (except the
vanishing tiles, whose state also depends on the moment they were first stepped
on).  This keeps server and clients in sync from just the clock plus tile
trigger events, and lets the bots predict where an obstacle will be.
"""

import math

from .constants import CHAR_HEIGHT, CHAR_RADIUS
from .geometry import closest_points_segments

TWO_PI = 2.0 * math.pi


class Solid:
    """Axis-aligned box you can stand on and collide with."""

    kind = "box"
    moving = False
    bounce = 0.0  # >0: upward launch speed when landed on (jump pad)
    knock = 0.0  # >0: horizontal knock speed when it pushes into you (pistons)

    def __init__(self, sid, center, size, style=None):
        self.id = sid
        self.cx, self.cy, self.cz = center  # centre of the box
        self.hx, self.hy, self.hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        self.style = style or {}
        self.vx = self.vy = self.vz = 0.0
        self.dx = self.dy = self.dz = 0.0  # displacement during the last update
        self._stamp = -1
        self._refresh_bounds()

    # -- bounds -----------------------------------------------------------
    def _refresh_bounds(self):
        self.minx, self.maxx = self.cx - self.hx, self.cx + self.hx
        self.miny, self.maxy = self.cy - self.hy, self.cy + self.hy
        self.minz, self.maxz = self.cz - self.hz, self.cz + self.hz

    def sweep_bounds(self):
        """Box that contains every position this solid can ever occupy."""
        return (self.minx, self.miny, self.minz, self.maxx, self.maxy, self.maxz)

    # -- queries ------------------------------------------------------------
    def top_at(self, x, y):
        return self.maxz

    def is_solid(self):
        return True

    def is_safe(self, t, horizon=0.0):
        """True if a bot can rely on standing here for the next `horizon` seconds."""
        return True

    # -- simulation -----------------------------------------------------------
    def update(self, t, dt):
        pass

    def on_stand(self, character, t):
        pass

    # -- rendering ------------------------------------------------------------
    def render_state(self, t):
        return (self.cx, self.cy, self.cz)


class Ramp(Solid):
    """Wedge whose walkable top rises linearly from z0 (at min Y) to z1 (at max Y)."""

    kind = "ramp"

    def __init__(self, sid, center, size, z0, z1, style=None):
        self.z0, self.z1 = z0, z1
        super().__init__(sid, center, size, style)

    def _refresh_bounds(self):
        super()._refresh_bounds()
        self.maxz = max(self.z0, self.z1)

    def top_at(self, x, y):
        span = self.maxy - self.miny
        if span <= 0.0:
            return self.maxz
        f = (y - self.miny) / span
        f = 0.0 if f < 0.0 else 1.0 if f > 1.0 else f
        return self.z0 + (self.z1 - self.z0) * f


class MovingPlatform(Solid):
    """Platform that eases back and forth between `center` and `center + offset`."""

    kind = "moving"
    moving = True

    def __init__(self, sid, center, size, offset, period, phase=0.0, style=None):
        self.base = tuple(center)
        self.offset = tuple(offset)
        self.period = max(0.5, float(period))
        self.phase = phase
        super().__init__(sid, center, size, style)
        self._apply(0.0)
        self.dx = self.dy = self.dz = 0.0

    def position_at(self, t):
        f = 0.5 - 0.5 * math.cos(TWO_PI * t / self.period + self.phase)
        return (self.base[0] + self.offset[0] * f,
                self.base[1] + self.offset[1] * f,
                self.base[2] + self.offset[2] * f)

    def velocity_at(self, t):
        w = TWO_PI / self.period
        k = 0.5 * w * math.sin(w * t + self.phase)
        return (self.offset[0] * k, self.offset[1] * k, self.offset[2] * k)

    def _apply(self, t):
        self.cx, self.cy, self.cz = self.position_at(t)
        self._refresh_bounds()

    def sweep_bounds(self):
        bx, by, bz = self.base
        ox, oy, oz = self.offset
        return (min(bx, bx + ox) - self.hx, min(by, by + oy) - self.hy, min(bz, bz + oz) - self.hz,
                max(bx, bx + ox) + self.hx, max(by, by + oy) + self.hy, max(bz, bz + oz) + self.hz)

    def update(self, t, dt):
        ox, oy, oz = self.cx, self.cy, self.cz
        self._apply(t)
        self.dx, self.dy, self.dz = self.cx - ox, self.cy - oy, self.cz - oz
        self.vx, self.vy, self.vz = self.velocity_at(t)


class Pusher(MovingPlatform):
    """Piston block: rests, shoots out quickly, holds, then retracts."""

    kind = "pusher"

    def __init__(self, sid, center, size, offset, period, phase=0.0, knock=9.0, style=None):
        self.knock = knock
        super().__init__(sid, center, size, offset, period, phase, style)

    def _extension(self, t):
        # Normalised cycle: 0-0.40 rest, 0.40-0.52 extend, 0.52-0.75 hold, 0.75-1.0 retract.
        u = ((t / self.period) + self.phase / TWO_PI) % 1.0
        if u < 0.40:
            return 0.0, 0.0
        if u < 0.52:
            f = (u - 0.40) / 0.12
            return f, 1.0 / (0.12 * self.period)
        if u < 0.75:
            return 1.0, 0.0
        f = 1.0 - (u - 0.75) / 0.25
        return f, -1.0 / (0.25 * self.period)

    def position_at(self, t):
        f, _ = self._extension(t)
        return (self.base[0] + self.offset[0] * f,
                self.base[1] + self.offset[1] * f,
                self.base[2] + self.offset[2] * f)

    def velocity_at(self, t):
        _, rate = self._extension(t)
        return (self.offset[0] * rate, self.offset[1] * rate, self.offset[2] * rate)

    def danger_at(self, x, y, z, t, margin=0.3):
        """Would a character at (x, y, z) be inside the piston's reach at time t?"""
        if z + CHAR_HEIGHT <= self.minz or z >= self.maxz:
            return False
        px, py, _ = self.position_at(t)
        r = CHAR_RADIUS + margin
        return (px - self.hx - r < x < px + self.hx + r) and (py - self.hy - r < y < py + self.hy + r)


class BouncePad(Solid):
    kind = "bounce"

    def __init__(self, sid, center, size, bounce=16.0, style=None):
        super().__init__(sid, center, size, style)
        self.bounce = bounce


class VanishingTile(Solid):
    """Tile that starts flashing when stepped on, then disappears for a while."""

    kind = "tile"
    SOLID, WARNING, GONE = "solid", "warning", "gone"

    def __init__(self, sid, center, size, warn_time=0.7, gone_time=4.0, style=None):
        super().__init__(sid, center, size, style)
        self.warn_time = warn_time
        self.gone_time = gone_time  # <= 0 means the tile never comes back
        self.triggered_at = None
        self.state = self.SOLID

    def state_at(self, t):
        if self.triggered_at is None:
            return self.SOLID
        age = t - self.triggered_at
        if age < self.warn_time:
            return self.WARNING
        if self.gone_time <= 0.0 or age < self.warn_time + self.gone_time:
            return self.GONE
        return self.SOLID

    def update(self, t, dt):
        self.state = self.state_at(t)
        if self.state == self.SOLID and self.triggered_at is not None:
            self.triggered_at = None  # respawned; can be triggered again

    def is_solid(self):
        return self.state != self.GONE

    def is_safe(self, t, horizon=0.0):
        if self.triggered_at is None:
            return True
        if self.state == self.WARNING:
            return (self.triggered_at + self.warn_time) - t > horizon
        return False

    def on_stand(self, character, t):
        if self.triggered_at is None:
            self.triggered_at = t
            self.state = self.WARNING

    def warning_fraction(self, t):
        if self.triggered_at is None:
            return 0.0
        return min(1.0, (t - self.triggered_at) / self.warn_time)


# ---------------------------------------------------------------------------
# Hazards
# ---------------------------------------------------------------------------


class Hazard:
    """Moving obstacle that knocks characters back instead of being stood on."""

    kind = "hazard"

    def __init__(self, hid, style=None):
        self.id = hid
        self.style = style or {}
        self._stamp = -1

    def sweep_bounds(self):
        raise NotImplementedError

    def update(self, t, dt):
        pass

    def segments_at(self, t):
        """List of (p, q, radius, velocity_fn) capsules describing the hazard at time t."""
        raise NotImplementedError

    def collide(self, ch, t):
        """Resolve contact with character `ch`.  Returns True if it was hit."""
        bottom = (ch.x, ch.y, ch.z + CHAR_RADIUS)
        top = (ch.x, ch.y, ch.z + CHAR_HEIGHT - CHAR_RADIUS)
        for p, q, radius, vel_fn in self.segments_at(t):
            c_char, c_haz, d2 = closest_points_segments(bottom, top, p, q)
            reach = radius + CHAR_RADIUS
            if d2 >= reach * reach:
                continue
            d = math.sqrt(d2) if d2 > 1e-12 else 1e-6
            nx = (c_char[0] - c_haz[0]) / d
            ny = (c_char[1] - c_haz[1]) / d
            hl = math.hypot(nx, ny)
            if hl < 1e-4:
                nx, ny, hl = 0.0, -1.0, 1.0
            nx, ny = nx / hl, ny / hl
            depth = reach - d
            ch.x += nx * depth
            ch.y += ny * depth
            vx, vy, vz = vel_fn(c_haz)
            ch.hit_by(self.id, t, nx, ny, vx, vy, self.style.get("knock", 11.0),
                      self.style.get("lift", 6.0))
            return True
        return False

    def danger_at(self, x, y, z, t, margin=0.3):
        """Would a character standing at (x, y, z) be touching this hazard at time t?"""
        bottom = (x, y, z + CHAR_RADIUS)
        top = (x, y, z + CHAR_HEIGHT - CHAR_RADIUS)
        for p, q, radius, _ in self.segments_at(t):
            _, _, d2 = closest_points_segments(bottom, top, p, q)
            reach = radius + CHAR_RADIUS + margin
            if d2 < reach * reach:
                return True
        return False


class PendulumHammer(Hazard):
    """A hammer hanging from a pivot, swinging across the course.

    axis="y": swings in the X-Z plane (side to side across a course that runs along Y).
    axis="x": swings in the Y-Z plane (towards / away from the runner).
    """

    kind = "hammer"

    def __init__(self, hid, pivot, length, amplitude_deg, period, phase=0.0,
                 head_radius=0.65, head_half_len=0.9, axis="y", style=None):
        super().__init__(hid, style)
        self.pivot = tuple(pivot)
        self.length = length
        self.amplitude = math.radians(amplitude_deg)
        self.period = period
        self.phase = phase
        self.head_radius = head_radius
        self.head_half_len = head_half_len
        self.axis = axis

    def angle_at(self, t):
        return self.amplitude * math.sin(TWO_PI * t / self.period + self.phase)

    def angular_velocity_at(self, t):
        w = TWO_PI / self.period
        return self.amplitude * w * math.cos(w * t + self.phase)

    def _dir(self, a):
        s, c = math.sin(a), math.cos(a)
        if self.axis == "y":
            return (s, 0.0, -c), (c, 0.0, s)  # arm direction, tangent
        return (0.0, s, -c), (0.0, c, s)

    def head_center(self, t):
        arm, _ = self._dir(self.angle_at(t))
        px, py, pz = self.pivot
        L = self.length
        return (px + arm[0] * L, py + arm[1] * L, pz + arm[2] * L)

    def segments_at(self, t):
        a = self.angle_at(t)
        w = self.angular_velocity_at(t)
        arm, tan = self._dir(a)
        px, py, pz = self.pivot
        L = self.length
        hc = (px + arm[0] * L, py + arm[1] * L, pz + arm[2] * L)
        h = self.head_half_len
        p = (hc[0] - tan[0] * h, hc[1] - tan[1] * h, hc[2] - tan[2] * h)
        q = (hc[0] + tan[0] * h, hc[1] + tan[1] * h, hc[2] + tan[2] * h)

        def vel(point, tan=tan, w=w, L=L):
            return (tan[0] * w * L, tan[1] * w * L, tan[2] * w * L)

        return [(p, q, self.head_radius, vel)]

    def sweep_bounds(self):
        px, py, pz = self.pivot
        r = self.length + self.head_half_len + self.head_radius
        return (px - r, py - r, pz - r, px + r, py + r, pz + 0.5)

    def render_state(self, t):
        return (self.pivot, math.degrees(self.angle_at(t)))


class Sweeper(Hazard):
    """One or more bars rotating around a vertical post, low enough to jump over."""

    kind = "sweeper"

    def __init__(self, hid, center, z, length, angular_speed, arms=2, phase=0.0,
                 radius=0.28, style=None):
        super().__init__(hid, style)
        self.cx, self.cy = center[0], center[1]
        self.z = z
        self.length = length
        self.speed = angular_speed  # rad/s, sign = direction
        self.arms = max(1, int(arms))
        self.phase = phase
        self.radius = radius

    def angle_at(self, t):
        return self.phase + self.speed * t

    def segments_at(self, t):
        base = self.angle_at(t)
        out = []
        for k in range(self.arms):
            a = base + TWO_PI * k / self.arms
            ca, sa = math.cos(a), math.sin(a)
            p = (self.cx + ca * 0.35, self.cy + sa * 0.35, self.z)
            q = (self.cx + ca * self.length, self.cy + sa * self.length, self.z)

            def vel(point, cx=self.cx, cy=self.cy, w=self.speed):
                rx, ry = point[0] - cx, point[1] - cy
                return (-ry * w, rx * w, 0.0)

            out.append((p, q, self.radius, vel))
        return out

    def sweep_bounds(self):
        r = self.length + self.radius
        return (self.cx - r, self.cy - r, self.z - self.radius,
                self.cx + r, self.cy + r, self.z + self.radius)

    def render_state(self, t):
        return ((self.cx, self.cy, self.z), math.degrees(self.angle_at(t)))

