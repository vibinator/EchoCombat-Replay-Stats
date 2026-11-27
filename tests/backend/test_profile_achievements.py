"""Challenges about the player's page (profile_achievements.py): "Edit your Bio" (user, 2026-11-26)."""

from backend import profile_achievements as pa
from backend.achievements import RULES
from backend.combat_achievements import COMBAT_RULES
from backend.db import open_db
from backend.icons import RULE_IDS
from backend.models import NakamaAccount, Player, PlayerProfile


def _card(items, rule):
    return next(i for i in items if i["id"] == rule.id)


def test_edit_your_bio_is_a_special_out_of_every_total():
    r = pa.BIO_RULE
    assert (r.name, r.period, r.counted, r.group) == ("Edit your Bio", "game", False, "Profile")
    assert r.id not in {x.id for x in RULES + COMBAT_RULES} and r.id in RULE_IDS  # its own id; an admin can give it an icon


def test_complete_once_the_page_has_a_bio(tmp_path):
    _, sm = open_db(tmp_path / "b.db", 0)
    with sm() as db:
        db.add_all([Player(user_id=u, name=u, first_seen_at="t", last_seen_at="t") for u in ("p1", "p2", "p3", "p4")])
        db.add(PlayerProfile(user_id="p1", discord_id="d1", bio="Pew pew", show_avatar=True, linked_at="t", updated_at="2026-11-20T10:00:00"))
        db.add(PlayerProfile(user_id="p2", discord_id="d2", bio="   ", show_avatar=True, linked_at="t", updated_at="t"))  # blank: not done
        db.commit()
        done, blank, none = (_card(pa.player_items(db, u), pa.BIO_RULE) for u in ("p1", "p2", "p3"))
        entry = _card(pa.catalogue(db), pa.BIO_RULE)
    assert (done["progress"], done["unlocked_at"], done["counted"]) == (1.0, "2026-11-20", False)
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


def test_george_league_specials_are_out_of_every_total():
    """Join Echo Combat George League / Join a George League Team (user, 2026-11-27): Specials from the league's roster."""
    for r in (pa.LEAGUE_RULE, pa.LEAGUE_TEAM_RULE):
        assert (r.period, r.counted, r.binary, r.group) == ("game", False, True, "George League")
        assert r.id not in {x.id for x in RULES + COMBAT_RULES} and r.id in RULE_IDS
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
    # p1 is on the league and a team, p2 on the league only, p3 nowhere; one member has no page here
    league.store(sm, {"123456789012345678", "223456789012345678", "999999999999999999"}, {"123456789012345678"}, now="2026-11-27T10:00:00")
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
