import datetime as dt

from progression.rewards import MatchSummary


def test_match_rewards_award_xon_and_xp(services):
    acc = services.ensure_player("Grinder")
    start = services.wallet.balance(acc.id)
    out = services.progression.apply_match(acc.id, MatchSummary(placement=1, players=20, eliminations=4,
                                                                damage=600, chests=3, survive_secs=420))
    assert out.xon > 0 and out.xp > 0
    assert services.wallet.balance(acc.id) == start + out.xon
    stats = services.progression.stats(acc.id)
    assert stats["wins"] == 1 and stats["eliminations"] == 4 and stats["matches"] == 1
    assert "banner_crown" in out.unlocked_items          # first-win milestone
    assert services.locker.owns(acc.id, "banner_crown")
    assert services.progression.recent_matches(acc.id)[0]["placement"] == 1


def test_battle_pass_tiers_unlock_items_once(services):
    acc = services.ensure_player("Pass")
    services.progression.add_xp(acc.id, 8 * 1000)       # level 9 -> tiers 1..8 (and 9)
    assert services.locker.owns(acc.id, "outfit_volt_brawler")
    balance = services.wallet.balance(acc.id)
    services.progression.sync_battle_pass(acc.id)       # idempotent
    assert services.wallet.balance(acc.id) == balance


def test_daily_quests_progress_and_complete(services):
    acc = services.ensure_player("Quester")
    day = dt.date(2026, 10, 10)
    quests = services.progression.daily_quests(acc.id, day)
    assert len(quests) == 4
    big = MatchSummary(placement=1, players=20, eliminations=10, damage=5000, chests=10, survive_secs=900,
                       healed=500, pickaxe_hits=50, glide_secs=60, sniper_hits=5)
    out = services.progression.apply_match(acc.id, big, date=day)
    out2 = services.progression.apply_match(acc.id, big, date=day)
    done = services.progression.daily_quests(acc.id, day)
    # every quest except "play 2 matches" completes after one big match; all after two
    assert all(q.complete and q.claimed for q in done)
    assert len(out.completed_quests) + len(out2.completed_quests) == 4
