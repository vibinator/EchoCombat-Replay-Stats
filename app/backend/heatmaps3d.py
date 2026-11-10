"""3D heatmaps: the heat of heatmaps.py in world-space voxels (VOX_M cubes), for the 3D view of a heatmap.

Layers are the same as the 2D ones (team, player, weapon, ordnance, tac mod, loadout, speed band) and are cut from the
2 Hz tracks.bin exactly as there; only the height comes from the 5 Hz head positions of tracks3d.bin (the nearest sample
in time; kept per match in heights.bin, see there). A match whose 3D tracks are not on disk is left out (a heatmap over hundreds of matches must not queue a
replay parse for each); the answer says how many matches it covers (`matches_3d`).
"""

import base64
import json
import logging
import os
import struct
import threading
import zlib
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np

from . import heatmaps, tracks, tracks3d
from .stats.maps import HEATMAP_LAYOUTS, HeatmapLayout

log = logging.getLogger(__name__)

VOX_M = 0.5
Y_LIMIT_M = 150.0  # heights beyond this are glitches (the world is a few tens of metres tall)

Voxels = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]  # ix, iy, iz, count (iy in world voxels, may be < 0)


def aligned_dm(track: dict, track3d: dict, hz: int, hz3d: int) -> np.ndarray | None:
    """Height in decimetres (as stored) of every sample of a 2 Hz track: the nearest 5 Hz sample in time, or the
    nearest one where the player was present when that sample has none. None = no height known for this player in
    this match."""
    n3 = len(track3d["y"])
    present = np.flatnonzero(np.frombuffer(track3d["team"], dtype=np.uint8) != 0)
    if n3 == 0 or len(present) == 0:
        return None
    n = len(track["team"])
    j = np.clip(np.rint(np.arange(n) * (hz3d / hz)).astype(np.int64), 0, n3 - 1)
    at = np.searchsorted(present, j)
    left, right = present[np.clip(at - 1, 0, len(present) - 1)], present[np.clip(at, 0, len(present) - 1)]
    nearest = np.where(np.abs(j - left) <= np.abs(right - j), left, right)
    return np.frombuffer(track3d["y"], dtype=np.int16)[nearest]


def aligned_y(track: dict, track3d: dict, hz: int, hz3d: int) -> np.ndarray | None:
    """aligned_dm in metres."""
    dm = aligned_dm(track, track3d, hz, hz3d)
    return None if dm is None else dm / 10


Heights = dict[str, np.ndarray]  # user id -> the height (int16 decimetres) of every sample of the player's 2 Hz track


def heights_of(players: dict, players3d: dict, hz: int, hz3d: int) -> Heights:
    """The height of every player of a match that has one (players without a 3D track are left out)."""
    out = {}
    for uid, t in players.items():
        t3 = players3d.get(uid)
        dm = aligned_dm(t, t3, hz, hz3d) if t3 is not None else None
        if dm is not None:
            out[uid] = dm
    return out


# heights.bin: a match's Heights, kept next to its tracks3d.bin (2026-11-10). A player heatmap over 2,000 matches
# needs one number per sample of one player, and got it by unpacking 2,000 tracks3d.bin files (~95 KB each, 400 KB
# unpacked: every player's position, facing and hands at 5 Hz): 18 s on the live server. This file is a few KB and
# already lined up with the 2 Hz samples. Written the first time a heatmap needs the match (or by
# tools/backfill_tracks3d.py --heights); built again when tracks3d.bin changes (its time and size are in the header)
# or the 2 Hz track has another number of samples. zlib(u32 header length, header JSON, int16[samples] per player).
HEIGHTS_VERSION = 1
HEIGHTS_NAME = "heights.bin"


def heights_path(tracks3d_file: Path) -> Path:
    return tracks3d_file.with_name(HEIGHTS_NAME)


def encode_heights(heights: Heights, samples: int, source: list[int]) -> bytes:
    header = json.dumps({"version": HEIGHTS_VERSION, "samples": samples, "source": source, "players": list(heights)},
                        separators=(",", ":")).encode()
    return zlib.compress(b"".join([struct.pack("<I", len(header)), header,
                                   *(np.ascontiguousarray(h, dtype="<i2").tobytes() for h in heights.values())]), 1)


def decode_heights(data: bytes, samples: int, source: list[int]) -> Heights | None:
    """None = not for this version, these 2 Hz samples or this tracks3d.bin."""
    raw = zlib.decompress(data)
    (length,) = struct.unpack_from("<I", raw)
    header = json.loads(raw[4 : 4 + length])
    if header.get("version") != HEIGHTS_VERSION or header["samples"] != samples or header["source"] != source:
        return None
    all_ = np.frombuffer(raw, dtype="<i2", count=samples * len(header["players"]), offset=4 + length)
    return {uid: all_[i * samples : (i + 1) * samples] for i, uid in enumerate(header["players"])}


def write_heights(path: Path, heights: Heights, samples: int, source: list[int]) -> bool:
    """False = not written (a folder that cannot be written to, a full disk): the heatmap is drawn all the same."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmph")
    try:
        tmp.write_bytes(encode_heights(heights, samples, source))
        os.replace(tmp, path)
        return True
    except OSError as e:
        log.debug("%s not written: %s", path, e)
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def match_heights(two: tuple[dict, dict], tracks3d_file: Path, save: bool = True) -> Heights | None:
    """The heights of a match's players: from heights.bin when it is there and still fits, else worked out from
    tracks3d.bin (and saved for the next time). None = the match has no (readable) 3D tracks."""
    try:
        st = tracks3d_file.stat()
    except OSError:
        return None
    header, players = two
    samples, source = header["samples"], [st.st_mtime_ns, st.st_size]
    path = heights_path(tracks3d_file)
    try:
        found = decode_heights(path.read_bytes(), samples, source)
        if found is not None:
            return found
    except FileNotFoundError:
        pass
    except (OSError, zlib.error, struct.error, ValueError, KeyError, TypeError):
        log.warning("%s is damaged; it is built again", path)
    three = tracks3d.read(tracks3d_file)
    if three is None:
        return None
    found = heights_of(players, three[1], header.get("hz", tracks.HZ), three[0].get("hz", tracks3d.HZ))
    if save:
        write_heights(path, found, samples, source)
    return found


def save_heights(tracks_file: Path, tracks3d_file: Path) -> bool:
    """Writes a match's heights.bin unless a fitting one is there (after its tracks are written, and the backfill
    tool). False = no tracks to make it from, or it could not be written."""
    two = tracks.read(tracks_file)
    if two is None or match_heights(two, tracks3d_file) is None:
        return False
    return heights_path(tracks3d_file).exists()


def layer_paths3d(players: dict, heights: Heights, user_ids: set[str] | None, mode: str, hz: int):
    """layer_paths with the height too: (user_id, key, x, y, z, lengths), players without a height skipped."""
    usable = {uid: t for uid, t in players.items() if uid in heights and (user_ids is None or uid in user_ids)}
    for uid, key, idx, lengths in heatmaps.layer_runs(usable, user_ids, mode, hz):
        t = usable[uid]
        yield (uid, key, np.frombuffer(t["x"], dtype=np.int16)[idx] / 10, heights[uid][idx] / 10,
               np.frombuffer(t["z"], dtype=np.int16)[idx] / 10, lengths)


def _pair(p2: Path, p3: Path) -> tuple[tuple[dict, dict], Heights | None] | None:
    two = tracks.read(p2)
    return None if two is None else (two, match_heights(two, p3))


def read_pairs(paths: Iterable[tuple[Path, Path]]) -> Iterator[tuple[tuple[dict, dict], Heights | None]]:
    """(tracks, heights) of each (tracks.bin, tracks3d.bin) pair, in order, a few matches at a time in parallel; a
    match without readable 2 Hz tracks is skipped, one without 3D tracks comes with None (they are never built here)."""
    pending: list = []
    for p2, p3 in paths:
        pending.append(tracks._readers.submit(_pair, p2, p3))
        if len(pending) >= tracks.READ_AHEAD:
            if (got := pending.pop(0).result()) is not None:
                yield got
    for item in pending:
        if (got := item.result()) is not None:
            yield got


# Voxel counts are kept as (key, count) arrays, key = ((iy + Y_OFFSET) * nz + iz) * nx + ix: the same for every part
# of a heatmap, so parts counted one after the other (FLUSH_SAMPLES) add up without holding every point in memory.
Y_OFFSET = int(np.ceil(Y_LIMIT_M / VOX_M)) + 1
DENSE_CELLS = 16_000_000  # count in a plain array up to this many voxels in the box of a part (128 MB), else sort
DENSE_PER_POINT = 8  # ... and only when the part has a point per this many voxels: going through an empty box costs more than sorting
FLUSH_SAMPLES = 400_000  # track samples of one layer voxelised at a time (~170 matches of one player)


def _points(x: np.ndarray, y: np.ndarray, z: np.ndarray, lengths: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every sample, then a point every half voxel between consecutive samples of a path unless the step is a jump:
    the points of heatmaps._densify(x, z, lengths, VOX_M, y), to the last bit, in another order (the samples are not
    carried through the interpolation, which is half the work when most of a track is standing or drifting)."""
    total = len(x)
    first = np.zeros(total, dtype=bool)
    first[np.cumsum(lengths[lengths > 0])[:-1]] = True
    first[0] = True
    dx, dy, dz = np.zeros(total), np.zeros(total), np.zeros(total)
    dx[1:], dy[1:], dz[1:] = x[1:] - x[:-1], y[1:] - y[:-1], z[1:] - z[:-1]
    dist = np.sqrt(dx * dx + dy * dy + dz * dz)
    steps = (dist / (VOX_M / 2)).astype(np.int64)
    steps[first | (dist > heatmaps.MAX_STEP_M)] = 1
    between = np.maximum(steps, 1) - 1  # points before the sample, on the way from the one before it
    moving = np.flatnonzero(between)
    if len(moving) == 0:
        return x, y, z
    between = between[moving]
    owner = np.repeat(moving, between)
    t = (np.arange(len(owner)) - np.repeat(np.cumsum(between) - between, between) + 1) / steps[owner]
    before = owner - 1
    return (np.concatenate((x, x[before] + dx[owner] * t)), np.concatenate((y, y[before] + dy[owner] * t)),
            np.concatenate((z, z[before] + dz[owner] * t)))


def _keys(layout: HeatmapLayout, x: np.ndarray, y: np.ndarray, z: np.ndarray, lengths: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(key, count) of the paths' voxels (flat arrays, metres, cut into `lengths`; joined like the 2D heatmap's)."""
    empty = np.zeros(0, dtype=np.int64)
    if len(x) == 0:
        return empty, empty
    xs, ys, zs = _points(x, y, z, lengths)
    keep = (layout.x_min <= xs) & (xs <= layout.x_max) & (layout.z_min <= zs) & (zs <= layout.z_max) & (np.abs(ys) <= Y_LIMIT_M)
    nx, nz = grid_dims(layout)
    ix = np.minimum(((xs[keep] - layout.x_min) / VOX_M).astype(np.int64), nx - 1)
    iz = np.minimum(((zs[keep] - layout.z_min) / VOX_M).astype(np.int64), nz - 1)
    iy = np.floor(ys[keep] / VOX_M).astype(np.int64)
    if len(ix) == 0:
        return empty, empty
    low, high = int(iy.min()), int(iy.max())
    flat = ((iy - low) * nz + iz) * nx + ix
    cells = (high - low + 1) * nx * nz
    if cells <= DENSE_CELLS and cells <= DENSE_PER_POINT * len(flat):
        counts = np.bincount(flat, minlength=cells)
        flat = np.flatnonzero(counts)
        n = counts[flat]
    else:  # few points (one of many loadouts), or a glitch far above or below the map
        flat, n = np.unique(flat, return_counts=True)
    return flat + (low + Y_OFFSET) * nx * nz, n


def _add(parts: list[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    """(key, count) parts as one, the counts of a voxel in several parts added up."""
    if len(parts) == 1:
        return parts[0]
    keys, inverse = np.unique(np.concatenate([k for k, _ in parts]), return_inverse=True)
    return keys, np.bincount(inverse, weights=np.concatenate([n for _, n in parts]), minlength=len(keys)).astype(np.int64)


def _voxels(layout: HeatmapLayout, keys: np.ndarray, n: np.ndarray) -> Voxels:
    nx, nz = grid_dims(layout)
    iy, rest = np.divmod(keys, nx * nz)
    iz, ix = np.divmod(rest, nx)
    return ix, iy - Y_OFFSET, iz, n


def voxelise(layout: HeatmapLayout, x: np.ndarray, y: np.ndarray, z: np.ndarray, lengths: np.ndarray) -> Voxels:
    """Voxel counts of paths (flat arrays, metres, cut into `lengths`; joined like the 2D heatmap's)."""
    return _voxels(layout, *_keys(layout, x, y, z, lengths))


def grid_dims(layout: HeatmapLayout) -> tuple[int, int]:
    """(nx, nz): voxels along world x and z."""
    return (int(np.ceil((layout.x_max - layout.x_min) / VOX_M)), int(np.ceil((layout.z_max - layout.z_min) / VOX_M)))


class _Layers:
    """Paths gathered per layer and voxelised a part at a time."""

    def __init__(self, layout: HeatmapLayout):
        self.layout = layout
        self.waiting: dict[str, list] = {}
        self.samples: dict[str, int] = {}
        self.counted: dict[str, list] = {}

    def add(self, layer: str, x: np.ndarray, y: np.ndarray, z: np.ndarray, lengths: np.ndarray) -> None:
        self.waiting.setdefault(layer, []).append((x, y, z, lengths))
        self.samples[layer] = self.samples.get(layer, 0) + len(x)
        if self.samples[layer] >= FLUSH_SAMPLES:
            self._flush(layer)

    def _flush(self, layer: str) -> None:
        parts = self.waiting.pop(layer, [])
        self.samples[layer] = 0
        if parts:
            self.counted.setdefault(layer, []).append(
                _keys(self.layout, *(np.concatenate([p[i] for p in parts]) for i in range(4))))

    def result(self) -> dict[str, Voxels]:
        """In the order the layers were first seen."""
        order = list(self.samples)
        for layer in order:
            self._flush(layer)
        return {layer: _voxels(self.layout, *_add(self.counted[layer])) for layer in order}


def build_layers3d(layout: HeatmapLayout, decoded: Iterable[tuple[tuple[dict, dict], Heights | None]],
                   user_ids: set[str] | None, mode: str) -> tuple[dict[str, Voxels], dict[str, str], int]:
    """Voxelise every ((header, players), heights | None) pair into one Voxels per layer.
    Returns (layers, labels, matches with 3D tracks)."""
    found = _Layers(layout)
    labels: dict[str, str] = {}
    used = 0
    for (header, players), heights in decoded:
        if heights is None:
            continue
        used += 1
        for _, key, x, y, z, lengths in layer_paths3d(players, heights, user_ids, mode, header.get("hz", 2)):
            layer, label = heatmaps.layer_label(mode, header, heatmaps.key_value(mode, key))
            labels[layer] = label
            found.add(layer, x, y, z, lengths)
    layers = found.result()
    if mode == "loadout":
        layers, labels = _fold(layers, labels)
    if mode == "speed":
        layers = {k: layers[k] for _, k, _ in heatmaps.SPEED_BANDS if k in layers}
    return layers, labels, used


def player_layers3d(layout: HeatmapLayout, players: dict, heights: Heights, user_ids: set[str] | None,
                    hz: int) -> dict[str, Voxels]:
    """One layer per player (raw user id), for a single match."""
    found = _Layers(layout)
    for uid, _, x, y, z, lengths in layer_paths3d(players, heights, user_ids, "team", hz):
        found.add(uid, x, y, z, lengths)
    return found.result()


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
