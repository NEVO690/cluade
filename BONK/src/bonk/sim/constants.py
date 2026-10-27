"""Physics and movement tuning shared by the client, the bots and the server.

All distances are in metres, times in seconds.  The world is Z-up and every
course runs roughly along +Y (start at low Y, finish at high Y).
"""

TICK_RATE = 60
DT = 1.0 / TICK_RATE

# Character body (a vertical cylinder).
CHAR_RADIUS = 0.42
CHAR_HEIGHT = 1.45

# Ground movement.
RUN_SPEED = 7.0
WALK_SPEED = 3.2
GROUND_ACCEL = 55.0
GROUND_DECEL = 45.0
AIR_ACCEL = 16.0
TURN_RATE = 14.0  # how fast the body yaw follows the movement direction (1/s)

# Vertical movement.
GRAVITY = 30.0
JUMP_SPEED = 10.0  # apex = v^2 / 2g = 1.67 m, air time on flat ground = 0.67 s
MAX_FALL_SPEED = 32.0
COYOTE_TIME = 0.10  # a jump is still allowed this long after walking off an edge
JUMP_BUFFER = 0.12  # a jump pressed this long before landing still triggers
STEP_HEIGHT = 0.32  # small ledges are climbed without jumping
GROUND_SNAP = 0.30  # stick to descending ramps / steps up to this distance
LAND_TIME = 0.14  # duration of the LAND state after touching down from a fall
HARD_LANDING_SPEED = 8.0  # only falls faster than this enter LAND

# Getting hit.
STUN_TIME = 0.75
STUN_CONTROL = 0.15  # fraction of normal acceleration while stunned
HEAD_BONK_SPEED = 8.5  # bounce speed when landing on another character's head
HEAD_BONK_STUN = 0.35

# Character-character pushing.
PUSH_STRENGTH = 0.5

# Respawn after falling in a "respawn" course.
RESPAWN_DELAY = 1.2
RESPAWN_GRACE = 1.0  # cannot be stunned right after respawning

# Derived values used by the course validator and the bots.
AIR_TIME_FLAT = 2.0 * JUMP_SPEED / GRAVITY
MAX_JUMP_HEIGHT = JUMP_SPEED * JUMP_SPEED / (2.0 * GRAVITY)
MAX_JUMP_DISTANCE_FLAT = RUN_SPEED * AIR_TIME_FLAT


def air_time_for_drop(drop):
    """Seconds from take-off until landing `drop` metres lower (negative = higher)."""
    # z(t) = v t - g t^2 / 2 = -drop  ->  g/2 t^2 - v t - drop = 0
    a = 0.5 * GRAVITY
    b = -JUMP_SPEED
    c = -drop
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return None  # target is higher than the jump apex
    return (-b + disc ** 0.5) / (2.0 * a)


def max_jump_distance(drop=0.0, speed=RUN_SPEED):
    """Horizontal reach of a running jump that lands `drop` metres lower."""
    t = air_time_for_drop(drop)
    if t is None:
        return 0.0
    return speed * t
