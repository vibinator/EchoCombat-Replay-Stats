"""Heatmap grids in minimap image space (D18). Cells are `cell_m` metres (default 0.25, D35); consecutive
2 Hz samples are joined with a line unless the player jumped (respawn / teleport)."""

import math
import struct
import zlib
from collections import Counter
from collections.abc import Callable, Iterable
from functools import lru_cache

import numpy as np

from .stats.maps import HEATMAP_LAYOUTS, HeatmapLayout

CELL_M = 0.25  # playback position snapping
HEATMAP_CELL_M = 0.1  # heatmaps: super fine only (positions are stored to 0.1 m)
CELL_SIZES = (HEATMAP_CELL_M,)
MAX_STEP_M = 12.0  # > 24 m/s between 0.5 s samples = respawn or teleport: do not draw a line
NO_GEAR = 255  # tracks.NO_WEAPON


def grid_size(layout: HeatmapLayout, cell_m: float = CELL_M) -> tuple[int, int]:
    width_m = (layout.z_max - layout.z_min) if layout.u_axis == "z" else (layout.x_max - layout.x_min)
    height_m = (layout.x_max - layout.x_min) if layout.u_axis == "z" else (layout.z_max - layout.z_min)
    return math.ceil(width_m / cell_m), math.ceil(height_m / cell_m)


@lru_cache(maxsize=64)
def _geometry(layout: HeatmapLayout, cell_m: float) -> tuple:
    """Layout worked out once per (layout, cell size): heatmaps map millions of points."""
    x_min, x_max, z_min, z_max = layout.x_min, layout.x_max, layout.z_min, layout.z_max
    swap = layout.u_axis == "z"
    u_min, u_max, v_min, v_max = (z_min, z_max, x_min, x_max) if swap else (x_min, x_max, z_min, z_max)
    cols, rows = grid_size(layout, cell_m)
    return x_min, x_max, z_min, z_max, swap, u_min, u_max, v_min, v_max, layout.u_flip, layout.v_flip, cols - 1, rows - 1


def cell_mapper(layout: HeatmapLayout, cell_m: float = CELL_M) -> Callable[[float, float], tuple[int, int] | None]:
    """to_cell for one layout and cell size."""
    x_min, x_max, z_min, z_max, swap, u_min, u_max, v_min, v_max, u_flip, v_flip, last_col, last_row =         _geometry(layout, cell_m)

    def cell_of(x: float, z: float) -> tuple[int, int] | None:
        if not (x_min <= x <= x_max and z_min <= z <= z_max):
            return None
        u, v = (z, x) if swap else (x, z)
        col = (u_max - u) if u_flip else (u - u_min)
        row = (v - v_min) if v_flip else (v_max - v)
        return min(int(col / cell_m), last_col), min(int(row / cell_m), last_row)

    return cell_of


def to_cell(layout: HeatmapLayout, x: float, z: float, cell_m: float = CELL_M) -> tuple[int, int] | None:
    return cell_mapper(layout, cell_m)(x, z)


def rasterise(layout: HeatmapLayout, path: Iterable[tuple[float, float] | None], into: Counter,
              cell_m: float = CELL_M) -> None:
    """Add one player's path (metres; None = gap) to `into` as cell counts."""
    paths, current = [], []
    for point in path:
        if point is None:
            paths.append(current)
            current = []
        else:
            current.append(point)
    paths.append(current)
    into.update(rasterise_many(layout, paths, cell_m))


def rasterise_many(layout: HeatmapLayout, paths: list[list[tuple[float, float]]], cell_m: float = CELL_M) -> Counter:
    """Cell counts for many paths (lists of (x, z) metres)."""
    lengths = np.fromiter((len(p) for p in paths), dtype=np.int64, count=len(paths))
    total = int(lengths.sum())
    xz = np.fromiter((c for p in paths for point in p for c in point), dtype=np.float64, count=2 * total).reshape(-1, 2)
    return _rasterise_arrays(layout, xz[:, 0], xz[:, 1], lengths, cell_m)


def _rasterise_arrays(layout: HeatmapLayout, x: np.ndarray, z: np.ndarray, lengths: np.ndarray,
                      cell_m: float = CELL_M) -> Counter:
    """Cell counts for paths given as flat x / z arrays (metres) cut into `lengths` (numpy: the 1000-match player
    heatmap maps ~7 million points). Consecutive points are joined with a point every half cell unless the step is a
    jump (> MAX_STEP_M); same arithmetic as to_cell, so both give the same cells."""
    total = len(x)
    if total == 0:
        return Counter()
    first = np.zeros(total, dtype=bool)
    first[np.cumsum(lengths[lengths > 0])[:-1]] = True
    first[0] = True
    # points per sample: the sample itself, plus the in-between points from the previous sample (same path)
    dx, dz = np.zeros(total), np.zeros(total)
    dx[1:], dz[1:] = x[1:] - x[:-1], z[1:] - z[:-1]
    dist = np.hypot(dx, dz)
    # np.hypot can differ from math.hypot in the last bit: where that could change a step count (positions are
    # whole decimetres, so exact multiples of half a cell are common), use math.hypot as before
    ratio = dist / (cell_m / 2)
    edge = np.flatnonzero((dist > 0) & ((np.abs(ratio - np.rint(ratio)) < 1e-6) | (np.abs(dist - MAX_STEP_M) < 1e-6)))
    for i in edge.tolist():
        dist[i] = math.hypot(dx[i], dz[i])
    joined = ~first & (dist <= MAX_STEP_M)
    steps = np.where(joined, np.maximum(1, (dist / (cell_m / 2)).astype(np.int64)), 1)
    owner = np.repeat(np.arange(total), steps)
    j = np.arange(len(owner)) - np.repeat(np.cumsum(steps) - steps, steps) + 1  # 1..steps
    k = steps[owner]
    inner = j < k
    px, pz = np.zeros(total), np.zeros(total)
    px[1:], pz[1:] = x[:-1], z[:-1]
    t = j / k
    xs = np.where(inner, px[owner] + dx[owner] * t, x[owner])
    zs = np.where(inner, pz[owner] + dz[owner] * t, z[owner])

    x_min, x_max, z_min, z_max, swap, u_min, u_max, v_min, v_max, u_flip, v_flip, last_col, last_row =         _geometry(layout, cell_m)
    keep = (x_min <= xs) & (xs <= x_max) & (z_min <= zs) & (zs <= z_max)
    xs, zs = xs[keep], zs[keep]
    u, v = (zs, xs) if swap else (xs, zs)
    col = np.minimum((((u_max - u) if u_flip else (u - u_min)) / cell_m).astype(np.int64), last_col)
    row = np.minimum((((v - v_min) if v_flip else (v_max - v)) / cell_m).astype(np.int64), last_row)
    counts = np.bincount(col * (last_row + 1) + row, minlength=(last_col + 1) * (last_row + 1))
    cells = np.flatnonzero(counts)
    cols, rows = np.divmod(cells, last_row + 1)
    return Counter(dict(zip(zip(cols.tolist(), rows.tolist()), counts[cells].tolist())))


SPEED_BANDS = [(1.0, "stopped", "Stopped (< 1 m/s)"), (3.0, "slow", "Slow (1-3 m/s)"),
               (6.0, "medium", "Medium (3-6 m/s)"), (float("inf"), "fast", "Fast (6+ m/s)")]


GEAR_FIELDS = {"weapons": "weapon", "ordnance": "ordnance", "tacmod": "tacmod"}
_SPEED_LIMITS = np.array([limit for limit, _, _ in SPEED_BANDS[:-1]])


def _sample_keys(t: dict, mode: str, hz: int) -> np.ndarray:
    """Layer of every sample as an int (-1 = skip): team code, gear index, weapon << 16 | ordnance << 8 | tacmod,
    or speed band index (speed from the movement to the next sample; none after a jump or before an absence)."""
    team = np.frombuffer(t["team"], dtype=np.uint8)
    if mode == "team":
        keys = team.astype(np.int64)
    elif mode in GEAR_FIELDS:
        value = np.frombuffer(t[GEAR_FIELDS[mode]], dtype=np.uint8).astype(np.int64)
        keys = np.where(value == NO_GEAR, -1, value)
    elif mode == "loadout":
        w, o, tm = (np.frombuffer(t[f], dtype=np.uint8).astype(np.int64) for f in ("weapon", "ordnance", "tacmod"))
        keys = np.where((w == NO_GEAR) | (o == NO_GEAR) | (tm == NO_GEAR), -1, (w << 16) | (o << 8) | tm)
    elif mode == "speed":
        x, z = np.frombuffer(t["x"], dtype=np.int16), np.frombuffer(t["z"], dtype=np.int16)
        keys = np.full(len(team), -1, dtype=np.int64)
        if len(team) > 1:
            metres = np.hypot(np.diff(x.astype(np.float64)), np.diff(z.astype(np.float64))) / 10
            band = np.searchsorted(_SPEED_LIMITS, metres * hz, side="right")
            keys[:-1] = np.where((team[1:] != 0) & (metres <= MAX_STEP_M), band, -1)
    else:
        raise ValueError(mode)
    return np.where(team != 0, keys, -1)


def key_value(mode: str, key: int):
    """The int from _sample_keys as layer_label takes it."""
    if mode == "speed":
        return SPEED_BANDS[key][1]
    if mode == "loadout":
        return key >> 16, (key >> 8) & 255, key & 255
    return key


def layer_paths(players: dict, user_ids: set[str] | None = None, mode: str = "team", hz: int = 2):
    """Yield (user_id, key, x, z, lengths): one player's paths in one layer, flat x / z (metres) cut into lengths.
    A path is a run of samples in the same layer, plus the next sample while the player is still present
    (joins it up to the next layer's path); absent samples end it."""
    for uid, t in players.items():
        if user_ids is not None and uid not in user_ids:
            continue
        keys = _sample_keys(t, mode, hz)
        n = len(keys)
        if n == 0:
            continue
        change = np.flatnonzero(keys[1:] != keys[:-1]) + 1
        starts = np.concatenate(([0], change))
        ends = np.concatenate((change, [n]))
        run_keys = keys[starts]
        keep = run_keys >= 0
        starts, ends, run_keys = starts[keep], ends[keep], run_keys[keep]
        if len(starts) == 0:
            continue
        joins = ends < n
        joins[joins] = keys[ends[joins]] >= 0
        lengths = ends - starts + joins
        x = np.frombuffer(t["x"], dtype=np.int16) / 10
        z = np.frombuffer(t["z"], dtype=np.int16) / 10
        for key in np.unique(run_keys).tolist():
            sel = run_keys == key
            run_starts, run_lengths = starts[sel], lengths[sel]
            idx = np.repeat(run_starts, run_lengths) + (
                np.arange(int(run_lengths.sum())) - np.repeat(np.cumsum(run_lengths) - run_lengths, run_lengths))
            yield uid, key, x[idx], z[idx], run_lengths


def _merge(parts: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return tuple(np.concatenate([p[i] for p in parts]) for i in range(3))


def layer_label(mode: str, header: dict, key) -> tuple[str, str]:
    """(layer key used in the response, display label)."""
    from .gear import ORDNANCES, TACMODS, WEAPONS
    from .gear import lookup as gear_lookup

    if mode == "team":
        return ("blue", "Blue") if key == 1 else ("orange", "Orange")
    if mode == "speed":
        return key, next(label for _, k, label in SPEED_BANDS if k == key)
    tables = {"weapons": ("weapons", WEAPONS), "ordnance": ("ordnances", ORDNANCES), "tacmod": ("tacmods", TACMODS)}
    if mode in tables:
        field, table = tables[mode]
        code = header[field][key]
        return code, gear_lookup(table, code).display_name
    w, o, t = header["weapons"][key[0]], header["ordnances"][key[1]], header["tacmods"][key[2]]
    names = [gear_lookup(table, code).display_name for code, table in ((w, WEAPONS), (o, ORDNANCES), (t, TACMODS))]
    return f"{w}|{o}|{t}", " · ".join(names)


MAX_LOADOUT_LAYERS = 7  # the rest fold into "Other" (categorical palette has 8 slots)


def fold_layers(layers: dict[str, Counter], labels: dict[str, str]) -> tuple[dict[str, Counter], dict[str, str]]:
    """Keep the busiest MAX_LOADOUT_LAYERS loadouts, fold the rest into 'other'."""
    if len(layers) <= MAX_LOADOUT_LAYERS:
        return layers, labels
    ranked = sorted(layers, key=lambda k: -sum(layers[k].values()))
    keep = ranked[:MAX_LOADOUT_LAYERS]
    other = Counter()
    for k in ranked[MAX_LOADOUT_LAYERS:]:
        other.update(layers[k])
    out = {k: layers[k] for k in keep} | {"other": other}
    return out, {k: labels[k] for k in keep} | {"other": "Other loadouts"}


def player_layers(layout: HeatmapLayout, players: dict, user_ids: set[str] | None,
                  cell_m: float) -> dict[str, Counter]:
    """One layer per player (keyed by raw user id), for a single match."""
    parts: dict[str, list] = {}
    for uid, _, x, z, lengths in layer_paths(players, user_ids, "team"):
        parts.setdefault(uid, []).append((x, z, lengths))
    return {uid: _rasterise_arrays(layout, *_merge(p), cell_m) for uid, p in parts.items()}


def response(map_name: str, layers: dict[str, Counter], labels: dict[str, str] | None = None, matches: int = 0,
             cell_m: float = CELL_M, mode: str = "team", teams: dict[str, str] | None = None) -> dict:
    layout = HEATMAP_LAYOUTS[map_name]
    cols, rows = grid_size(layout, cell_m)
    return {
        "map": map_name,
        "image": f"/minimaps/{map_name}.png",
        "mode": mode,
        "cols": cols,
        "rows": rows,
        "cell_m": cell_m,
        "matches": matches,
        "layers": [
            {"key": key, "label": (labels or {}).get(key, key),
             "cells": [[c, r, n] for (c, r), n in counts.items()], "max": max(counts.values(), default=0)}
            | ({"team": teams[key]} if teams and key in teams else {})
            for key, counts in layers.items() if counts
        ],
    }


TRACK_MODES = ("team", "weapons", "ordnance", "tacmod", "loadout", "speed")


def build_layers(layout: HeatmapLayout, decoded: Iterable[tuple[dict, dict]], user_ids: set[str] | None,
                 mode: str, cell_m: float) -> tuple[dict[str, Counter], dict[str, str]]:
    """Rasterise every (header, players) track file into one Counter per layer."""
    parts: dict[str, list] = {}
    labels: dict[str, str] = {}
    for header, players in decoded:
        for _, key, x, z, lengths in layer_paths(players, user_ids, mode, header.get("hz", 2)):
            layer, label = layer_label(mode, header, key_value(mode, key))
            labels[layer] = label
            parts.setdefault(layer, []).append((x, z, lengths))
    layers = {layer: _rasterise_arrays(layout, *_merge(p), cell_m) for layer, p in parts.items()}
    if mode == "loadout":
        layers, labels = fold_layers(layers, labels)
    if mode == "speed":  # keep the band order
        order = [k for _, k, _ in SPEED_BANDS]
        layers = {k: layers[k] for k in order if k in layers}
    return layers, labels


# Match card thumbnails: both teams' heat drawn server-side into one small transparent PNG laid over the minimap
# thumbnail, so a page of cards costs one request instead of one heatmap each. 1 m cells: about one cell per pixel on a
# card (the browser smooths it); ~5 KB each. Colours and alpha curve as HeatCanvas in HeatmapView.tsx.
THUMB_CELL_M = 1.0
TEAM_RGB = {"blue": (0x19, 0xD9, 0xFC), "orange": (0xEA, 0x79, 0x24)}


def _png(rgba: np.ndarray) -> bytes:
    """Minimal 8-bit RGBA PNG (no filters) from a rows x cols x 4 uint8 array."""
    height, width, _ = rgba.shape
    raw = np.concatenate([np.zeros((height, 1), np.uint8), rgba.reshape(height, width * 4)], axis=1).tobytes()

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8 bits, RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def thumbnail_png(layout: HeatmapLayout, decoded: tuple[dict, dict]) -> bytes | None:
    """Team heat of one match as a PNG covering the whole minimap; None when nobody was on the map."""
    layers, _ = build_layers(layout, [decoded], None, "team", THUMB_CELL_M)
    if not any(layers.values()):
        return None
    cols, rows = grid_size(layout, THUMB_CELL_M)
    out = np.zeros((rows, cols, 4))
    for team in ("blue", "orange"):  # composited "over", blue first, like the full heatmap
        counts = layers.get(team)
        if not counts:
            continue
        cells = np.array(list(counts.keys()))
        n = np.array(list(counts.values()), dtype=np.float64)
        col, row = cells[:, 0], cells[:, 1]
        a = 0.25 + 0.75 * np.log1p(n) / math.log1p(n.max())
        prev = out[row, col, 3]
        alpha = a + prev * (1 - a)
        for ch, value in enumerate(TEAM_RGB[team]):
            out[row, col, ch] = (value * a + out[row, col, ch] * prev * (1 - a)) / alpha
        out[row, col, 3] = alpha
    out[..., 3] *= 255
    return _png(np.clip(np.rint(out), 0, 255).astype(np.uint8))
