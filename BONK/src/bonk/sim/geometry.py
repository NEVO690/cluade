"""Small geometry helpers used by the collision code (no external dependencies)."""

import math


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def approach(current, target, max_delta):
    if current < target:
        return min(current + max_delta, target)
    return max(current - max_delta, target)


def wrap_angle(a):
    """Wrap an angle in radians to [-pi, pi)."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def closest_points_segments(p1, q1, p2, q2):
    """Closest points between segments p1-q1 and p2-q2 (3D tuples).

    Returns (c1, c2, dist_sq).  Standard algorithm from Ericson,
    "Real-Time Collision Detection", section 5.1.9.
    """
    d1 = (q1[0] - p1[0], q1[1] - p1[1], q1[2] - p1[2])
    d2 = (q2[0] - p2[0], q2[1] - p2[1], q2[2] - p2[2])
    r = (p1[0] - p2[0], p1[1] - p2[1], p1[2] - p2[2])
    a = d1[0] * d1[0] + d1[1] * d1[1] + d1[2] * d1[2]
    e = d2[0] * d2[0] + d2[1] * d2[1] + d2[2] * d2[2]
    f = d2[0] * r[0] + d2[1] * r[1] + d2[2] * r[2]
    eps = 1e-9
    if a <= eps and e <= eps:
        s = t = 0.0
    elif a <= eps:
        s = 0.0
        t = clamp(f / e, 0.0, 1.0)
    else:
        c = d1[0] * r[0] + d1[1] * r[1] + d1[2] * r[2]
        if e <= eps:
            t = 0.0
            s = clamp(-c / a, 0.0, 1.0)
        else:
            b = d1[0] * d2[0] + d1[1] * d2[1] + d1[2] * d2[2]
            denom = a * e - b * b
            s = clamp((b * f - c * e) / denom, 0.0, 1.0) if denom > eps else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t = 0.0
                s = clamp(-c / a, 0.0, 1.0)
            elif t > 1.0:
                t = 1.0
                s = clamp((b - c) / a, 0.0, 1.0)
    c1 = (p1[0] + d1[0] * s, p1[1] + d1[1] * s, p1[2] + d1[2] * s)
    c2 = (p2[0] + d2[0] * t, p2[1] + d2[1] * t, p2[2] + d2[2] * t)
    dx, dy, dz = c1[0] - c2[0], c1[1] - c2[1], c1[2] - c2[2]
    return c1, c2, dx * dx + dy * dy + dz * dz


def circle_rect_push(x, y, r, minx, miny, maxx, maxy):
    """Push vector that moves a circle (x, y, r) out of a rectangle, or None."""
    cx = clamp(x, minx, maxx)
    cy = clamp(y, miny, maxy)
    dx, dy = x - cx, y - cy
    d2 = dx * dx + dy * dy
    if d2 >= r * r:
        return None
    if d2 > 1e-12:
        d = math.sqrt(d2)
        k = (r - d) / d
        return dx * k, dy * k
    # Centre is inside the rectangle: leave along the shallowest side.
    left, right = x - minx, maxx - x
    down, up = y - miny, maxy - y
    m = min(left, right, down, up)
    if m == left:
        return -(left + r), 0.0
    if m == right:
        return right + r, 0.0
    if m == down:
        return 0.0, -(down + r)
    return 0.0, up + r


def circle_overlaps_rect(x, y, r, minx, miny, maxx, maxy):
    cx = clamp(x, minx, maxx)
    cy = clamp(y, miny, maxy)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy < r * r
