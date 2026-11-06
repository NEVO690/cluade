"""Tiered achievements based on lifetime statistics."""


def stat_value(profile, stat):
    if stat == "characters_unlocked":
        return len(profile.data["unlocked"])
    return profile.data["stats"].get(stat, 0)


def entries(profile):
    """Yield (definition, tier_claimed, next_threshold, current_value, claimable, reward)."""
    out = []
    for a in profile.gd.progression.get("achievements", []):
        tier = profile.data["achievements"].get(a["id"], 0)
        val = stat_value(profile, a["stat"])
        done = tier >= len(a["thresholds"])
        nxt = None if done else a["thresholds"][tier]
        reward = None if done else a["gems"][tier]
        out.append((a, tier, nxt, val, (not done) and val >= nxt, reward))
    return out


def newly_claimable(profile):
    return [e[0]["id"] for e in entries(profile) if e[4]]


def claim(profile, ach_id):
    for a, tier, nxt, val, ok, reward in entries(profile):
        if a["id"] == ach_id and ok:
            profile.data["achievements"][ach_id] = tier + 1
            profile.data["gems"] += reward
            profile.save()
            return reward
    return None


def claimable_count(profile):
    return sum(1 for e in entries(profile) if e[4])
