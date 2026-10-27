"""Chooses and blends character animations from the *simulated* movement state.

Gameplay decides the state (IDLE, RUN, JUMP...); this class only decides how
to show it.  Locomotion clips are played at a rate proportional to the real
ground speed so the feet do not slide.
"""

from ...sim.character import MoveState

STATE_TO_CLIP = {
    MoveState.IDLE: "Idle",
    MoveState.WALK: "Walk",
    MoveState.RUN: "Run",
    MoveState.JUMP: "Jump",
    MoveState.FALL: "Fall",
    MoveState.LAND: "Land",
    MoveState.TUMBLE: "Fall",
    MoveState.RESPAWNING: "Idle",
    MoveState.ELIMINATED: "Elimination",
    MoveState.VICTORY: "Victory",
}

BLEND_TIME = {
    "Jump": 0.06,
    "Land": 0.05,
    "Fall": 0.15,
    "Elimination": 0.2,
}
DEFAULT_BLEND = 0.12


class AnimationController:
    def __init__(self, actor, meta):
        self.actor = actor
        self.meta = meta  # from bonk_character.json
        self.available = set(actor.getAnimNames())
        self.current = None
        self.weights = {}  # clip -> current blend weight
        self.fading_out = set()
        self.blend_time = DEFAULT_BLEND
        actor.enableBlend()
        self.history = []  # (clip) changes, used by tests

    def clip_for(self, state):
        return STATE_TO_CLIP.get(state, "Idle")

    def update(self, state, ground_speed, dt):
        clip = self.clip_for(state)
        if clip not in self.available:
            clip = "Idle"
        if clip != self.current:
            self._switch(clip)
        self._set_rate(clip, ground_speed)
        self._blend(dt)

    def _switch(self, clip):
        prev = self.current
        self.current = clip
        self.history.append(clip)
        del self.history[:-50]
        self.blend_time = BLEND_TIME.get(clip, DEFAULT_BLEND)
        info = self.meta.get(clip, {})
        if info.get("loop", True):
            if clip not in self.weights:
                self.actor.loop(clip)
        else:
            self.actor.play(clip)  # one-shot; holds its last frame
        self.weights.setdefault(clip, 0.0)
        if prev is not None:
            self.fading_out.add(prev)
        self.fading_out.discard(clip)

    def _set_rate(self, clip, speed):
        native = self.meta.get(clip, {}).get("native_speed", 0.0)
        if native > 0.0:
            rate = max(0.6, min(2.4, speed / native))
            self.actor.setPlayRate(rate, clip)

    def _blend(self, dt):
        step = 1.0 if self.blend_time <= 0 else dt / self.blend_time
        cur = self.current
        self.weights[cur] = min(1.0, self.weights.get(cur, 0.0) + step)
        for clip in list(self.fading_out):
            w = self.weights.get(clip, 0.0) - step
            if w <= 0.0:
                self.fading_out.discard(clip)
                self.weights.pop(clip, None)
                self.actor.stop(clip)
                self.actor.setControlEffect(clip, 0.0)
            else:
                self.weights[clip] = w
        total = sum(self.weights.values()) or 1.0
        for clip, w in self.weights.items():
            self.actor.setControlEffect(clip, w / total)
