"""3D heatmaps: the heat of heatmaps.py in world-space voxels (VOX_M cubes), for the 3D view of a heatmap.

Layers are the same as the 2D ones (team, player, weapon, ordnance, tac mod, loadout, speed band) and are cut from the
2 Hz tracks.bin exactly as there; only the height comes from the 5 Hz head positions of tracks3d.bin (the nearest sample
in time). A match whose 3D tracks are not on disk is left out (a heatmap over hundreds of matches must not queue a
replay parse for each); the answer says how many matches it covers (`matches_3d`).
"""

import base64
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np

from . import heatmaps, tracks, tracks3d
from .stats.maps import HEATMAP_LAYOUTS, HeatmapLayout

VOX_M = 0.5
Y_LIMIT_M = 150.0  # heights beyond this are glitches (the world is a few tens of metres tall)

Voxels = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]  # ix, iy, iz, count (iy in world voxels, may be < 0)


def aligned_y(track: dict, track3d: dict, hz: int, hz3d: int) -> np.ndarray | None:
    """Height in metres of every sample of a 2 Hz track: the nearest 5 Hz sample in time, or the nearest one where the
    player was present when that sample has none. None = no height known for this player in this match."""
    n3 = len(track3d["y"])
    present = np.flatnonzero(np.frombuffer(track3d["team"], dtype=np.uint8) != 0)
    if n3 == 0 or len(present) == 0:
        return None
    n = len(track["team"])
    j = np.clip(np.rint(np.arange(n) * (hz3d / hz)).astype(np.int64), 0, n3 - 1)
    at = np.searchsorted(present, j)
    left, right = present[np.clip(at - 1, 0, len(present) - 1)], present[np.clip(at, 0, len(present) - 1)]
    nearest = np.where(np.abs(j - left) <= np.abs(right - j), left, right)
    return np.frombuffer(track3d["y"], dtype=np.int16)[nearest] / 10


def _with_height(players: dict, players3d: dict, hz: int, hz3d: int) -> dict[str, np.ndarray]:
    out = {}
    for uid, t in players.items():
        t3 = players3d.get(uid)
        y = aligned_y(t, t3, hz, hz3d) if t3 is not None else None
        if y is not None:
            out[uid] = y
    return out


def layer_paths3d(players: dict, players3d: dict, user_ids: set[str] | None, mode: str, hz: int, hz3d: int):
    """layer_paths with the height too: (user_id, key, x, y, z, lengths), players without a 3D track skipped."""
    heights = _with_height(players, players3d, hz, hz3d)
    usable = {uid: t for uid, t in players.items() if uid in heights}
    for uid, key, idx, lengths in heatmaps.layer_runs(usable, user_ids, mode, hz):
        t = usable[uid]
        yield (uid, key, np.frombuffer(t["x"], dtype=np.int16)[idx] / 10, heights[uid][idx],
               np.frombuffer(t["z"], dtype=np.int16)[idx] / 10, lengths)


def read_pairs(paths: Iterable[tuple[Path, Path]]) -> Iterator[tuple[tuple[dict, dict], tuple[dict, dict] | None]]:
    """(tracks, tracks3d) of each (tracks.bin, tracks3d.bin) pair, in order, a few files at a time in parallel; a match
    without readable 2 Hz tracks is skipped, one without 3D tracks comes with None (it is never built here)."""
    pending: list = []

    def take(item):
        two, three = item[0].result(), item[1].result()
        return None if two is None else (two, three)

    for p2, p3 in paths:
        pending.append((tracks._readers.submit(tracks.read, p2), tracks._readers.submit(tracks3d.read, p3)))
        if len(pending) >= tracks.READ_AHEAD:
            if (got := take(pending.pop(0))) is not None:
                yield got
    for item in pending:
        if (got := take(item)) is not None:
            yield got


def _merge4(parts: list) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return tuple(np.concatenate([p[i] for p in parts]) for i in range(4))


def voxelise(layout: HeatmapLayout, x: np.ndarray, y: np.ndarray, z: np.ndarray, lengths: np.ndarray) -> Voxels:
    """Voxel counts of paths (flat arrays, metres, cut into `lengths`; joined like the 2D heatmap's)."""
    empty = np.zeros(0, dtype=np.int64)
    if len(x) == 0:
        return empty, empty, empty, empty
    xs, zs, ys = heatmaps._densify(x, z, lengths, VOX_M, y)
    keep = (layout.x_min <= xs) & (xs <= layout.x_max) & (layout.z_min <= zs) & (zs <= layout.z_max) & (np.abs(ys) <= Y_LIMIT_M)
    nx, nz = grid_dims(layout)
    ix = np.minimum(((xs[keep] - layout.x_min) / VOX_M).astype(np.int64), nx - 1)
    iz = np.minimum(((zs[keep] - layout.z_min) / VOX_M).astype(np.int64), nz - 1)
    iy = np.floor(ys[keep] / VOX_M).astype(np.int64)
    if len(ix) == 0:
        return empty, empty, empty, empty
    iy0 = int(iy.min())
    flat, n = np.unique((((iy - iy0) * nz) + iz) * nx + ix, return_counts=True)
    iy_, rest = np.divmod(flat, nx * nz)
    iz_, ix_ = np.divmod(rest, nx)
    return ix_, iy_ + iy0, iz_, n


def grid_dims(layout: HeatmapLayout) -> tuple[int, int]:
    """(nx, nz): voxels along world x and z."""
    return (int(np.ceil((layout.x_max - layout.x_min) / VOX_M)), int(np.ceil((layout.z_max - layout.z_min) / VOX_M)))


def build_layers3d(layout: HeatmapLayout, decoded: Iterable[tuple[tuple[dict, dict], tuple[dict, dict] | None]],
                   user_ids: set[str] | None, mode: str) -> tuple[dict[str, Voxels], dict[str, str], int]:
    """Voxelise every ((header, players), (header3d, players3d) | None) pair into one Voxels per layer.
    Returns (layers, labels, matches with 3D tracks)."""
    parts: dict[str, list] = {}
    labels: dict[str, str] = {}
    used = 0
    for (header, players), three in decoded:
        if three is None:
            continue
        used += 1
        hz = header.get("hz", 2)
        for _, key, x, y, z, lengths in layer_paths3d(players, three[1], user_ids, mode, hz, three[0].get("hz", 5)):
            layer, label = heatmaps.layer_label(mode, header, heatmaps.key_value(mode, key))
            labels[layer] = label
            parts.setdefault(layer, []).append((x, y, z, lengths))
    layers = {layer: voxelise(layout, *_merge4(p)) for layer, p in parts.items()}
    if mode == "loadout":
        layers, labels = _fold(layers, labels)
    if mode == "speed":
        layers = {k: layers[k] for _, k, _ in heatmaps.SPEED_BANDS if k in layers}
    return layers, labels, used


def player_layers3d(layout: HeatmapLayout, players: dict, players3d: dict, user_ids: set[str] | None,
                    hz: int, hz3d: int) -> dict[str, Voxels]:
    """One layer per player (raw user id), for a single match."""
    parts: dict[str, list] = {}
    for uid, _, x, y, z, lengths in layer_paths3d(players, players3d, user_ids, "team", hz, hz3d):
        parts.setdefault(uid, []).append((x, y, z, lengths))
    return {uid: voxelise(layout, *_merge4(p)) for uid, p in parts.items()}


def _fold(layers: dict[str, Voxels], labels: dict[str, str]) -> tuple[dict[str, Voxels], dict[str, str]]:
    """The busiest MAX_LOADOUT_LAYERS loadouts as they are, the rest as 'other' (as heatmaps.fold_layers)."""
    if len(layers) <= heatmaps.MAX_LOADOUT_LAYERS:
        return layers, labels
    ranked = sorted(layers, key=lambda k: -int(layers[k][3].sum()))
    keep = ranked[: heatmaps.MAX_LOADOUT_LAYERS]
    other: Counter = Counter()
    for k in ranked[heatmaps.MAX_LOADOUT_LAYERS:]:
        ix, iy, iz, n = layers[k]
        other.update(dict(zip(zip(ix.tolist(), iy.tolist(), iz.tolist()), n.tolist())))
    if other:
        keys = np.array(list(other.keys()), dtype=np.int64)
        merged: Voxels = (keys[:, 0], keys[:, 1], keys[:, 2], np.array(list(other.values()), dtype=np.int64))
    else:
        merged = layers[ranked[-1]]
    return ({k: layers[k] for k in keep} | {"other": merged},
            {k: labels[k] for k in keep} | {"other": "Other loadouts"})


def pack(layer: Voxels, nx: int, nz: int, iy0: int) -> dict:
    """A layer's voxels, packed like heatmaps.pack_cells: index = ((iy - iy0) * nz + iz) * nx + ix."""
    ix, iy, iz, n = layer
    if len(n) == 0:
        return {"d": "", "n": "", "w": 2}
    index = ((iy - iy0) * nz + iz) * nx + ix
    order = np.argsort(index, kind="stable")
    index, n = index[order], n[order]
    width = 2 if n.max() < 65536 else 4
    return {"d": base64.b64encode(np.diff(index, prepend=0).astype("<u4").tobytes()).decode("ascii"),
            "n": base64.b64encode(n.astype("<u2" if width == 2 else "<u4").tobytes()).decode("ascii"), "w": width}


def unpack(packed: dict, nx: int, nz: int, iy0: int) -> list[tuple[int, int, int, int]]:
    """[(ix, iy, iz, n)], the inverse of pack (tests, tools)."""
    index = np.cumsum(np.frombuffer(base64.b64decode(packed["d"]), dtype="<u4").astype(np.int64))
    n = np.frombuffer(base64.b64decode(packed["n"]), dtype="<u2" if packed["w"] == 2 else "<u4")
    return [(int(i % nx), int(i // (nx * nz)) + iy0, int((i // nx) % nz), int(v)) for i, v in zip(index, n)]


def response(map_name: str, layers: dict[str, Voxels], labels: dict[str, str] | None = None, matches: int = 0,
             matches_3d: int = 0, mode: str = "team", teams: dict[str, str] | None = None,
             model: str | None = None) -> dict:
    layout = HEATMAP_LAYOUTS[map_name]
    nx, nz = grid_dims(layout)
    lows = [int(v[1].min()) for v in layers.values() if len(v[1])]
    highs = [int(v[1].max()) for v in layers.values() if len(v[1])]
    iy0 = min(lows, default=0)
    return {
        "map": map_name,
        "model": model,
        "mode": mode,
        "vox_m": VOX_M,
        "nx": nx,
        "nz": nz,
        "ny": max(highs, default=0) - iy0 + 1,
        "origin": [layout.x_min, iy0 * VOX_M, layout.z_min],  # world position of the corner of voxel (0, 0, 0)
        "matches": matches,
        "matches_3d": matches_3d,
        "layers": [
            {"key": key, "label": (labels or {}).get(key, key), "packed": pack(v, nx, nz, iy0), "max": int(v[3].max())}
            | ({"team": teams[key]} if teams and key in teams else {})
            for key, v in layers.items() if len(v[3])
        ],
    }
