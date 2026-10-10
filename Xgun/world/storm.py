"""Shrinking safe zone ("the storm")."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

# (wait seconds, shrink seconds, target radius, damage per second outside)
DEFAULT_PHASES = [(75, 50, 380, 1), (50, 40, 240, 2), (40, 35, 140, 4), (35, 30, 75, 6), (30, 25, 35, 8),
                  (25, 25, 12, 10), (20, 25, 0, 14)]


@dataclass
class StormState:
    phase: int
    center: tuple[float, float]
    radius: float
    target_center: tuple[float, float]
    target_radius: float
    shrinking: bool
    time_left: float
    dps: float


class Storm:
    def __init__(self, rng: random.Random, is_land, start_radius: float = 720.0, phases=None, time_scale: float = 1.0):
        self.rng = rng
        self.is_land = is_land
        self.phases = phases or DEFAULT_PHASES
        self.time_scale = time_scale
        self.center = (0.0, 0.0)
        self.radius = start_radius
        self.phase = 0
        self.shrinking = False
        self.timer = self.phases[0][0] * time_scale
        self._start_center = self.center
        self._start_radius = self.radius
        self.target_center, self.target_radius = self._pick_next(0)
        self.dps = 0.5

    def _pick_next(self, phase: int):
        r_new = self.phases[phase][2]
        for _ in range(60):
            max_off = max(0.0, self.radius - r_new) * (0.85 if phase else 0.35)
            a = self.rng.uniform(0, 2 * math.pi)
            d = max_off * math.sqrt(self.rng.random())
            c = (self.center[0] + math.cos(a) * d, self.center[1] + math.sin(a) * d)
            if self.is_land(*c):
                return c, r_new
        return self.center, r_new

    def update(self, dt: float) -> list[str]:
        events = []
        if self.phase >= len(self.phases):
            return events
        self.timer -= dt
        wait, shrink, _, dps = self.phases[self.phase]
        if self.shrinking:
            t = 1 - max(0.0, self.timer) / (shrink * self.time_scale)
            self.radius = self._start_radius + (self.target_radius - self._start_radius) * t
            self.center = (self._start_center[0] + (self.target_center[0] - self._start_center[0]) * t,
                           self._start_center[1] + (self.target_center[1] - self._start_center[1]) * t)
            if self.timer <= 0:
                self.shrinking = False
                self.phase += 1
                events.append("storm_stopped")
                if self.phase < len(self.phases):
                    self.timer = self.phases[self.phase][0] * self.time_scale
                    self.target_center, self.target_radius = self._pick_next(self.phase)
                    events.append("storm_next")
        elif self.timer <= 0:
            self.shrinking = True
            self.dps = dps
            self._start_center, self._start_radius = self.center, self.radius
            self.timer = shrink * self.time_scale
            events.append("storm_shrinking")
        return events

    def outside(self, x: float, y: float) -> bool:
        return math.hypot(x - self.center[0], y - self.center[1]) > self.radius

    def distance_inside(self, x: float, y: float) -> float:
        return self.radius - math.hypot(x - self.center[0], y - self.center[1])

    def state(self) -> StormState:
        return StormState(self.phase, self.center, self.radius, self.target_center, self.target_radius, self.shrinking,
                          max(0.0, self.timer), self.dps)
