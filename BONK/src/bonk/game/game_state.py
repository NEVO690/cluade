"""Show-level states (one show = several rounds)."""


class GameState:
    LOBBY = "LOBBY"
    COUNTDOWN = "COUNTDOWN"
    ROUND_START = "ROUND_START"
    ROUND_ACTIVE = "ROUND_ACTIVE"
    ROUND_END = "ROUND_END"
    RESULTS = "RESULTS"
    GAME_OVER = "GAME_OVER"

    ALL = (LOBBY, COUNTDOWN, ROUND_START, ROUND_ACTIVE, ROUND_END, RESULTS, GAME_OVER)

    # Allowed transitions; anything else is a programming error.
    TRANSITIONS = {
        LOBBY: (COUNTDOWN,),
        COUNTDOWN: (ROUND_START, GAME_OVER),
        ROUND_START: (ROUND_ACTIVE, ROUND_END, GAME_OVER),
        ROUND_ACTIVE: (ROUND_END, GAME_OVER),
        ROUND_END: (RESULTS, GAME_OVER),
        RESULTS: (COUNTDOWN, GAME_OVER),
        GAME_OVER: (LOBBY,),
    }


class Outcome:
    QUALIFIED = "qualified"
    WINNER = "winner"
    ELIMINATED = "eliminated"
