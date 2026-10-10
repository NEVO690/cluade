"""Random cosmetic loadouts for bots (purely visual)."""
from __future__ import annotations

import random

PICKAXES = ["pickaxe_iron_pick", "pickaxe_spray_hook", "pickaxe_frostbite", "pickaxe_gearbreaker", "pickaxe_circuit_splitter",
            "pickaxe_dragonfang"]
OUTFITS = ["outfit_vex_runner", "outfit_tidal_drifter", "outfit_glitch_medic", "outfit_volt_brawler", "outfit_frost_warden",
           "outfit_nova_sentinel", "outfit_ember_ronin"]
BACKPACKS = ["backpack_daypack", "backpack_explorer_roll", "backpack_crystal_core", "backpack_boombox", "backpack_jet_canister",
             "backpack_ember_quiver", None]
GLIDERS = ["glider_wing_sail", "glider_patchwork", "glider_kite_ray", "glider_delta_jet", "glider_phoenix"]


def random_loadout(rng: random.Random) -> dict:
    """Bots wear random cosmetics — purely visual, no gameplay effect."""
    return {"outfit": rng.choice(OUTFITS), "backpack": rng.choice(BACKPACKS), "pickaxe": rng.choice(PICKAXES),
            "glider": rng.choice(GLIDERS)}
