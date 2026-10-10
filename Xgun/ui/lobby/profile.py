from ui.lobby.common import Tab, header


class ProfileTab(Tab):
    def build(self):
        header(self.root, "ProfileTab")
