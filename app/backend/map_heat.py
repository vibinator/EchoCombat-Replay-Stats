"""All-time heat per map for the home page's "Matches per map" cards: where players have been over every counted
match - both teams, or only while holding one weapon, ordnance or tac mod - as one small PNG per map laid over the
minimap thumbnail.

The whole archive is far too much to rasterise for a request (33 000 matches, ~300 million samples: minutes on the
NAS), so the counts are kept: per map one grid of CELL_M cells per layer (LAYERS: the two teams and every gear code),
saved in the data folder with the replay ids already added. It is brought up to date once per calendar month (user,
2026-11-10), on the first visit of the month: an update only reads the tracks of replays that are new (or subtracts
those that stopped counting: a duplicate recording, D13), a batch at a time in a background thread; the cards show
what has been added so far. An update cut short by a restart carries on at the next visit.

Kept cheap:
- samples are counted where they are (2 Hz), not joined with lines as the match heatmaps do: over thousands of matches
  the paths fill in by themselves, and it is several times faster;
- every sample is mapped to its cell once and then counted in its four layers (team, weapon, ordnance, tac mod) with a
  single bincount per few million samples, not one pass per layer;
- the files are read a few at a time in parallel and not kept in the tracks cache (an archive-wide pass would push out
  what visitors are using);
- an answer is four palette PNGs (one byte per pixel, 5-30 KB each), built once per layer, view and state of the
  counts and then served from the response cache.

Three pictures come out of the same counts (reviewed 2026-11-10): both teams; one piece of gear "favoured" (where it
is held more often than on the map as a whole - the default, because plain counts of any gear mostly show where
everybody is); and one piece of gear "all" (everywhere it was held).

Delete the file to build it again from nothing (also done when FORMAT, the cell size, a map's extents or the gear
tables change)."""

import base64
import io
import logging
import os
import threading
import time
from datetime import date
from pathlib import Path

import numpy as np
from sqlalchemy import select

from . import heatmaps, tracks
from .duplicates import counted
from .gear import ORDNANCES, TACMODS, WEAPONS
from .models import Match
from .stats.maps import HEATMAP_LAYOUTS

log = logging.getLogger(__name__)

FORMAT = 3  # of the saved file: another number = start again (3: Fission turned top to bottom)
# Cell size: 0.3 m since 2026-11-10 (user: a little finer than the first 0.5 m; the large view shows it). Positions are
# stored in whole decimetres, so a cell must be a whole number of them: 0.25 m cells would hold 2 or 3 positions in
# turn and show as stripes.
CELL_M = 0.3
NUDGE_M = 0.0125  # added to every position: none then sits exactly on a cell's edge, where rounding would decide
TEAMS = ("blue", "orange")
TEAM_LAYER = "team"  # the answer that mixes the two team layers
# (group, field in a tracks file, list of codes in its header, gear table)
GEAR_GROUPS = (("weapon", "weapon", "weapons", WEAPONS), ("ordnance", "ordnance", "ordnances", ORDNANCES),
               ("tacmod", "tacmod", "tacmods", TACMODS))
LAYERS = [f"team:{t}" for t in TEAMS] + [f"{group}:{code}" for group, _, _, table in GEAR_GROUPS for code in table]
LAYER_INDEX = {key: i for i, key in enumerate(LAYERS)}
BATCH = 500  # replays added between two saves (and two looks at the cards while it builds)
READ_CHUNK = 64  # files decoded at once
FLUSH_SAMPLES = 2_000_000  # samples gathered per map before they are counted (memory: ~70 MB at the peak)
FILE_NAME = "map-heat.npz"
RETRY_S = 600  # after an update that failed


def _shape(map_: str) -> tuple[int, int]:
    cols, rows = heatmaps.grid_size(HEATMAP_LAYOUTS[map_], CELL_M)
    return rows, cols


def _gear_layers(header: dict, codes_field: str, group: str) -> np.ndarray:
    """Index in a tracks file's own gear list (255 = none) -> layer number, -1 = not counted."""
    out = np.full(256, -1, dtype=np.int64)
    for i, code in enumerate(header.get(codes_field, [])[:255]):
        out[i] = LAYER_INDEX.get(f"{group}:{code}", -1)
    return out


def sample_keys(map_: str, header: dict, players: dict) -> np.ndarray:
    """Every sample of one match as layer * cells + cell, once per layer it belongs to (its team and the three pieces
    of gear held)."""
    layout = HEATMAP_LAYOUTS[map_]
    rows, cols = _shape(map_)
    lookups = [(field, _gear_layers(header, codes_field, group)) for group, field, codes_field, _ in GEAR_GROUPS]
    keys = []
    for t in players.values():
        team = np.frombuffer(t["team"], dtype=np.uint8)
        present = team != 0
        if not present.any():
            continue
        x = np.frombuffer(t["x"], dtype=np.int16)[present] / 10 + NUDGE_M
        z = np.frombuffer(t["z"], dtype=np.int16)[present] / 10 + NUDGE_M
        col, row, inside = heatmaps.cells_of(layout, x, z, CELL_M)
        cell = row * cols + col
        where = np.flatnonzero(present)[inside]
        layers = [team[where].astype(np.int64) - 1]  # tracks.BLUE, ORANGE = 1, 2 -> layers 0, 1
        layers += [lookup[np.frombuffer(t[field], dtype=np.uint8)[where]] for field, lookup in lookups]
        for layer in layers:
            known = layer >= 0
            keys.append(layer[known] * (rows * cols) + cell[known])
    return np.concatenate(keys) if keys else np.zeros(0, dtype=np.int64)


def add_keys(counts: np.ndarray, keys: list[np.ndarray], sign: int = 1) -> None:
    """Add (or with sign -1 take away) gathered sample_keys to a map's layers x rows x cols counts."""
    if not keys:
        return
    found = np.bincount(np.concatenate(keys), minlength=counts.size).reshape(counts.shape)
    if sign > 0:
        counts += found.astype(counts.dtype)
    else:  # the file may have been read again since it was added: never below nothing
        np.subtract(counts, np.minimum(found, counts).astype(counts.dtype), out=counts)


# -- drawing ----------------------------------------------------------------------------------------------------------
# Over the whole archive every reachable cell has been visited, so a log scale (as a single match uses) would paint
# the map evenly. Here the strength rises with the square root of the count, up to the PEAK_QUANTILE busiest cell (the
# spawn rooms would otherwise set the scale and leave the rest faint).
PEAK_QUANTILE = 0.999
# Teams (reviewed 2026-11-10: the first version was a grey wash over the whole map). The floor everybody drifts over
# stays clear (below TEAM_FLOOR), a cell takes the colour of the team that is there most (the share is stretched by
# TEAM_CONTRAST, so only a really even cell is neutral), and the busiest cells turn towards white.
TEAM_RGB = {"blue": (0x38, 0xB6, 0xFF), "orange": (0xFF, 0x8A, 0x1E)}
TEAM_FLOOR, TEAM_GAMMA, TEAM_MAX_ALPHA = 0.08, 0.85, 0.95
TEAM_CONTRAST, TEAM_WHITE = 2.2, 0.55
SHARE_STEPS, ALPHA_STEPS = 8, 31  # 8 x 31 + 1 (clear) = 249 palette entries
# Gear: one ramp for every piece of gear (dark violet -> magenta -> pale yellow), so two layers compare by shape and a
# busy spot reads the same whatever is selected; apart from both team colours on the dimmed minimap.
GEAR_RAMP = ((0.0, (0x3B, 0x0F, 0x70)), (0.3, (0x8C, 0x29, 0x81)), (0.55, (0xDE, 0x49, 0x68)),
             (0.8, (0xFE, 0x9F, 0x6D)), (1.0, (0xFC, 0xFD, 0xBF)))
GEAR_ALPHA = (0.05, 0.95)
GEAR_STEPS = 255
# "favoured" view of a piece of gear: where it is held more often than it is on the map as a whole. Every piece of
# gear is mostly where everybody is (the objective, the payload's route), so the plain counts look alike for all of
# them; this shows what is particular to one (a sniper's perch, a healer's corner). Counts are smoothed over
# FAVOURED_BLUR cells first, a cell needs FAVOURED_MIN_EXPECTED samples expected of this gear (else a few seconds of
# one player would light it). The ramp starts a little above "as often as anywhere" (FAVOURED_FROM) and ends at the
# layer's own FAVOURED_QUANTILE cell, kept within FAVOURED_TOP: gear half of all players carry can never be held
# twice as often as usual anywhere, gear few carry can be ten times as often in one corner.
VIEWS = ("favoured", "all")
FAVOURED_BLUR = max(1, round(1.0 / CELL_M))  # cells: about a metre each way
FAVOURED_MIN_EXPECTED = 160.0 * CELL_M * CELL_M  # per cell: 160 samples per square metre
FAVOURED_FROM = 1.05
FAVOURED_QUANTILE = 0.995
FAVOURED_TOP = (1.3, 2.5)
FAVOURED_ALPHA = (0.30, 0.95)  # a favoured spot is a patch, not a wash: visible from its edge
FAVOURED_CAP_QUANTILE = 0.999  # a cell counts for no more than this one: somebody parked in one spot for hours
FAVOURED_SPIKE = 2.0
# (Surge has such a cell) would otherwise light a square around it in the layer of whatever they were holding
MIN_LAYER_SHARE = 0.005  # gear held less than this share of the time is not offered: too little to draw


def _strength(total: np.ndarray) -> np.ndarray | None:
    visited = total > 0
    if not visited.any():
        return None
    peak = float(np.quantile(total[visited], PEAK_QUANTILE))
    return np.sqrt(np.minimum(total / peak, 1.0))


def _team_palette() -> np.ndarray:
    palette = np.zeros((1 + SHARE_STEPS * ALPHA_STEPS, 4))
    blue, orange = (np.array(TEAM_RGB[t], dtype=np.float64) for t in TEAMS)
    for s in range(SHARE_STEPS):
        share = s / (SHARE_STEPS - 1)  # of orange, after the stretch
        for a in range(ALPHA_STEPS):
            level = a / (ALPHA_STEPS - 1)
            white = TEAM_WHITE * level ** 4
            rgb = (blue * (1 - share) + orange * share) * (1 - white) + 255 * white
            palette[1 + s * ALPHA_STEPS + a] = (*rgb, TEAM_MAX_ALPHA * level * 255)
    return np.rint(palette).astype(np.uint8)


def _gear_palette(alpha: tuple[float, float]) -> np.ndarray:
    palette = np.zeros((1 + GEAR_STEPS, 4))
    at = np.array([p for p, _ in GEAR_RAMP])
    level = np.arange(GEAR_STEPS) / (GEAR_STEPS - 1)
    for ch in range(3):
        palette[1:, ch] = np.interp(level, at, [rgb[ch] for _, rgb in GEAR_RAMP])
    palette[1:, 3] = (alpha[0] + (alpha[1] - alpha[0]) * level) * 255
    return np.rint(palette).astype(np.uint8)


TEAM_PALETTE, GEAR_PALETTE, FAVOURED_PALETTE = _team_palette(), _gear_palette(GEAR_ALPHA), _gear_palette(FAVOURED_ALPHA)


def render_teams(blue: np.ndarray, orange: np.ndarray) -> bytes | None:
    """One map's heat of both teams as a transparent PNG covering the whole minimap; None when there is none."""
    blue, orange = blue.astype(np.float64), orange.astype(np.float64)
    total = blue + orange
    strength = _strength(total)
    if strength is None:
        return None
    level = np.clip((strength - TEAM_FLOOR) / (1 - TEAM_FLOOR), 0, 1) ** TEAM_GAMMA
    step = np.rint(level * (ALPHA_STEPS - 1))
    share = np.divide(orange, total, out=np.full(total.shape, 0.5), where=total > 0)
    share = np.clip(0.5 + (share - 0.5) * TEAM_CONTRAST, 0, 1)
    index = 1 + np.rint(share * (SHARE_STEPS - 1)) * ALPHA_STEPS + step
    return heatmaps.png_indexed(np.where(step > 0, index, 0).astype(np.uint8), TEAM_PALETTE)


def render_gear(total: np.ndarray) -> bytes | None:
    """The same for one piece of gear: everywhere it was held ("all" view)."""
    strength = _strength(total.astype(np.float64))
    if strength is None:
        return None
    index = np.where(total > 0, 1 + np.rint(strength * (GEAR_STEPS - 1)), 0)
    return heatmaps.png_indexed(index.astype(np.uint8), GEAR_PALETTE)


def _blur(grid: np.ndarray, radius: int) -> np.ndarray:
    """Box blur over 2 * radius + 1 cells, twice in each direction (close to a Gaussian); the sum is kept."""
    out = grid.astype(np.float64)
    width = 2 * radius + 1
    for _ in range(2):
        for axis in (0, 1):
            pad = [(radius + 1, radius) if ax == axis else (0, 0) for ax in (0, 1)]
            total = np.cumsum(np.pad(out, pad), axis=axis)
            n = total.shape[axis]
            out = (np.take(total, range(width, n), axis=axis) - np.take(total, range(0, n - width), axis=axis)) / width
    return out


def render_favoured(gear: np.ndarray, group: np.ndarray) -> bytes | None:
    """One piece of gear against all gear of its group (same map): bright where it is held more often than on the
    map as a whole ("favoured" view). None when there is too little of it to say."""
    gear, group = gear.astype(np.float64), group.astype(np.float64)
    if gear.sum() <= 0:
        return None
    cap = float(np.quantile(group[group > 0], FAVOURED_CAP_QUANTILE))
    # ... nor for more than FAVOURED_SPIKE times its surroundings: a lone parked player beside the map, where nobody
    # else ever is, would still stand out after the cap above
    around = _blur(np.minimum(group, cap), FAVOURED_BLUR)
    weight = np.minimum(1.0, np.minimum(cap, FAVOURED_SPIKE * around) / np.maximum(group, 1.0))
    held, everyone = _blur(gear * weight, FAVOURED_BLUR), _blur(group * weight, FAVOURED_BLUR)
    usual = held.sum() / everyone.sum()
    enough = everyone * usual >= FAVOURED_MIN_EXPECTED
    lift = np.divide(held, everyone * usual, out=np.zeros(held.shape), where=enough)
    favoured = lift >= FAVOURED_FROM
    if not favoured.any():
        return None
    top = float(np.clip(np.quantile(lift[favoured], FAVOURED_QUANTILE), *FAVOURED_TOP))
    strength = np.clip((lift - FAVOURED_FROM) / (top - FAVOURED_FROM), 0, 1)
    index = np.where(favoured, 1 + np.rint(strength * (GEAR_STEPS - 1)), 0)
    return heatmaps.png_indexed(index.astype(np.uint8), FAVOURED_PALETTE)


class MapHeat:
    """The counts in memory (~70 MB), their file, and the background update. One per app."""

    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.processed_dir: Path = settings.processed_dir
        self.path: Path = settings.data_dir / "database" / FILE_NAME
        self.refresh_s: float = settings.cache_refresh_s
        self.lock = threading.Lock()  # counts, included, revision, updated_on
        self.updating = threading.Lock()  # one update at a time
        self.counts: dict[str, np.ndarray] = {}  # map -> layers x rows x cols
        self.included: dict[int, str] = {}  # replay id -> map it was added to
        self.revision = 0  # changes whenever the counts do: part of the cache key of the answer
        self.building = False
        self.updated_on: str | None = None  # day the last complete update finished (ISO); None = never finished
        self.tried_at = 0.0
        self.loaded = False

    # -- file ---------------------------------------------------------------------------------------------------

    def _empty(self) -> None:
        self.counts = {m: np.zeros((len(LAYERS), *_shape(m)), dtype=np.uint32) for m in HEATMAP_LAYOUTS}
        self.included = {}
        self.updated_on = None

    def _load(self) -> None:
        self._empty()
        self.loaded = True
        try:
            with np.load(self.path, allow_pickle=False) as saved:
                if (int(saved["format"]) != FORMAT or float(saved["cell_m"]) != CELL_M
                        or [str(k) for k in saved["layers"]] != LAYERS):
                    return
                counts = {m: saved[f"counts_{m}"] for m in self.counts}
                if any(counts[m].shape != self.counts[m].shape for m in counts):
                    return  # a map's extents changed
                maps = [str(m) for m in saved["maps"]]
                self.included = {int(r): maps[int(i)] for r, i in zip(saved["replay_ids"], saved["replay_maps"])}
                self.counts = {m: c.astype(np.uint32) for m, c in counts.items()}
                self.updated_on = str(saved["updated_on"]) or None
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001 - a damaged or older file: count again
            log.warning("Could not use %s; the all-time map heat is built again", self.path)
            self._empty()

    def _save(self) -> None:
        maps = list(HEATMAP_LAYOUTS)
        index = {m: i for i, m in enumerate(maps)}
        buffer = io.BytesIO()
        np.savez_compressed(
            buffer, format=np.int64(FORMAT), cell_m=np.float64(CELL_M), maps=np.array(maps), layers=np.array(LAYERS),
            updated_on=np.array(self.updated_on or ""),
            replay_ids=np.fromiter(self.included.keys(), dtype=np.int64, count=len(self.included)),
            replay_maps=np.fromiter((index[m] for m in self.included.values()), dtype=np.int8, count=len(self.included)),
            **{f"counts_{m}": c for m, c in self.counts.items()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(buffer.getvalue())
        os.replace(tmp, self.path)

    # -- update -------------------------------------------------------------------------------------------------

    def _wanted(self) -> dict[int, str]:
        with self.sessions() as db:
            rows = db.execute(select(Match.replay_id, Match.map).where(counted(Match.id), Match.map.in_(HEATMAP_LAYOUTS)))
            return {replay_id: map_ for replay_id, map_ in rows}

    def update(self) -> None:
        """Bring the counts up to date with the archive. Slow the first time; later only the new replays are read."""
        with self.updating:
            if not self.loaded:
                with self.lock:
                    self._load()
            wanted = self._wanted()
            gone = [(r, m) for r, m in self.included.items() if wanted.get(r) != m]
            new = [(r, m) for r, m in wanted.items() if r not in self.included]
            self.building = True
            try:
                # a replay that no longer counts (a fuller copy of the match arrived, or it was deleted): take it out
                # again if its tracks are still there, forget it either way
                for start in range(0, len(gone), BATCH):
                    self._apply(gone[start:start + BATCH], -1)
                for start in range(0, len(new), BATCH):
                    self._apply(new[start:start + BATCH], 1)
                with self.lock:
                    self.updated_on = date.today().isoformat()
                    self.revision += 1
                    self._save()
            finally:
                self.building = False

    def _apply(self, batch: list[tuple[int, str]], sign: int) -> None:
        # read and work out the cells outside the lock (the slow part), count under it
        found: dict[str, np.ndarray] = {}
        pending: dict[str, list[np.ndarray]] = {}
        seen: list[tuple[int, str, bool]] = []

        def flush(map_: str) -> None:
            keys = pending.pop(map_, [])
            if keys:
                if map_ not in found:
                    found[map_] = np.zeros(self.counts[map_].shape, dtype=np.uint32)
                add_keys(found[map_], keys)

        for start in range(0, len(batch), READ_CHUNK):
            chunk = batch[start:start + READ_CHUNK]
            paths = [tracks.tracks_path(self.processed_dir, replay_id) for replay_id, _ in chunk]
            for (replay_id, map_), data in zip(chunk, tracks._readers.map(_read, paths)):
                seen.append((replay_id, map_, data is not None))
                if data is None:
                    continue
                pending.setdefault(map_, []).append(sample_keys(map_, *data))
                if sum(len(k) for k in pending[map_]) >= FLUSH_SAMPLES:
                    flush(map_)
        for map_ in list(pending):
            flush(map_)
        with self.lock:
            for map_, counts in found.items():
                if sign > 0:
                    self.counts[map_] += counts
                else:
                    np.subtract(self.counts[map_], np.minimum(counts, self.counts[map_]), out=self.counts[map_])
            for replay_id, map_, readable in seen:
                if sign < 0:
                    self.included.pop(replay_id, None)
                elif readable:  # no tracks yet (still importing): looked at again at the next update
                    self.included[replay_id] = map_
            self.revision += 1
            self._save()

    def due(self) -> bool:
        """Never finished, or last finished in an earlier month."""
        return self.updated_on is None or self.updated_on[:7] != date.today().isoformat()[:7]

    def ensure(self) -> None:
        """Called with every request for the cards: load what was saved, and start the month's update when it is due.
        cache_refresh_s = 0 (the tests): update before answering."""
        if not self.loaded:
            with self.updating, self.lock:
                if not self.loaded:
                    self._load()
        if not self.due():
            return
        if self.refresh_s <= 0:
            self.update()
            return
        now = time.monotonic()
        if self.updating.locked() or (self.tried_at and now - self.tried_at < RETRY_S):
            return
        self.tried_at = now

        def run():
            try:
                self.update()
            except Exception:  # noqa: BLE001 - the cards keep what they had; tried again after RETRY_S
                log.exception("Updating the all-time map heat failed")

        threading.Thread(target=run, name="map-heat", daemon=True).start()

    # -- answer -------------------------------------------------------------------------------------------------

    def answer(self, layer: str = TEAM_LAYER, view: str = VIEWS[0]) -> dict:
        """The cards' overlays for one layer, and the layers there are (gear hardly ever held is left out; the most
        held first within its group). `view` (gear only): "favoured" = where it is held more than usual, "all" =
        everywhere it was held."""
        teams = [LAYER_INDEX[f"team:{t}"] for t in TEAMS]
        group = layer.partition(":")[0]
        in_group = [i for key, i in LAYER_INDEX.items() if key.startswith(group + ":")]
        with self.lock:
            if layer == TEAM_LAYER:
                picked = {m: [c[i].copy() for i in teams] for m, c in self.counts.items()}
            elif view == "all":
                picked = {m: [c[LAYER_INDEX[layer]].copy()] for m, c in self.counts.items()}
            else:
                picked = {m: [c[LAYER_INDEX[layer]].copy(), c[in_group].sum(axis=0, dtype=np.int64)]
                          for m, c in self.counts.items()}
            samples = sum(c.sum(axis=(1, 2), dtype=np.int64) for c in self.counts.values()) if self.counts else []
            per_map: dict[str, int] = {}
            for map_ in self.included.values():
                per_map[map_] = per_map.get(map_, 0) + 1
            building, updated_on = self.building, self.updated_on
        draw = render_teams if layer == TEAM_LAYER else render_gear if view == "all" else render_favoured
        maps = {}
        for map_, grids in picked.items():
            png = draw(*grids)
            if png:
                maps[map_] = {"image": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                              "matches": per_map.get(map_, 0)}
        layers = [{"key": TEAM_LAYER, "group": "team", "label": "Both teams"}]
        for name, _, _, table in GEAR_GROUPS:
            held = [(int(samples[LAYER_INDEX[f"{name}:{code}"]]), code) for code in table] if len(samples) else []
            total = sum(n for n, _ in held)
            for n, code in sorted(held, key=lambda item: -item[0]):
                if n and n / total >= MIN_LAYER_SHARE:
                    layers.append({"key": f"{name}:{code}", "group": name, "code": code,
                                   "label": table[code].display_name, "cut": table[code].cut,
                                   "share": round(n / total, 4)})
        return {"layer": layer, "view": "teams" if layer == TEAM_LAYER else view, "maps": maps, "layers": layers,
                "building": building, "updated_on": updated_on}


def _read(path: Path):
    """One tracks file, not kept in the tracks cache: an archive-wide pass would push out what visitors are using."""
    try:
        return tracks.decode(path.read_bytes())
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - one unreadable file must not stop the pass
        log.warning("Unreadable tracks file %s left out of the all-time map heat", path)
        return None
