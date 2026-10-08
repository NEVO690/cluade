"""Chase camera with smoothing, shake and a perspective projection."""
import math
import random

from . import settings as S
from .utils import clamp


class Camera:
    def __init__(self, width=S.SCREEN_W, height=S.SCREEN_H):
        self.width = width
        self.height = height
        self.focal = (width / 2) / math.tan(math.radians(S.CAMERA_HFOV) / 2)
        self.hx = width / 2
        self.hy = height * S.HORIZON_RATIO
        self.x = 0.0
        self.y = S.CAMERA_HEIGHT
        self.z = -S.CAMERA_BACK
        self.base_hx = self.hx
        self.base_hy = self.hy
        self._shake_time = 0.0
        self._shake_dur = 0.0
        self._shake_mag = 0.0
        self.fov_kick = 0.0  # widens the view slightly at high speed
        self._base_focal = self.focal

    def follow(self, px, py, pz, dt, snap=False):
        tx = px * 0.72
        # follow jumps loosely, but rise fully with roofs and jet flights
        ty = S.CAMERA_HEIGHT + (py * 0.62 if py < 3.4 else 3.4 * 0.62 + (py - 3.4) * 0.95)
        tz = pz - S.CAMERA_BACK
        if snap:
            self.x, self.y = tx, ty
        else:
            kx = 1 - math.exp(-dt * 9.0)
            ky = 1 - math.exp(-dt * 5.0)
            self.x += (tx - self.x) * kx
            self.y += (ty - self.y) * ky
        self.z = tz

    def shake(self, magnitude, duration):
        if magnitude >= self._shake_mag * (self._shake_time / max(self._shake_dur, 1e-6)):
            self._shake_mag = magnitude
            self._shake_dur = duration
            self._shake_time = duration

    def set_speed_factor(self, f):
        """f in 0..1 - gently widens the field of view as the run gets faster."""
        self.focal = self._base_focal * (1.0 - 0.08 * clamp(f, 0, 1))

    def update(self, dt):
        if self._shake_time > 0:
            self._shake_time = max(0.0, self._shake_time - dt)
            k = self._shake_mag * (self._shake_time / self._shake_dur)
            self.hx = self.base_hx + random.uniform(-k, k)
            self.hy = self.base_hy + random.uniform(-k, k)
        else:
            self.hx, self.hy = self.base_hx, self.base_hy

    # ------------------------------------------------------------------
    def project(self, x, y, z):
        dz = z - self.z
        if dz < S.NEAR_PLANE:
            return None
        s = self.focal / dz
        return (self.hx + (x - self.x) * s, self.hy - (y - self.y) * s, s)
