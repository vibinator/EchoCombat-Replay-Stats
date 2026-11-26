"""Challenges about the player's page (profile_achievements.py): "Edit your Bio" (user, 2026-11-26)."""

from backend import profile_achievements as pa
from backend.achievements import RULES
from backend.combat_achievements import COMBAT_RULES
from backend.db import open_db
from backend.icons import RULE_IDS
from backend.models import Player, PlayerProfile


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
        [done] = pa.player_items(db, "p1")
        [blank] = pa.player_items(db, "p2")
        [none] = pa.player_items(db, "p3")
        [entry] = pa.catalogue(db)
    assert (done["progress"], done["unlocked_at"], done["counted"]) == (1.0, "2026-11-20", False)
    assert blank["progress"] == none["progress"] == 0.0 and none["unlocked_at"] is None
    assert entry["unlocked_share"] == 0.25 and "progress" not in entry  # one of four players


def test_edit_your_bio_is_won_or_not(tmp_path):
    _, sm = open_db(tmp_path / "c.db", 0)
    with sm() as db:
        db.add(Player(user_id="p1", name="p1", first_seen_at="t", last_seen_at="t"))
        db.add(PlayerProfile(user_id="p1", discord_id="d1", bio="Hi", show_avatar=True, linked_at="t", updated_at="2026-11-26T10:00:00"))
        db.commit()
        [item] = pa.player_items(db, "p1")
    assert (item["binary"], item["tier"]) == (True, "crown")
