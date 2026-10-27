"""Third-person follow camera.

* yaw/pitch come from the mouse (or gamepad right stick / Q,E keys);
* the focus point follows the player with exponential smoothing; height is
  smoothed more slowly so jumps don't shake the view, but a long fall is
  followed quickly;
* the camera is pulled closer if a platform would sit between it and the
  player (simple ray-march against the simulation's solids).
"""

import math


def _damp(current, target, rate, dt):
    return target + (current - target) * math.exp(-rate * dt)


class FollowCamera:
    def __init__(self, cam, lens):
        self.cam = cam
        self.lens = lens
        self.yaw = 0.0  # degrees, 0 = looking along +Y
        self.pitch = -16.0
        self.distance = 7.5
        self.fx = self.fy = self.fz = 0.0
        self.ground_z = 0.0
        self.shake = 0.0
        self._t = 0.0
        self.world = None
        self.current_dist = self.distance

    def snap(self, x, y, z, yaw=None):
        self.fx, self.fy, self.fz = x, y, z + 1.2
        self.ground_z = z
        if yaw is not None:
            self.yaw = yaw
        self.current_dist = self.distance

    def rotate(self, dyaw, dpitch):
        self.yaw = (self.yaw + dyaw) % 360.0
        self.pitch = max(-60.0, min(25.0, self.pitch + dpitch))

    def add_shake(self, amount):
        self.shake = min(0.6, self.shake + amount)

    def update(self, tx, ty, tz, grounded, dt):
        self._t += dt
        self.fx = _damp(self.fx, tx, 14.0, dt)
        self.fy = _damp(self.fy, ty, 14.0, dt)
        if grounded:
            self.ground_z = tz
        # Follow the ground level gently; if the player drops far below it, follow faster.
        target_z = self.ground_z + 1.2
        if tz + 1.2 < target_z - 1.5:
            target_z = tz + 1.2
            rate = 9.0
        else:
            rate = 5.0
        self.fz = _damp(self.fz, max(target_z, tz + 0.4), rate, dt)
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)
        fwd = (-math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), math.sin(pitch))
        want = self.distance
        if self.world is not None:
            want = self._clip_distance(fwd, want)
        self.current_dist = _damp(self.current_dist, want, 12.0 if want < self.current_dist else 3.0, dt)
        d = self.current_dist
        cx, cy, cz = self.fx - fwd[0] * d, self.fy - fwd[1] * d, self.fz - fwd[2] * d + 0.6
        if self.shake > 0.0:
            s = self.shake
            cx += math.sin(self._t * 53.0) * s * 0.3
            cz += math.cos(self._t * 47.0) * s * 0.3
            self.shake = max(0.0, self.shake - dt * 1.8)
        self.cam.setPos(cx, cy, cz)
        self.cam.lookAt(self.fx, self.fy, self.fz + 0.3)

    def _clip_distance(self, fwd, dist):
        """Shorten the boom if a solid box blocks the view of the player."""
        steps = 10
        for i in range(2, steps + 1):
            d = dist * i / steps
            px, py, pz = self.fx - fwd[0] * d, self.fy - fwd[1] * d, self.fz - fwd[2] * d + 0.6
            for s in self.world.solids_near(py, 0.5):
                if s.is_solid() and s.minx < px < s.maxx and s.miny < py < s.maxy and s.minz < pz < s.maxz:
                    return max(2.5, d - dist / steps)
        return dist

    def heading_vectors(self):
        """World-space (forward, right) unit vectors on the ground plane."""
        yaw = math.radians(self.yaw)
        fwd = (-math.sin(yaw), math.cos(yaw))
        right = (math.cos(yaw), math.sin(yaw))
        return fwd, right
