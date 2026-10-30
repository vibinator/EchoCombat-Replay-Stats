"""Heatmap grids in minimap image space (D18). Cells are `cell_m` metres (default 0.25, D35); consecutive
2 Hz samples are joined with a line unless the player jumped (respawn / teleport)."""

import math
from collections import Counter
from collections.abc import Iterable

from .stats.maps import HEATMAP_LAYOUTS, HeatmapLayout

CELL_M = 0.25  # default; 0.1 (positions are stored to 0.1 m), 0.5 and 1.0 also offered
CELL_SIZES = (0.1, 0.25, 0.5, 1.0)
MAX_STEP_M = 12.0  # > 24 m/s between 0.5 s samples = respawn or teleport: do not draw a line


def grid_size(layout: HeatmapLayout, cell_m: float = CELL_M) -> tuple[int, int]:
    width_m = (layout.z_max - layout.z_min) if layout.u_axis == "z" else (layout.x_max - layout.x_min)
    height_m = (layout.x_max - layout.x_min) if layout.u_axis == "z" else (layout.z_max - layout.z_min)
    return math.ceil(width_m / cell_m), math.ceil(height_m / cell_m)


def to_cell(layout: HeatmapLayout, x: float, z: float, cell_m: float = CELL_M) -> tuple[int, int] | None:
    if not (layout.x_min <= x <= layout.x_max and layout.z_min <= z <= layout.z_max):
        return None
    if layout.u_axis == "z":
        u, u_min, u_max, v, v_min, v_max = z, layout.z_min, layout.z_max, x, layout.x_min, layout.x_max
    else:
        u, u_min, u_max, v, v_min, v_max = x, layout.x_min, layout.x_max, z, layout.z_min, layout.z_max
    col = (u_max - u) if layout.u_flip else (u - u_min)
    row = (v - v_min) if layout.v_flip else (v_max - v)
    cols, rows = grid_size(layout, cell_m)
    return min(int(col / cell_m), cols - 1), min(int(row / cell_m), rows - 1)


def rasterise(layout: HeatmapLayout, path: Iterable[tuple[float, float] | None], into: Counter,
              cell_m: float = CELL_M) -> None:
    """Add one player's path (metres; None = gap) to `into` as cell counts."""
    prev = None
    for point in path:
        if point is None:
            prev = None
            continue
        x, z = point
        if prev is not None:
            px, pz = prev
            dist = math.hypot(x - px, z - pz)
            if dist <= MAX_STEP_M:
                steps = max(1, int(dist / (cell_m / 2)))
                for i in range(1, steps):
                    t = i / steps
                    cell = to_cell(layout, px + (x - px) * t, pz + (z - pz) * t, cell_m)
                    if cell:
                        into[cell] += 1
        cell = to_cell(layout, x, z, cell_m)
        if cell:
            into[cell] += 1
        prev = point


SPEED_BANDS = [(1.0, "stopped", "Stopped (< 1 m/s)"), (3.0, "slow", "Slow (1-3 m/s)"),
               (6.0, "medium", "Medium (3-6 m/s)"), (float("inf"), "fast", "Fast (6+ m/s)")]


def _speed_band(t: dict, i: int, hz: int) -> str | None:
    """Speed from the movement to the next sample (2 Hz)."""
    j = i + 1
    if j >= len(t["team"]) or not t["team"][j]:
        return None
    metres = math.hypot(t["x"][j] - t["x"][i], t["z"][j] - t["z"][i]) / 10
    speed = metres * hz
    if metres > MAX_STEP_M:
        return None  # respawn / teleport
    return next(key for limit, key, _ in SPEED_BANDS if speed < limit)


def layer_key(mode: str, t: dict, i: int, hz: int = 2):
    """Layer of sample i: team code, gear index, (weapon, ordnance, tacmod) or speed band; None = skip."""
    if mode == "team":
        return t["team"][i]
    if mode in ("weapons", "ordnance", "tacmod"):
        value = t[{"weapons": "weapon", "ordnance": "ordnance", "tacmod": "tacmod"}[mode]][i]
        return None if value == 255 else value
    if mode == "loadout":
        key = (t["weapon"][i], t["ordnance"][i], t["tacmod"][i])
        return None if 255 in key else key
    if mode == "speed":
        return _speed_band(t, i, hz)
    raise ValueError(mode)


def track_paths(players: dict, user_ids: set[str] | None = None, mode: str = "team", hz: int = 2):
    """Yield (user_id, key, path) from decoded tracks; a new path starts whenever the layer key changes
    or the player is absent."""
    for uid, t in players.items():
        if user_ids is not None and uid not in user_ids:
            continue
        path: list[tuple[float, float]] = []
        current = None
        for i, team in enumerate(t["team"]):
            key = None if team == 0 else layer_key(mode, t, i, hz)
            if key != current:
                if path and current is not None:
                    if key is not None:  # still present: join the previous layer's path up to this point
                        path.append((t["x"][i] / 10, t["z"][i] / 10))
                    yield uid, current, path
                path, current = [], key
            if key is not None:
                path.append((t["x"][i] / 10, t["z"][i] / 10))
        if path and current is not None:
            yield uid, current, path


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
    layers: dict[str, Counter] = {}
    for uid, _, path in track_paths(players, user_ids, "team"):
        rasterise(layout, path, layers.setdefault(uid, Counter()), cell_m)
    return layers


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
    layers: dict[str, Counter] = {}
    labels: dict[str, str] = {}
    for header, players in decoded:
        for _, key, path in track_paths(players, user_ids, mode, header.get("hz", 2)):
            layer, label = layer_label(mode, header, key)
            labels[layer] = label
            rasterise(layout, path, layers.setdefault(layer, Counter()), cell_m)
    if mode == "loadout":
        layers, labels = fold_layers(layers, labels)
    if mode == "speed":  # keep the band order
        order = [k for _, k, _ in SPEED_BANDS]
        layers = {k: layers[k] for k in order if k in layers}
    return layers, labels
