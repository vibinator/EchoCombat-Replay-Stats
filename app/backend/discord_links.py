"""Which Discord account belongs to which replay player, in one place (user, 2026-11-25: links can be wrong or broken).

A player reaches a Discord account by the first of these that holds:
  profile    the bot's or an admin's link (PlayerProfile)
  player_id  a recent replay player's id IS the Discord id
  seen       the Echo account seen with the player on the match list (NakamaAccount)
  name       the one server member with the player's exact name (picture only, never edit rights; discord_names.py)
Only "profile" is stored by a person; the others are found again at every look, so deleting the stored link is not enough
to take an account off a player. An admin's unlink is therefore remembered as a block on that one pair (DiscordLinkBlock),
which every route obeys, the bot's included. Linking the pair by hand again lifts it.

A bot / admin link is exclusive both ways: the account is nobody else's and the player has no other account, whatever the
automatic routes say. Merged ids (D34) are one player: links and blocks of any of them count for the main player.
The bio and the picture choice belong to the Discord account (only it can write them), so they move with it.
"""

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from . import aliases, auth
from .db import utcnow
from .models import DiscordLinkBlock, DiscordProfile, NakamaAccount, Player, PlayerAlias, PlayerProfile


def main_id(db: Session, user_id: str) -> str:
    """A merged id (D34) means its main player."""
    alias = db.get(PlayerAlias, user_id)
    return alias.main_user_id if alias is not None else user_id


def profile_of(db: Session, main: str) -> PlayerProfile | None:
    """The bot / admin link of a player: its own, else one made for an id that was merged into it later."""
    own = db.get(PlayerProfile, main)
    return own or db.scalar(select(PlayerProfile).where(PlayerProfile.user_id.in_(aliases.ids_of(db, main)))
                            .order_by(PlayerProfile.linked_at.desc()).limit(1))


def blocks_of(db: Session, main: str) -> list[str]:
    """Discord ids an admin took off this player, newest first."""
    found = db.scalars(select(DiscordLinkBlock.discord_id).where(DiscordLinkBlock.user_id.in_(aliases.ids_of(db, main)))
                       .order_by(DiscordLinkBlock.created_at.desc())).all()
    return list(dict.fromkeys(found))


def blocked(db: Session, main: str, discord_id: str) -> bool:
    return db.scalar(select(DiscordLinkBlock.user_id).where(
        DiscordLinkBlock.discord_id == discord_id, DiscordLinkBlock.user_id.in_(aliases.ids_of(db, main))).limit(1)) is not None


def allowed(db: Session, main: str, discord_id: str) -> bool:
    """Whether an automatic route may give this player this account: not unlinked by an admin, and neither of the two is
    linked to another by the bot / an admin."""
    mine = profile_of(db, main)
    if mine is not None and mine.discord_id != discord_id:
        return False
    owner = db.scalar(select(PlayerProfile.user_id).where(PlayerProfile.discord_id == discord_id))
    if owner is not None and main_id(db, owner) != main:
        return False
    return not blocked(db, main, discord_id)


def is_own_id(db: Session, main: str) -> bool:
    """A player whose id IS their Discord id, and may keep that account."""
    return (auth.is_discord_id(main) and db.scalar(select(Player.id).where(Player.user_id == main)) is not None
            and allowed(db, main, main))


def seen_discord(db: Session, main: str) -> str | None:
    """The Discord account seen with this player (or one of its merged ids) on the Echo match list, newest first."""
    for d in db.scalars(select(NakamaAccount.discord_id).where(
            NakamaAccount.replay_user_id.in_(aliases.ids_of(db, main)), NakamaAccount.discord_id.is_not(None))
            .order_by(NakamaAccount.last_seen_at.desc())).all():
        if allowed(db, main, d):
            return d
    return None


def name_match_ok(db: Session, main: str, name: str, discord_id: str) -> bool:
    """Whether the one member named like this player may lend it their picture: not linked by the bot / an admin, not taken
    off this player, and no other player has the name."""
    if db.scalar(select(PlayerProfile.user_id).where(PlayerProfile.discord_id == discord_id)) is not None:
        return False  # linked to a player: shown only there
    if blocked(db, main, discord_id):
        return False
    same_name = db.scalars(select(Player.user_id).where(func.lower(Player.name) == name.lower())).all()
    return len({main_id(db, u) for u in same_name} | {main}) == 1


def discord_of(db: Session, main: str) -> tuple[str, str] | None:
    """(Discord id, route) of a player, the name match left out."""
    profile = profile_of(db, main)
    if profile is not None:
        return profile.discord_id, "profile"
    if is_own_id(db, main):
        return main, "player_id"
    seen = seen_discord(db, main)
    return (seen, "seen") if seen else None


def account_link(db: Session, discord_id: str | None) -> tuple[str | None, str | None]:
    """(replay player, how) to store with an account of the match list: a bot / admin link first, then a replay player whose
    id IS the Discord id."""
    if not discord_id:
        return None, None
    linked = db.scalar(select(PlayerProfile).where(PlayerProfile.discord_id == discord_id))
    if linked is not None:
        main = main_id(db, linked.user_id)
        return (main, "profile") if profile_of(db, main) is linked else (None, None)  # a merge left the player two accounts
    if (db.scalar(select(Player.id).where(Player.user_id == discord_id)) is not None
            and allowed(db, main_id(db, discord_id), discord_id)):
        return discord_id, "player_id"
    return None, None


def player_of(db: Session, discord_id: str) -> str | None:
    """The replay player page of a Discord account."""
    user_id, _ = account_link(db, discord_id)
    if user_id:
        return main_id(db, user_id)
    for seen in db.scalars(select(NakamaAccount.replay_user_id).where(
            NakamaAccount.discord_id == discord_id, NakamaAccount.replay_user_id.is_not(None))
            .order_by(NakamaAccount.last_seen_at.desc())).all():
        main = main_id(db, seen)
        if allowed(db, main, discord_id):
            return main
    return None


def account_name(db: Session, discord_id: str) -> str | None:
    """A name for a Discord account without asking Discord: its Echo account's, or one Discord told us earlier."""
    acc = db.scalar(select(NakamaAccount).where(NakamaAccount.discord_id == discord_id)
                    .order_by(NakamaAccount.last_seen_at.desc()).limit(1))
    return (acc.display_name or acc.username) if acc is not None else auth.remembered_name(discord_id)


# --- changes (the caller commits) ---------------------------------------------------------------

def _refresh_accounts(db: Session, discord_ids: set[str]) -> None:
    """The stored link of these match-list accounts, at once instead of when they next play (Mega Prize history,
    "Linked account")."""
    db.flush()
    for acc in db.scalars(select(NakamaAccount).where(NakamaAccount.discord_id.in_(discord_ids))).all():
        acc.replay_user_id, acc.link = account_link(db, acc.discord_id)


def _drop(db: Session, profile: PlayerProfile) -> None:
    """Removes a link; the bio and picture choice stay with the Discord account."""
    kept = db.get(DiscordProfile, profile.discord_id)
    if kept is None:
        kept = DiscordProfile(discord_id=profile.discord_id)
        db.add(kept)
    kept.bio, kept.show_avatar, kept.updated_at = profile.bio, profile.show_avatar, profile.updated_at
    db.delete(profile)


def link(db: Session, user_id: str, discord_id: str) -> tuple[PlayerProfile, bool]:
    """Links a player to a Discord account, replacing what either of them had, and lifts an admin's block on the pair.
    Returns (link, changed)."""
    main = main_id(db, user_id)
    ids = aliases.ids_of(db, main)
    db.execute(delete(DiscordLinkBlock).where(DiscordLinkBlock.user_id.in_(ids), DiscordLinkBlock.discord_id == discord_id))
    existing = db.get(PlayerProfile, main)
    if existing is not None and existing.discord_id == discord_id:
        _refresh_accounts(db, {discord_id})
        return existing, False
    old = db.scalars(select(PlayerProfile).where(or_(PlayerProfile.discord_id == discord_id, PlayerProfile.user_id.in_(ids)))).all()
    touched = {discord_id, *(p.discord_id for p in old), *(p.user_id for p in old), *ids}
    for p in old:
        _drop(db, p)
    db.flush()
    mine = db.get(DiscordProfile, discord_id)
    now = utcnow()
    profile = PlayerProfile(user_id=main, discord_id=discord_id, bio=mine.bio if mine else None,
                            show_avatar=mine.show_avatar if mine else True, linked_at=now, updated_at=now)
    db.add(profile)
    _refresh_accounts(db, touched)
    return profile, True


def unlink(db: Session, user_id: str, discord_id: str, block: bool) -> bool:
    """Takes a Discord account off a player. block: an admin's decision, no automatic route nor the bot may restore it.
    Returns whether a stored (bot / admin) link was removed."""
    main = main_id(db, user_id)
    ids = aliases.ids_of(db, main)
    rows = db.scalars(select(PlayerProfile).where(PlayerProfile.user_id.in_(ids), PlayerProfile.discord_id == discord_id)).all()
    for p in rows:
        _drop(db, p)
    if block:
        for u in {main} | ({discord_id} & ids):  # also on the merged id that IS the Discord id: it holds after an unmerge
            db.merge(DiscordLinkBlock(user_id=u, discord_id=discord_id, created_at=utcnow()))
    _refresh_accounts(db, {discord_id, *ids})
    return bool(rows)
