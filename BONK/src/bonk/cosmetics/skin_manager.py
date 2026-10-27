"""Which skins the player owns / has equipped, and whether locked ones can be bought."""


class SkinManager:
    def __init__(self, store, catalog):
        self.store = store
        self.catalog = catalog

    @property
    def _c(self):
        return self.store.data["cosmetics"]

    @property
    def owned(self):
        return list(self._c["owned_skins"])

    @property
    def equipped(self):
        sid = self._c["equipped_skin"]
        return sid if sid in self.catalog else "classic"

    def is_owned(self, skin_id):
        return skin_id in self._c["owned_skins"]

    def grant(self, skin_id):
        if skin_id not in self.catalog:
            raise KeyError(skin_id)
        if skin_id not in self._c["owned_skins"]:
            self._c["owned_skins"].append(skin_id)

    def revoke(self, skin_id):
        """Used only to roll back a purchase whose save failed."""
        if skin_id != "classic" and skin_id in self._c["owned_skins"]:
            self._c["owned_skins"].remove(skin_id)
            if self._c["equipped_skin"] == skin_id:
                self._c["equipped_skin"] = "classic"

    def equip(self, skin_id):
        if not self.is_owned(skin_id):
            raise PermissionError("skin %s is not owned" % skin_id)
        self._c["equipped_skin"] = skin_id

    def unmet_requirements(self, skin_id, level, rank_id, rank_order, completed_achievements):
        """List of human-readable reasons why a skin cannot be bought yet (empty = OK)."""
        skin = self.catalog.get(skin_id)
        reasons = []
        req = skin.unlock
        if "level" in req and level < int(req["level"]):
            reasons.append("Reach level %d" % int(req["level"]))
        if "rank" in req and rank_order(rank_id) < rank_order(req["rank"]):
            reasons.append("Reach %s rank" % req["rank"])
        if "achievement" in req and req["achievement"] not in completed_achievements:
            reasons.append("Unlock achievement '%s'" % req["achievement"])
        return reasons
