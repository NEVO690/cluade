"""Bot behaviour profiles.

Every bot uses the same body and the same top speed as the player.  The
profiles change *behaviour*: how often the bot re-thinks, how far it looks
ahead, how precisely it times jumps, whether it predicts obstacles, how
much it hesitates, and how wild its line through the course is.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BotProfile:
    name: str
    decision_interval: float  # seconds between re-plans (reaction time)
    lookahead: float  # metres along the route used to pick a target
    jump_jitter: float  # random error (m) in where a jump is triggered
    misjudge_chance: float  # chance per gap of not spotting it in time
    hazard_awareness: float  # chance of predicting a given hazard encounter
    hesitation_chance: float  # chance per second of a short pause
    walk_chance: float  # chance per decision of walking instead of running
    lane_noise: float  # how much the preferred lateral line wanders (0-1)
    tile_safety: float  # chance of noticing that a tile is about to vanish
    patience: float  # seconds willing to wait for an obstacle before trying anyway
    random_jump_rate: float = 0.0  # spontaneous jumps per second (chaotic)
    zigzag: float = 0.0  # metres of weaving
    aggression: float = 0.0  # tendency to bump into nearby opponents
    sweeper_lead: float = 0.16  # how early it jumps over a sweeping bar (s)


EASY = BotProfile("EASY", decision_interval=0.30, lookahead=2.6, jump_jitter=0.32,
                  misjudge_chance=0.10, hazard_awareness=0.35, hesitation_chance=0.10,
                  walk_chance=0.22, lane_noise=0.6, tile_safety=0.45, patience=1.2,
                  sweeper_lead=0.20)
NORMAL = BotProfile("NORMAL", decision_interval=0.15, lookahead=3.6, jump_jitter=0.16,
                    misjudge_chance=0.03, hazard_awareness=0.75, hesitation_chance=0.03,
                    walk_chance=0.04, lane_noise=0.35, tile_safety=0.85, patience=2.5)
HARD = BotProfile("HARD", decision_interval=0.05, lookahead=4.6, jump_jitter=0.05,
                  misjudge_chance=0.0, hazard_awareness=1.0, hesitation_chance=0.0,
                  walk_chance=0.0, lane_noise=0.12, tile_safety=1.0, patience=4.0,
                  sweeper_lead=0.14)
CHAOTIC = BotProfile("CHAOTIC", decision_interval=0.10, lookahead=3.4, jump_jitter=0.22,
                     misjudge_chance=0.03, hazard_awareness=0.6, hesitation_chance=0.0,
                     walk_chance=0.0, lane_noise=0.9, tile_safety=0.8, patience=1.0,
                     random_jump_rate=0.45, zigzag=1.3, aggression=0.7)

PROFILES = {p.name: p for p in (EASY, NORMAL, HARD, CHAOTIC)}
DIFFICULTY_NAMES = ("EASY", "NORMAL", "HARD", "CHAOTIC", "MIXED")


def profile(name):
    return PROFILES[name.upper()]


def mixed_lineup(count, rng):
    """Difficulty for each bot when the player picks MIXED."""
    pool = ["EASY"] * 3 + ["NORMAL"] * 5 + ["HARD"] * 2 + ["CHAOTIC"] * 2
    return [rng.choice(pool) for _ in range(count)]
