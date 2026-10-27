"""Course centre-line made of waypoints.  Used for standings and by the bot AI."""

import math


class Waypoint:
    __slots__ = ("x", "y", "z", "width", "tags", "s")

    def __init__(self, x, y, z, width=2.0, tags=()):
        self.x, self.y, self.z = x, y, z
        self.width = width  # half-width of the walkable corridor at this point
        self.tags = tuple(tags)
        self.s = 0.0  # distance from the start along the route

    def has(self, tag):
        return any(t == tag or t.startswith(tag + ":") for t in self.tags)

    def tag_value(self, tag, default=None):
        for t in self.tags:
            if t.startswith(tag + ":"):
                return t.split(":", 1)[1]
        return default


class Route:
    def __init__(self, waypoints):
        if len(waypoints) < 2:
            raise ValueError("a route needs at least two waypoints")
        self.points = waypoints
        s = 0.0
        waypoints[0].s = 0.0
        for a, b in zip(waypoints, waypoints[1:]):
            s += math.hypot(b.x - a.x, b.y - a.y)
            b.s = s
        self.length = s

    def project(self, x, y, z, hint=0, window=None):
        """Project a point onto the route.

        Returns (distance_along, segment_index, lateral, match_cost) where
        match_cost is the squared distance plus a penalty for height mismatch.

        Segments whose height is far from `z` are penalised so that a character
        on one level is not projected onto a route above or below it.
        """
        pts = self.points
        n = len(pts) - 1
        if window is None:
            lo, hi = 0, n
        else:
            lo, hi = max(0, hint - window), min(n, hint + window + 1)
        best = (1e18, 0.0, 0, 0.0)
        for i in range(lo, hi):
            a, b = pts[i], pts[i + 1]
            ex, ey = b.x - a.x, b.y - a.y
            l2 = ex * ex + ey * ey
            if l2 < 1e-9:
                continue
            u = ((x - a.x) * ex + (y - a.y) * ey) / l2
            u = 0.0 if u < 0.0 else 1.0 if u > 1.0 else u
            px, py = a.x + ex * u, a.y + ey * u
            pz = a.z + (b.z - a.z) * u
            dx, dy = x - px, y - py
            d2 = dx * dx + dy * dy
            dz = abs(z - pz)
            if dz > 2.5:
                d2 += (dz - 2.5) ** 2 * 4.0 + 4.0
            if d2 < best[0]:
                l = math.sqrt(l2)
                lateral = (dx * -ey + dy * ex) / l  # signed distance (left positive)
                best = (d2, a.s + (b.s - a.s) * u, i, lateral)
        return best[1], best[2], best[3], best[0]

    def point_at(self, s):
        """(x, y, z, segment_index) at distance `s` along the route."""
        pts = self.points
        if s <= 0.0:
            return pts[0].x, pts[0].y, pts[0].z, 0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if s <= b.s or i == len(pts) - 2:
                span = b.s - a.s
                u = 0.0 if span <= 1e-9 else min(1.0, (s - a.s) / span)
                return (a.x + (b.x - a.x) * u, a.y + (b.y - a.y) * u,
                        a.z + (b.z - a.z) * u, i)
        last = pts[-1]
        return last.x, last.y, last.z, len(pts) - 2

    def frame_at(self, s):
        """(x, y, z, dir_x, dir_y, half_width, segment) of the route at distance s."""
        pts = self.points
        s = max(pts[0].s, min(s, pts[-1].s))
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if s <= b.s or i == len(pts) - 2:
                span = b.s - a.s
                u = 0.0 if span <= 1e-9 else max(0.0, min(1.0, (s - a.s) / span))
                dx, dy = b.x - a.x, b.y - a.y
                l = math.hypot(dx, dy) or 1.0
                return (a.x + dx * u, a.y + dy * u, a.z + (b.z - a.z) * u, dx / l, dy / l,
                        a.width + (b.width - a.width) * u, i)
        last = pts[-1]
        return last.x, last.y, last.z, 0.0, 1.0, last.width, len(pts) - 2

    @property
    def end_s(self):
        return self.points[-1].s

    def direction(self, seg):
        a, b = self.points[seg], self.points[min(seg + 1, len(self.points) - 1)]
        dx, dy = b.x - a.x, b.y - a.y
        l = math.hypot(dx, dy) or 1.0
        return dx / l, dy / l
