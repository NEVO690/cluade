"""Local bot AI (no network services or language models involved)."""

from .bot_controller import BotController
from .bot_difficulty import PROFILES, profile


def make_bot(difficulty, rng, world):
    return BotController(profile(difficulty), rng, world)


__all__ = ["BotController", "PROFILES", "profile", "make_bot"]
