"""Daily missions: three deterministic missions per day, tracked from match results."""
import random

from ilbrawl.progression import profile as _p

CLASSES = ["tank", "assassin", "marksman", "support", "controller"]


def ensure_daily(profile):
    d = profile.data
    today = _p.today_str()
    if d["missions"].get("date") == today and d["missions"].get("list"):
        return False
    templates = profile.gd.progression.get("missions", [])
    rng = random.Random("missions-" + today)
    chosen = rng.sample(templates, k=min(3, len(templates)))
    lst = []
    for tpl in chosen:
        m = {"type": tpl["type"], "target": rng.choice(tpl["targets"]), "progress": 0, "claimed": False,
             "coins": tpl["coins"], "xp": tpl["xp"], "param": None}
        if tpl["type"] == "play_mode":
            m["param"] = rng.choice(profile.gd.mode_order)
        elif tpl["type"] == "win_with_class":
            m["param"] = rng.choice(CLASSES)
        lst.append(m)
    d["missions"] = {"date": today, "list": lst}
    return True


def _increment(m, result, gd):
    p = result["player"]
    t = m["type"]
    won = result["outcome"] == "win"
    if t == "play_matches":
        return 1
    if t == "win_matches":
        return 1 if won else 0
    if t == "deal_damage":
        return int(p.get("damage", 0))
    if t == "eliminate":
        return p.get("kills", 0)
    if t == "use_super":
        return p.get("supers", 0)
    if t == "heal_amount":
        return int(p.get("healing", 0))
    if t == "play_mode":
        return 1 if result["mode"] == m["param"] else 0
    if t == "collect_gems":
        return p.get("gems", 0)
    if t == "score_goals":
        return p.get("goals", 0)
    if t == "win_with_class":
        return 1 if won and gd.characters[result["char"]]["class"] == m["param"] else 0
    return 0


def apply_result(profile, result):
    ensure_daily(profile)
    completed = []
    for i, m in enumerate(profile.data["missions"]["list"]):
        if m["progress"] >= m["target"]:
            continue
        m["progress"] = min(m["target"], m["progress"] + _increment(m, result, profile.gd))
        if m["progress"] >= m["target"]:
            completed.append(i)
    return completed


def claim(profile, index):
    lst = profile.data["missions"]["list"]
    if not (0 <= index < len(lst)):
        return None
    m = lst[index]
    if m["claimed"] or m["progress"] < m["target"]:
        return None
    m["claimed"] = True
    profile.data["coins"] += m["coins"]
    profile.add_xp(m["xp"])
    profile.save()
    return m


def claimable_count(profile):
    return sum(1 for m in profile.data["missions"]["list"] if not m["claimed"] and m["progress"] >= m["target"])


def describe(m, i18n):
    params = {"n": m["target"]}
    if m["type"] == "play_mode":
        params["mode"] = i18n.t("mode.%s.name" % m["param"])
    elif m["type"] == "win_with_class":
        params["cls"] = i18n.t("class.%s" % m["param"])
    return i18n.t("mission." + m["type"], **params)
