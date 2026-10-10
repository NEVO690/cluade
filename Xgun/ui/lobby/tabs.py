"""Tab registry for the lobby."""
from __future__ import annotations


def create(name: str, lobby, parent):
    from ui.lobby.battlepass import BattlePassTab
    from ui.lobby.friends import FriendsTab
    from ui.lobby.locker import LockerTab
    from ui.lobby.play import PlayTab
    from ui.lobby.profile import ProfileTab
    from ui.lobby.quests import QuestsTab
    from ui.lobby.settings_tab import SettingsTab
    from ui.lobby.shop import ShopTab
    from ui.lobby.tiktok import TikTokTab
    return {"PLAY": PlayTab, "LOCKER": LockerTab, "XON SHOP": ShopTab, "BATTLE PASS": BattlePassTab, "TIKTOK": TikTokTab,
            "FRIENDS": FriendsTab, "PROFILE": ProfileTab, "QUESTS": QuestsTab, "SETTINGS": SettingsTab}[name](lobby, parent)
