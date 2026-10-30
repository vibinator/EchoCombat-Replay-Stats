"""Achievement icons chosen on the Console page (D43): an existing badge image or an uploaded PNG. The choice is
in app_settings and uploads in <data>/icons, so both survive updates and database rebuilds. Applied when an answer
is sent (never stored in cached results), so a change shows everywhere at once."""

import hashlib
import json
import re
import struct
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .achievements import RULES, icon_file
from .config import PROJECT_ROOT, Settings
from .db import utcnow
from .models import AppSetting

KEY = "achievement_icons"  # JSON {rule id: icon file under /achievements/}
CUSTOM = "custom/"  # uploaded icons: /achievements/custom/<hash>.png
CUSTOM_NAME = re.compile(r"^[0-9a-f]{16}\.png$")
MAX_BYTES = 512 * 1024
MAX_SIDE = 1024
PNG = b"\x89PNG\r\n\x1a\n"
# badge art shipped with the site; tier frames and locks are not icons
BUILT_IN_DIRS = (PROJECT_ROOT / "app" / "frontend" / "dist" / "achievements", PROJECT_ROOT / "app" / "frontend" / "public" / "achievements")
NOT_ICONS = re.compile(r"^(white|bronze|silver|gold)(_lock)?\.png$|^lock_")
RULE_IDS = {r.id for r in RULES}


class IconError(ValueError):
    pass


def overrides(db: Session) -> dict[int, str]:
    value = db.scalar(select(AppSetting.value).where(AppSetting.key == KEY))
    return {int(k): v for k, v in json.loads(value).items()} if value else {}


def apply(db: Session, items: list[dict], id_key: str = "id") -> list[dict]:
    """Copies of `items` with the admin-chosen icons (the originals may live in a cache)."""
    chosen = overrides(db)
    return [item | {"icon": chosen[item[id_key]]} if item.get(id_key) in chosen else item for item in items]


def custom_dir(settings: Settings) -> Path:
    return settings.data_dir / "icons"


def built_in() -> list[str]:
    folder = next((d for d in BUILT_IN_DIRS if d.is_dir()), None)
    return sorted(p.name for p in folder.glob("*.png") if not NOT_ICONS.search(p.name)) if folder else []


def available(settings: Settings) -> list[str]:
    """Every icon an admin can pick: the built-in badge art, then uploads (newest first)."""
    folder = custom_dir(settings)
    uploads = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.is_dir() else []
    return built_in() + [CUSTOM + p.name for p in uploads if CUSTOM_NAME.match(p.name)]


def default(rule_id: int) -> str | None:
    return icon_file(next(r for r in RULES if r.id == rule_id))


def set_icon(db: Session, settings: Settings, rule_id: int, icon: str | None) -> dict[int, str]:
    """icon None = back to the default."""
    if rule_id not in RULE_IDS:
        raise IconError(f"No achievement {rule_id}")
    if icon is not None and icon not in available(settings):
        raise IconError(f"Unknown icon '{icon}'")
    chosen = overrides(db)
    if icon is None or icon == default(rule_id):
        chosen.pop(rule_id, None)
    else:
        chosen[rule_id] = icon
    db.merge(AppSetting(key=KEY, value=json.dumps({str(k): v for k, v in sorted(chosen.items())}) or None,
                        updated_at=utcnow()))
    db.commit()
    return chosen


def save_upload(settings: Settings, data: bytes) -> str:
    """Checks a PNG and stores it under its content hash. Returns the icon name (custom/<hash>.png)."""
    if len(data) > MAX_BYTES:
        raise IconError(f"Image too big: at most {MAX_BYTES // 1024} KB")
    if not data.startswith(PNG) or data[12:16] != b"IHDR" or len(data) < 33:
        raise IconError("Only PNG images can be uploaded")
    width, height = struct.unpack(">II", data[16:24])
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        raise IconError(f"Image must be at most {MAX_SIDE} x {MAX_SIDE} pixels")
    name = hashlib.sha256(data).hexdigest()[:16] + ".png"
    folder = custom_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    return CUSTOM + name
