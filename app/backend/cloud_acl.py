"""Open Cloud permissions per folder / file (user, 2026-11-16), on top of the whole-Cloud ones (Cloud view / Cloud edit
on the Permissions page). Console users set them on the Cloud page; the rules live in the table cloud_rules.

A rule belongs to one path and has two parts:
- grants: Discord roles / people with "view" or "edit" here and on everything below. This reaches people without
  whole-Cloud access too: they see only what is shared with them, plus the folders that lead there (and nothing else
  in those folders).
- private: only the people listed in this rule keep access here; everyone else loses it, whole-Cloud access or not.
  A listed person gets exactly the level listed (someone with Cloud edit listed as "view" can only download here).

Three levels (user, 2026-11-16): "view" = download; "edit" = also upload, new folder, rename, delete; "admin" = also
sets the permissions of the item and of everything inside it (and sees who has what there). Admin on the whole cloud
is the Cloud admin permission (Permissions page); console users have it.

A person's level on a path: start with their whole-Cloud level, then walk down from the top folder; each rule on the
way either adds its grant (the higher level wins) or, when private, replaces the level with its grant. A rule deeper
down therefore wins over one above it. One exception: admin is never taken away further down, so the admin of a
folder (or of the whole cloud) always sees and controls everything inside it, private or not.

Renaming or deleting needs edit on the item and on every rule below it (nobody removes a private folder they cannot
open by deleting the folder around it). Rules follow a rename; a deleted item's rules go into its recycle bin note
and come back with a restore.

Paths are matched without regard to letter case: on the NAS two names that differ only by case share one rule (the
stricter reading; on Windows they are the same file anyway). A rule is not removed when its file is taken away with
File Station: it applies again to whatever gets that name later, until a console user clears it."""

import functools
import json
from typing import Callable

from fastapi import Request
from sqlalchemy import select

from . import cloud
from .cloud import CloudError

RANK = {None: 0, "view": 1, "edit": 2, "admin": 3}
LEVELS = ("view", "edit", "admin")
MAX_GRANTS = 50


def clean(rel: str | None) -> str:
    """The path as the cloud itself reads it (cloud.resolve: same split, every name checked and trimmed), so a rule
    cannot be dodged with another spelling of the same path. Raises CloudError for a path the cloud refuses."""
    return "/".join(cloud.check_name(p) for p in (rel or "").replace("\\", "/").split("/") if p)


def join(folder: str, name: str) -> str:
    return f"{folder}/{name}" if folder else name


def _key(rel: str) -> str:
    return rel.casefold()


def _rest(path: str, top: str) -> str:
    """`path` below `top` ("" = top itself); by folder count, as the two may differ in letter case."""
    return "/".join(path.split("/")[len(top.split("/")):])


def edits(level: str | None) -> bool:
    """Upload, new folder, rename, delete: edit or admin."""
    return RANK[level] >= RANK["edit"]


def _higher(a: str | None, b: str | None) -> str | None:
    return a if RANK[a] >= RANK[b] else b


class Access:
    """What one logged-in person may do in the cloud. `rules`: key -> {"path", "private", "grants"}."""

    def __init__(self, user_id: str, base: str | None, console: bool, rules: dict[str, dict],
                 roles: Callable[[], frozenset[str]]):
        self.user_id, self.base, self.console, self.rules, self.roles = user_id, base, console, rules, roles

    def _grant(self, rule: dict) -> str | None:
        best = None
        for g in rule["grants"]:
            if g["id"] == self.user_id if g["type"] == "user" else g["id"] in self.roles():
                best = _higher(best, g["level"])
        return best

    def level(self, rel: str) -> str | None:
        """ "admin", "edit", "view" or None on this path (a clean path; "" = the cloud folder itself)."""
        if self.console:
            return "admin"
        level = self.base
        if not self.rules or not rel:
            return level
        parts = _key(rel).split("/")
        for depth in range(1, len(parts) + 1):
            if level == "admin":  # the admin of a folder keeps everything inside it
                return level
            rule = self.rules.get("/".join(parts[:depth]))
            if rule:
                grant = self._grant(rule)
                level = grant if rule["private"] else _higher(level, grant)
        return level

    def below(self, rel: str) -> list[dict]:
        """The rules on items inside this folder (not the one on the folder itself)."""
        prefix = _key(rel) + "/" if rel else ""
        return [r for k, r in self.rules.items() if k.startswith(prefix)]

    def visible(self, rel: str) -> bool:
        """Shown in a listing, and a folder can be opened: access here, or something further down is shared with them."""
        return bool(self.level(rel)) or any(self.level(r["path"]) for r in self.below(rel))

    def can_change(self, rel: str) -> bool:
        """Rename / delete: edit here and on everything below that has its own rule."""
        return edits(self.level(rel)) and all(edits(self.level(r["path"])) for r in self.below(rel))

    def best(self) -> str | None:
        """The most this person may do anywhere (the Cloud tab shows when it is not None)."""
        if self.console:
            return "admin"
        level = self.base
        for rule in self.rules.values():
            level = _higher(level, self.level(rule["path"]))
        return level

    def manages(self) -> bool:
        """Admin of the whole cloud or of at least one folder / file."""
        return self.best() == "admin"


def load(db) -> dict[str, dict]:
    from .models import CloudRule
    out = {}
    for r in db.scalars(select(CloudRule)):
        try:
            grants = json.loads(r.grants or "[]")
        except ValueError:
            grants = []  # unreadable: nobody is listed (a private rule then keeps everyone but console users out)
        out[r.key] = {"path": r.path, "private": bool(r.private), "grants": [g for g in grants if _valid(g)],
                      "updated_at": r.updated_at, "by": r.by_name}
    return out


def _valid(g) -> bool:
    return (isinstance(g, dict) and g.get("type") in ("role", "user") and g.get("level") in LEVELS
            and isinstance(g.get("id"), str) and g["id"].isascii() and g["id"].isdigit())


def access(request: Request, fresh: bool = False) -> Access | None:
    """The visitor's cloud access, or None when not logged in. fresh: ask Discord for their roles now (changes)."""
    from . import auth
    user = auth.viewer(request)
    if not user:
        return None
    settings = request.app.state.settings
    if fresh:
        auth.forget_roles(user["id"])
    roles = functools.cache(lambda: auth.member_roles(settings, user["id"]))
    with request.app.state.sessionmaker() as db:
        return _build(settings, db, user["id"], roles, load(db))


def _build(settings, db, user_id: str, roles: Callable[[], frozenset[str]], rules: dict[str, dict]) -> Access:
    from . import auth
    console = auth.allowed(settings, db, user_id, "console", roles)
    base = ("admin" if console or auth.allowed(settings, db, user_id, "cloud_admin", roles)
            else "edit" if auth.allowed(settings, db, user_id, "cloud_edit", roles)
            else "view" if auth.allowed(settings, db, user_id, "cloud_view", roles) else None)
    return Access(user_id, base, console, rules, roles)


def access_as(settings, db, kind: str, discord_id: str, rules: dict[str, dict]) -> Access:
    """What a role or a person may do (console users: "View as", and who gets into one item). A role: someone with
    only that role. A person: with the roles Discord gives for them now."""
    from . import auth
    if kind == "user":
        return _build(settings, db, discord_id, functools.cache(lambda: auth.member_roles(settings, discord_id)), rules)
    return _build(settings, db, "", lambda: frozenset({discord_id}), rules)


def chain(rules: dict[str, dict], rel: str, itself: bool = True) -> list[dict]:
    """The rules on the folders above this path, top first (and its own, last)."""
    parts = _key(rel).split("/") if rel else []
    keys = ("/".join(parts[:i]) for i in range(1, len(parts) + (1 if itself else 0)))
    return [rules[k] for k in keys if k in rules]


def effective(settings, db, rel: str, rules: dict[str, dict]) -> list[dict]:
    """Who ends up with what on this item: every role / person with a whole-Cloud permission or named in a rule on the
    way to it, with their final level (None = no access). Console users are not listed: they are always admin."""
    from .admin_actions import discord_roles
    people: dict[tuple[str, str], None] = {}
    for rule in chain(rules, rel):
        for g in rule["grants"]:
            people[(g["type"], g["id"])] = None
    for kind in ("cloud_admin", "cloud_edit", "cloud_view"):
        for i in discord_roles(db, kind):
            people[("role", i)] = None
        for i in discord_roles(db, f"{kind}_user"):
            people[("user", i)] = None
    out = []
    for kind, discord_id in people:
        acl = access_as(settings, db, kind, discord_id, rules)
        if not acl.console:
            out.append({"type": kind, "id": discord_id, "level": acl.level(rel)})
    out.sort(key=lambda p: -RANK[p["level"]])
    return out


# --- changing the rules (admins of the item; api/cloud.py checks that) ---------------------------------------------------

def check_grants(grants: list) -> list[dict]:
    """What an admin sent, tidied: one line per role / person (the last one given counts)."""
    from .admin_actions import AdminError, _role_id
    if len(grants) > MAX_GRANTS:
        raise CloudError(400, "bad_rule", f"At most {MAX_GRANTS} roles and people on one item")
    seen: dict[tuple[str, str], dict] = {}
    for g in grants:
        if not isinstance(g, dict) or g.get("type") not in ("role", "user") or g.get("level") not in LEVELS:
            raise CloudError(400, "bad_rule", "Each line needs a role or a person, and View, Edit or Admin")
        try:
            discord_id = _role_id(str(g.get("id") or ""))
        except AdminError as e:
            raise CloudError(400, "bad_id", str(e)) from None
        seen[(g["type"], discord_id)] = {"type": g["type"], "id": discord_id, "level": g["level"]}
    return list(seen.values())


def _write(db, rel: str, private: bool, grants: list[dict], user: dict) -> None:
    from .db import utcnow
    from .models import CloudRule
    db.merge(CloudRule(key=_key(rel), path=rel, private=private, grants=json.dumps(grants), updated_at=utcnow(),
                       by_id=user["id"], by_name=user["name"]))


def _rows(db, rel: str, itself: bool = True) -> list:
    """The stored rules on this path (itself) and below it."""
    from .models import CloudRule
    key = _key(rel)
    return [r for r in db.scalars(select(CloudRule)) if (itself and r.key == key) or r.key.startswith(key + "/")]


def save(sessions, rel: str, private: bool, grants: list[dict], user: dict) -> None:
    """Sets the rule of one path; nothing listed and not private = no rule."""
    from .models import CloudRule
    with sessions() as db:
        if private or grants:
            _write(db, rel, private, grants, user)
        else:
            row = db.get(CloudRule, _key(rel))
            if row:
                db.delete(row)
        db.commit()


def move(sessions, old: str, new: str, user: dict) -> None:
    """After a rename: the rules on the item and below it go with it. Left-over rules at the new name (of something
    that is no longer there) are dropped: the renamed item brings its own."""
    with sessions() as db:
        moving = _rows(db, old)
        if _key(old) != _key(new):
            for row in _rows(db, new):
                db.delete(row)
            db.flush()
        for row in moving:
            private, grants, rest = row.private, json.loads(row.grants or "[]"), _rest(row.path, old)
            db.delete(row)
            db.flush()
            _write(db, join(new, rest) if rest else new, private, grants, user)
        db.commit()


def stash(acl: Access, rel: str) -> list[dict]:
    """For the recycle bin note of a deleted item: its rules, with paths relative to the item ("" = the item)."""
    key = _key(rel)
    return [{"sub": _rest(r["path"], rel), "private": r["private"], "grants": r["grants"]}
            for k, r in acl.rules.items() if k == key or k.startswith(key + "/")]


def forget(sessions, rel: str) -> None:
    """The item was deleted: its rules are in its recycle bin note now."""
    with sessions() as db:
        for row in _rows(db, rel):
            db.delete(row)
        db.commit()


def put_back(sessions, rel: str, stashed, user: dict) -> None:
    """A restore: the rules from the recycle bin note, at the path the item comes back to (written just before the
    item is moved there, so a private item is never open for a moment). Rules left at that path are replaced."""
    with sessions() as db:
        for row in _rows(db, rel):
            db.delete(row)
        db.flush()
        for rule in stashed if isinstance(stashed, list) else []:
            if not isinstance(rule, dict):
                continue
            try:
                sub = clean(str(rule.get("sub") or ""))
                grants = check_grants(rule.get("grants") or [])
            except CloudError:
                continue  # a damaged note: that rule is skipped
            if rule.get("private") or grants:
                _write(db, join(rel, sub) if sub else rel, bool(rule.get("private")), grants, user)
        db.commit()


def describe(private: bool, grants: list[dict]) -> str:
    """For the audit log."""
    parts = ["private"] if private else []
    parts += [f"{g['level']}: {g['type']} {g['id']}" for g in grants]
    return ", ".join(parts) or "cleared"
