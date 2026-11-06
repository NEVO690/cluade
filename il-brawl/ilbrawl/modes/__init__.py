"""Game mode registry."""


def create_mode(mode_id, world, cfg):
    from ilbrawl.modes.gem_collection import GemCollection
    from ilbrawl.modes.goal_rush import GoalRush
    from ilbrawl.modes.solo_survival import SoloSurvival
    from ilbrawl.modes.team_survival import TeamSurvival
    from ilbrawl.modes.zone_control import ZoneControl
    classes = {
        "gem_collection": GemCollection,
        "solo_survival": SoloSurvival,
        "team_survival": TeamSurvival,
        "goal_rush": GoalRush,
        "zone_control": ZoneControl,
    }
    return classes[mode_id](world, cfg)
