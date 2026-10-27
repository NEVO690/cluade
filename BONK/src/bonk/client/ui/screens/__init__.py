"""All screens of the game."""

from .cosmetics import ShopScreen, SkinsScreen
from .ingame import HudScreen, PauseScreen, ResultsScreen, VictoryScreen
from .menus import LobbyScreen, LoadingScreen, MainMenu, MapSelect, ModeSelect, SplashScreen
from .multiplayer import MultiplayerScreen
from .progress import (AchievementsScreen, LevelsScreen, ProfileScreen, QuestsScreen, RanksScreen,
                       TitlesScreen)
from .settings import SettingsScreen

ALL_SCREENS = (SplashScreen, MainMenu, ModeSelect, LobbyScreen, MapSelect, LoadingScreen, HudScreen, PauseScreen,
               VictoryScreen, ResultsScreen, ShopScreen, SkinsScreen, ProfileScreen, LevelsScreen, RanksScreen,
               TitlesScreen, QuestsScreen, AchievementsScreen, SettingsScreen, MultiplayerScreen)


def register_all(app):
    for cls in ALL_SCREENS:
        app.screens.register(cls(app))
