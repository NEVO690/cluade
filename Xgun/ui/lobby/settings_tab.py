from ui.lobby.common import Tab, header


class SettingsTab(Tab):
    def build(self):
        header(self.root, "SettingsTab")
