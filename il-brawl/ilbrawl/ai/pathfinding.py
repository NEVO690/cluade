"""Grid A* pathfinding (8-directional, no corner cutting)."""
import heapq
import math

SQRT2 = math.sqrt(2)
DIRS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
        (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2)]


def astar(tm, start, goal, max_nodes=2500):
    if start == goal:
        return [goal]
    if tm.walk_blocked(*goal):
        goal = _nearest_open(tm, goal)
        if goal is None:
            return []
    open_heap = [(0.0, 0.0, start)]
    came = {start: None}
    cost = {start: 0.0}
    gx, gy = goal
    expanded = 0
    while open_heap:
        _, g, cur = heapq.heappop(open_heap)
        if cur == goal:
            break
        if g > cost.get(cur, 1e18):
            continue
        expanded += 1
        if expanded > max_nodes:
            break
        cx, cy = cur
        for dx, dy, c in DIRS:
            nx, ny = cx + dx, cy + dy
            if tm.walk_blocked(nx, ny):
                continue
            if dx and dy and (tm.walk_blocked(cx + dx, cy) or tm.walk_blocked(cx, cy + dy)):
                continue
            ng = g + c
            if ng < cost.get((nx, ny), 1e18):
                cost[(nx, ny)] = ng
                came[(nx, ny)] = cur
                h = math.hypot(gx - nx, gy - ny)
                heapq.heappush(open_heap, (ng + h, ng, (nx, ny)))
    if goal not in came:
        # partial path toward the closest explored node
        best = min(came, key=lambda n: math.hypot(gx - n[0], gy - n[1]))
        goal = best
    path = []
    n = goal
    while n is not None:
        path.append(n)
        n = came[n]
    path.reverse()
    return path


def _nearest_open(tm, t, rmax=5):
    x, y = t
    for r in range(1, rmax + 1):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) == r and not tm.walk_blocked(x + dx, y + dy):
                    return (x + dx, y + dy)
    return None
