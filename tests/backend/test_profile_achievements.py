"""Challenges about the player's page (profile_achievements.py): "Edit your Bio" (user, 2026-11-26)."""

from backend import profile_achievements as pa
from backend.achievements import RULES
from backend.combat_achievements import COMBAT_RULES
from backend.db import open_db
from backend.icons import RULE_IDS
from backend.models import NakamaAccount, Player, PlayerProfile
from sqlalchemy import select


def _card(items, rule):
    return next(i for i in items if i["id"] == rule.id)


def test_edit_your_bio_is_a_full_challenge():
    """Every challenge counts (user, 2026-11-28: "make the bio count, and other challenges too")."""
    r = pa.BIO_RULE
    assert (r.name, r.period, r.counted, r.group) == ("Edit your Bio", "game", True, "Profile")
    assert r.id not in {x.id for x in RULES + COMBAT_RULES} and r.id in RULE_IDS  # its own id; an admin can give it an icon
    assert all(x.counted for x in RULES + COMBAT_RULES + pa.PROFILE_RULES if not x.meta)
    assert pa.COUNTED_RULES[len(RULES)] is r  # first of the cards put on top of the replay answer


def test_complete_once_the_page_has_a_bio(tmp_path):
    _, sm = open_db(tmp_path / "b.db", 0)
    with sm() as db:
        db.add_all([Player(user_id=u, name=u, first_seen_at="t", last_seen_at="t") for u in ("p1", "p2", "p3", "p4")])
        db.add(PlayerProfile(user_id="p1", discord_id="d1", bio="Pew pew", show_avatar=True, linked_at="t", updated_at="2026-11-20T10:00:00"))
        db.add(PlayerProfile(user_id="p2", discord_id="d2", bio="   ", show_avatar=True, linked_at="t", updated_at="t"))  # blank: not done
        db.commit()
        done, blank, none = (_card(pa.player_items(db, u), pa.BIO_RULE) for u in ("p1", "p2", "p3"))
        entry = _card(pa.catalogue(db), pa.BIO_RULE)
    assert (done["progress"], done["unlocked_at"], done["counted"]) == (1.0, "2026-11-20", True)
    assert blank["progress"] == none["progress"] == 0.0 and none["unlocked_at"] is None
    assert entry["unlocked_share"] == 0.25 and "progress" not in entry  # one of four players


def test_edit_your_bio_is_won_or_not(tmp_path):
    _, sm = open_db(tmp_path / "c.db", 0)
    with sm() as db:
        db.add(Player(user_id="p1", name="p1", first_seen_at="t", last_seen_at="t"))
        db.add(PlayerProfile(user_id="p1", discord_id="d1", bio="Hi", show_avatar=True, linked_at="t", updated_at="2026-11-26T10:00:00"))
        db.commit()
        item = _card(pa.player_items(db, "p1"), pa.BIO_RULE)
    assert (item["binary"], item["tier"]) == (True, "crown")


def test_george_league_specials_are_full_challenges():
    """The George League Specials (user, 2026-11-27): Rookie League only, from the league's own site; they count as full
    challenges (user, same day), Edit your Bio too since 2026-11-28."""
    assert [r.id for r in pa.LEAGUE_RULES] == [280, 281, 282, 283, 284]
    for r in pa.LEAGUE_RULES:
        assert (r.period, r.counted, r.binary, r.group) == ("game", True, True, "George League")
        assert r.id not in {x.id for x in RULES + COMBAT_RULES} and r.id in RULE_IDS
        assert "Rookie" in r.description
    assert pa.LEAGUE_RULE.name == "Join Echo Combat George League"


def test_league_cards_follow_the_players_discord_account(tmp_path):
    from backend import league
    _, sm = open_db(tmp_path / "l.db", 0)
    with sm() as db:
        db.add_all([Player(user_id=u, name=u, first_seen_at="t", last_seen_at="t")
                    for u in ("123456789012345678", "p2", "p3", "p4")])  # a recent replay player's id IS the Discord id
        db.add(NakamaAccount(user_id="n2", discord_id="223456789012345678", username="n2", display_name=None, first_seen_at="t",
                             last_seen_at="t", replay_user_id="p2", link="player_id"))  # p2: linked by the Echo match list
        db.commit()
    # p1 is in the league and on a team, p2 in the league only, p3 nowhere; one member has no page here
    league.store(sm, league.Rosters(league={"123456789012345678", "223456789012345678", "999999999999999999"},
                                    on_team={"123456789012345678"}), now="2026-11-27T10:00:00")
    with sm() as db:
        one = {i["id"]: i for i in pa.player_items(db, "123456789012345678")}
        two = {i["id"]: i for i in pa.player_items(db, "p2")}
        three = {i["id"]: i for i in pa.player_items(db, "p3")}
        shares = {i["id"]: i["unlocked_share"] for i in pa.catalogue(db)}
    L, T = pa.LEAGUE_RULE.id, pa.LEAGUE_TEAM_RULE.id
    assert (one[L]["tier"], one[L]["unlocked_at"], one[T]["tier"]) == ("crown", "2026-11-27", "crown")
    assert (two[L]["progress"], two[T]["progress"]) == (1.0, 0.0)
    assert three[L]["progress"] == three[T]["progress"] == 0.0
    assert (shares[L], shares[T]) == (0.5, 0.25)  # 2 / 1 of the 4 players here; the member without a page is not counted
    assert one[L]["rules"] == pa.LEAGUE_NOTES


def test_won_league_cards_count_in_totals_ranking_and_medal_collector(tmp_path):
    """A won George League card is one more challenge fully complete (user, 2026-11-27): in the player's totals, the
    ranking's progress and average, and Medal Collector (one more challenge counted)."""
    from backend import league
    from backend.achievements import achiever_facts
    mc = pa._COLLECTOR_RULE
    _, sm = open_db(tmp_path / "w.db", 0)
    with sm() as db:
        db.add_all([Player(user_id=u, name=u, first_seen_at="t", last_seen_at="t") for u in ("123456789012345678", "p2")])
        db.commit()
    league.store(sm, league.Rosters(league={"123456789012345678"}, on_team={"123456789012345678"}), now="2026-11-27T10:00:00")
    with sm() as db:
        items = pa.player_items(db, "123456789012345678")
        extra = pa.profile_progress(db)
        pid1, pid2 = (db.scalar(select(Player.id).where(Player.user_id == u)) for u in ("123456789012345678", "p2"))
    assert extra == {pid1: [0.0, 1.0, 1.0, 0.0, 0.0, 0.0]}  # no bio; joined and on a team; p2 is not in the league

    # the player's own answer: Medal Collector at 4 of its first 5 -> 6 with the two league cards
    collector = {"id": mc.id, "group": mc.group, "counted": True, "progress": pa._collector(4), "count": 4, "tier": None}
    result = {"total": len(RULES), "completed": 3, "overall": 0.5}
    out, cards = pa.counted_answer(result, [collector] + items)
    assert out["total"] == len(RULES) + len(pa.PROFILE_RULES) and out["completed"] == 3 + 2
    assert cards[0]["count"] == 6 and cards[0]["tier"] == "bronze" and cards[0]["progress"] == pa._collector(6)
    expected = (0.5 * len(RULES) - pa._collector(4) + pa._collector(6) + 2) / (len(RULES) + 6)
    assert out["overall"] == round(expected, 4) and result["total"] == len(RULES)  # the cached one is not changed

    # the ranking: the same two cards appended, in the average and in Medal Collector
    index = pa._COLLECTOR
    base = [0.0] * len(RULES)
    base[index] = pa._collector(4)
    data = {"rows": [(pid1, 20, 0.1), (pid2, 20, 0.1)], "progress": {pid1: base, pid2: list(base)}, "recent": []}
    ranked = pa.with_league(data, extra)
    one, two = ranked["progress"][pid1], ranked["progress"][pid2]
    league = slice(len(RULES), len(RULES) + 6)  # Edit your Bio, the league cards; the Combat cards come after them
    assert one[league] == [0.0, 1.0, 1.0, 0.0, 0.0, 0.0] and one[index] == pa._collector(6) and two[index] == pa._collector(4)
    assert len(one) == len(two) == len(pa.COUNTED_RULES) and data["progress"][pid1] is base  # the cached ranking is not changed
    rows = dict((p, o) for p, _, o in ranked["rows"])
    assert rows[pid1] > rows[pid2] == round(0.1 * len(RULES) / len(pa.COUNTED_RULES), 4)
    facts = achiever_facts(one, pa.COUNTED_RULES)
    assert facts["completed"] == 2 and facts["total"] == len(pa.COUNTED_RULES)
    assert all(pa._collector_count(pa._collector(n)) == n for n in range(0, 75))  # the count comes back from the progress


def test_combat_cards_count_in_the_ranking_and_medal_collector():
    """The Combat challenges count (user, 2026-11-27: "Make Combat count"): added on top of the replay ranking, in the
    average and Medal Collector (a ladder from silver on); a player with reports but no replay game joins it once."""
    from backend.achievements import achiever_facts

    index = pa._COLLECTOR
    n = len(COMBAT_RULES)
    base = [0.0] * len(RULES)
    base[index] = pa._collector(4)
    data = {"rows": [(1, 20, 0.1)], "progress": {1: base}, "recent": []}
    cards = [1.0, 1.0] + [0.0] * (n - 2)
    combat = {1: (cards, 3, 7, True), 2: (cards, 2, 5, True), 3: (cards, 2, 5, False), 4: ([0.0] * n, 0, 0, True)}
    ranked = pa.with_league(data, {}, combat)
    rows = {p: (g, o) for p, g, o in ranked["rows"]}
    assert set(rows) == {1, 2}  # 3 is a merged id (its main row 2 is listed), 4 has no counted Combat game
    one = ranked["progress"][1]
    assert one[-n:] == cards and one[index] == pa._collector(7) and len(one) == len(pa.COUNTED_RULES)
    assert rows[1] == (20, round((0.1 * len(RULES) - pa._collector(4) + pa._collector(7) + 2) / len(pa.COUNTED_RULES), 4))
    assert rows[2][0] == 5 and ranked["progress"][2][index] == pa._collector(2)
    assert achiever_facts(one, pa.COUNTED_RULES)["completed"] == 2

    # the player's own answer: a Combat ladder at silver adds to Medal Collector, a crown also to "completed"
    mc = RULES[index]
    ladder = next(r for r in COMBAT_RULES if r.levels and not r.binary)
    silver = {"id": ladder.id, "counted": True, "progress": 0.5, "count": ladder.levels[1]}
    crown = {"id": ladder.id, "counted": True, "progress": 1.0, "count": ladder.levels[-1]}
    collector = {"id": mc.id, "counted": True, "progress": pa._collector(4), "count": 4, "tier": None}
    out, items = pa.counted_answer({"total": len(RULES), "completed": 3, "overall": 0.5}, [collector, silver, crown])
    assert items[0]["count"] == 6 and out["completed"] == 4 and out["total"] == len(RULES) + 2


def test_a_bio_counts_in_totals_ranking_and_medal_collector(tmp_path):
    """Edit your Bio is a full challenge (user, 2026-11-28): the bio the page shows, a bot-linked one or one written on
    My profile (kept by Discord id), on every merged id, in the player's totals and the ranking."""
    from backend.models import DiscordProfile, PlayerAlias
    did = "123456789012345678"
    _, sm = open_db(tmp_path / "bio.db", 0)
    with sm() as db:
        db.add_all([Player(user_id=u, name=u, first_seen_at="t", last_seen_at="t") for u in ("p1", "p1b", did, "p3")])
        db.add(PlayerAlias(alias_user_id="p1b", main_user_id="p1", created_at="t"))  # p1b merged into p1
        db.add(PlayerProfile(user_id="p1", discord_id="d1", bio="Pew pew", show_avatar=True, linked_at="t", updated_at="2026-11-20T10:00:00"))
        db.add(DiscordProfile(discord_id=did, bio="protostar support", show_avatar=True, updated_at="2026-11-21T10:00:00"))
        db.add(DiscordProfile(discord_id="999999999999999999", bio="no page here", show_avatar=True, updated_at="t"))
        db.commit()
        pids = {u: db.scalar(select(Player.id).where(Player.user_id == u)) for u in ("p1", "p1b", did, "p3")}
        merged = _card(pa.player_items(db, "p1b"), pa.BIO_RULE)
        own = _card(pa.player_items(db, did), pa.BIO_RULE)
        extra = pa.profile_progress(db)
    assert (merged["unlocked_at"], own["unlocked_at"]) == ("2026-11-20", "2026-11-21")
    bio = [1.0] + [0.0] * len(pa.LEAGUE_RULES)
    assert extra == {pids["p1"]: bio, pids["p1b"]: bio, pids[did]: bio}  # p3 has none; the third bio has no page

    out, _ = pa.counted_answer({"total": len(RULES), "completed": 0, "overall": 0.0}, [own])
    assert (out["total"], out["completed"]) == (len(RULES) + 1, 1)  # DinkatorBoi's case: 1 complete, not 0
    index = pa._COLLECTOR
    data = {"rows": [(pids[did], 5, 0.0), (pids["p3"], 5, 0.0)], "progress": {pids[did]: [0.0] * len(RULES), pids["p3"]: [0.0] * len(RULES)}}
    ranked = pa.with_league(data, extra)
    assert ranked["progress"][pids[did]][len(RULES)] == 1.0 and ranked["progress"][pids[did]][index] == pa._collector(1)
    rows = {p: o for p, _, o in ranked["rows"]}
    assert rows[pids[did]] > rows[pids["p3"]] == 0.0
