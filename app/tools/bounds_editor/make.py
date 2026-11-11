"""Bounds editor: review and draw the play-area outline and the spawn points of each map (user, 2026-11-10: the
boxes in stats/maps.py BOUNDS are not the real play areas).

    bounds_editor.bat            measures, writes app/tools/bounds_editor/data.js and opens index.html in the browser

index.html is the editor (no server, no install: a page opened from disk). This script prepares what it shows, from
the position tracks of the latest MATCHES counted matches per map in the data folder (read-only: nothing is written
but data.js):
- each map's picture layout and its current box (stats/maps.py), so what is drawn comes out in the game's own x / z;
- "where players are": every position, also beyond the minimap picture (MARGIN_M around it);
- a measured outline of the play area (measure_outline) and the measured spawn points (measure_spawns): what the
  editor opens with, for the user to check and correct by hand.
Without a data folder the editor still works, just without the overlay and the measured shapes.

The editor saves `echo_bounds.json`: {"<map>": [[x, z], ...]} in metres, one closed outline per map, and under
"spawns" {"<map>": [[x, z, radius], ...]}: circles over the spawn points (user, 2026-11-10), where leaving the play
area is the way back to the war room and must not count as a death."""

import base64
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1])]

import numpy as np  # noqa: E402

from backend import heatmaps, tracks  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.stats.maps import BOUNDS, HEATMAP_LAYOUTS, minimap_url  # noqa: E402

MATCHES = 200  # latest matches per map that are looked at (user, 2026-11-10)
MARGIN_M = 30.0  # shown (and measured) around the minimap picture
# Dyson needs more: two straight tubes along z = 0 bring players in from about x = +-105, 50 m beyond its picture
# (a third of the players of 200 matches used them, flying inwards at about 5 m/s). The war rooms are further out
# still (150 m and more), on every map: the window must stop short of them.
MARGINS = {"dyson": 62.0}
CELL_M = 0.5  # of the overlay and of the grid the outline is measured on
RGB = (0x35, 0xE0, 0xFF)

# The outline: the part of the map players are on. A cell counts when players were in it at least OUTLINE_MIN_SAMPLES
# times (2 a second; fewer is somebody thrown or glitched out for a moment); gaps up to OUTLINE_CLOSE_M across are
# closed, the piece holding the busiest cell is kept (the rest: specks off the map), holes inside it are filled, and
# it is widened by OUTLINE_PAD_M so nobody standing at the very edge is outside. Its edge is then thinned to corners
# no more than OUTLINE_TOLERANCE_M off the measured edge: few enough points to move by hand.
OUTLINE_MIN_SAMPLES = 4
OUTLINE_CLOSE_M = 2.5
OUTLINE_PAD_M = 1.5
OUTLINE_TOLERANCE_M = 1.0

# Spawn points: where players arrive on the map (the first sample inside the outline after one outside it or after
# not being there). The busiest 1 m cell, everything within SPAWN_GATHER_M of it, its middle; again, until a group
# holds under SPAWN_MIN_SHARE of all arrivals. Arrivals sit within 0.7 m of the middle (measured, 600 matches a map),
# and players who walk back out leave from within about 1.5 m of it: beyond 2 m the deaths around a spawn point are
# no more than anywhere else. So the circle is SPAWN_RADIUS_M.
SPAWN_GATHER_M = 8.0
SPAWN_MIN_SHARE = 0.01
SPAWN_RADIUS_M = 1.5


def window(layout) -> tuple[float, float, float, float]:
    """x_min, x_max, z_min, z_max of what the editor shows: the picture and its margin around it."""
    margin = next((MARGINS[name] for name, known in HEATMAP_LAYOUTS.items() if known == layout and name in MARGINS), MARGIN_M)
    return layout.x_min - margin, layout.x_max + margin, layout.z_min - margin, layout.z_max + margin


def _after_war_room(present: np.ndarray, x: np.ndarray, z: np.ndarray, win: tuple[float, float, float, float]) -> np.ndarray:
    """`present`, without what comes before the player's first time away from the map in each spell of being in the
    match. A player loads in at (0, 0, 0) in the middle of every map and is then carried to the war room: that ride
    shows as a straight line of positions across the map, and its start as a "spawn point" in the middle. Everything
    after the first sample outside the window (the war room, 150 m or more away) is real."""
    x0, x1, z0, z1 = win
    away = present & ~((x >= x0) & (x < x1) & (z >= z0) & (z < z1))
    spell = np.cumsum(~present)  # a new number after every absence
    seen = np.zeros(len(present), dtype=bool)
    for number in np.unique(spell[away]):
        mine = spell == number
        first = np.flatnonzero(mine & away)[0]
        seen |= mine & (np.arange(len(present)) >= first)
    return present & seen


def read_tracks(map_: str, settings) -> list[list[tuple[np.ndarray, np.ndarray, np.ndarray]]]:
    """Per match, per player: (present, x, z) of every 2 Hz sample, metres. Latest MATCHES matches of the map.
    `present` leaves out the ride from the load-in spot to the war room (_after_war_room)."""
    db_path = settings.data_dir / "database" / "echovr-stats.db"
    if not db_path.is_file():
        return []
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as db:
        ids = [r for (r,) in db.execute("select replay_id from matches where map = ? order by id desc limit ?", (map_, MATCHES))]
    out = []
    for replay_id in ids:
        try:
            _, players = tracks.decode(tracks.tracks_path(settings.processed_dir, replay_id).read_bytes())
        except (FileNotFoundError, OSError, ValueError):
            continue
        win = window(HEATMAP_LAYOUTS[map_])
        match = []
        for t in players.values():
            x, z = np.frombuffer(t["x"], dtype=np.int16) / 10, np.frombuffer(t["z"], dtype=np.int16) / 10
            match.append((_after_war_room(np.frombuffer(t["team"], dtype=np.uint8) != 0, x, z, win), x, z))
        out.append(match)
    return out


def positions_png(map_: str, matches) -> str | None:
    """PNG data URL: where players were, over the editor's window of the map. Drawn in the picture's own orientation
    (as the minimap), brighter where more time was spent (log scale)."""
    layout = HEATMAP_LAYOUTS[map_]
    x0, x1, z0, z1 = window(layout)
    wide = layout._replace(x_min=x0, x_max=x1, z_min=z0, z_max=z1)  # same axes and flips, a larger area
    cols, rows = heatmaps.grid_size(wide, CELL_M)
    counts = np.zeros(rows * cols, dtype=np.int64)
    for players in matches:
        for present, x, z in players:
            col, row, _ = heatmaps.cells_of(wide, x[present], z[present], CELL_M)
            counts += np.bincount(row * cols + col, minlength=rows * cols)
    if not counts.any():
        return None
    level = np.log1p(counts) / np.log1p(counts.max())
    index = np.where(counts > 0, 1 + np.rint(level * 254), 0).astype(np.uint8).reshape(rows, cols)
    palette = np.zeros((256, 4), dtype=np.uint8)
    palette[1:, :3] = RGB
    palette[1:, 3] = np.rint(255 * (0.25 + 0.7 * np.arange(255) / 254))
    return "data:image/png;base64," + base64.b64encode(heatmaps.png_indexed(index, palette)).decode("ascii")


# ---- the measured outline ---------------------------------------------------------------------------------------------

def _disk(radius_cells: int) -> list[tuple[int, int]]:
    r = radius_cells
    return [(dx, dz) for dx in range(-r, r + 1) for dz in range(-r, r + 1) if dx * dx + dz * dz <= r * r]


def _grow(mask: np.ndarray, radius_cells: int) -> np.ndarray:
    """Every cell within the radius of a set cell (the grid has an empty rim wide enough: nothing wraps round)."""
    out = np.zeros_like(mask)
    for dx, dz in _disk(radius_cells):
        out |= np.roll(np.roll(mask, dx, axis=0), dz, axis=1)
    return out


def _reach(start: np.ndarray, within: np.ndarray) -> np.ndarray:
    """The cells of `within` joined (edge to edge) to `start`."""
    reached = start & within
    while True:
        wider = reached.copy()
        wider[1:, :] |= reached[:-1, :]
        wider[:-1, :] |= reached[1:, :]
        wider[:, 1:] |= reached[:, :-1]
        wider[:, :-1] |= reached[:, 1:]
        wider &= within
        if (wider == reached).all():
            return reached
        reached = wider


def _trace(mask: np.ndarray) -> list[tuple[int, int]]:
    """The outer edge of one piece without holes, as grid corners (ix, iz) in order. Walks the cell edges that have
    the piece on one side only, keeping it on the left."""
    inside = np.pad(mask, 1)

    def cell(ix, iz):
        return inside[ix + 1, iz + 1]

    nxt = {}  # corner -> corners the edge leaving it leads to
    for ix, iz in zip(*np.nonzero(mask)):
        ix, iz = int(ix), int(iz)
        if not cell(ix, iz - 1):
            nxt.setdefault((ix, iz), []).append((ix + 1, iz))
        if not cell(ix + 1, iz):
            nxt.setdefault((ix + 1, iz), []).append((ix + 1, iz + 1))
        if not cell(ix, iz + 1):
            nxt.setdefault((ix + 1, iz + 1), []).append((ix, iz + 1))
        if not cell(ix - 1, iz):
            nxt.setdefault((ix, iz + 1), []).append((ix, iz))
    start = min(nxt)
    ring, at, came = [start], nxt[start][0], start
    while at != start:
        ring.append(at)
        options = nxt[at]
        if len(options) > 1:  # two cells touching at this corner only: turn left, staying on this cell's edge
            ahead = (at[0] - came[0], at[1] - came[1])
            left = (at[0] - ahead[1], at[1] + ahead[0])
            options = [o for o in options if o == left] or options
        came, at = at, options[0]
    return ring


def _thin(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas-Peucker on a closed ring: the corners that keep the line within `tolerance` of the measured one."""
    pts = np.array(points, dtype=np.float64)
    far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))  # cut the ring at two far-apart corners

    def keep(chain: np.ndarray) -> list[int]:
        stack, kept = [(0, len(chain) - 1)], {0, len(chain) - 1}
        while stack:
            a, b = stack.pop()
            if b - a < 2:
                continue
            p, q = chain[a], chain[b]
            line = q - p
            length = np.hypot(*line) or 1.0
            off = np.abs(line[0] * (chain[a + 1:b, 1] - p[1]) - line[1] * (chain[a + 1:b, 0] - p[0])) / length
            worst = int(np.argmax(off))
            if off[worst] > tolerance:
                kept.add(a + 1 + worst)
                stack += [(a, a + 1 + worst), (a + 1 + worst, b)]
        return sorted(kept)

    first = pts[:far + 1]
    second = np.concatenate([pts[far:], pts[:1]])
    return [tuple(first[i]) for i in keep(first)][:-1] + [tuple(second[i]) for i in keep(second)][:-1]


def measure_outline(map_: str, matches) -> tuple[list[list[float]], np.ndarray | None, tuple[float, float]]:
    """(the outline as [[x, z], ...], the grid of cells inside it, the grid's x / z origin). [] when there is no data."""
    x0, x1, z0, z1 = window(HEATMAP_LAYOUTS[map_])
    pad = int(np.ceil((OUTLINE_CLOSE_M + OUTLINE_PAD_M) / CELL_M)) + 2  # an empty rim: growing never reaches the edge
    nx, nz = int(np.ceil((x1 - x0) / CELL_M)) + 2 * pad, int(np.ceil((z1 - z0) / CELL_M)) + 2 * pad
    origin = (x0 - pad * CELL_M, z0 - pad * CELL_M)
    counts = np.zeros(nx * nz, dtype=np.int64)
    for players in matches:
        for present, x, z in players:
            keep = present & (x >= x0) & (x < x1) & (z >= z0) & (z < z1)
            ix = ((x[keep] - origin[0]) / CELL_M).astype(np.int64)
            iz = ((z[keep] - origin[1]) / CELL_M).astype(np.int64)
            counts += np.bincount(ix * nz + iz, minlength=nx * nz)
    counts = counts.reshape(nx, nz)
    if not counts.any():
        return [], None, origin
    close = int(round(OUTLINE_CLOSE_M / CELL_M))
    used = counts >= OUTLINE_MIN_SAMPLES
    closed = ~_grow(~_grow(used, close), close)  # gaps closed: grown, then shrunk by as much
    busiest = np.zeros_like(used)
    busiest[np.unravel_index(counts.argmax(), counts.shape)] = True
    piece = _reach(_grow(busiest, 2), closed)
    piece = _grow(piece, int(round(OUTLINE_PAD_M / CELL_M)))
    rim = np.zeros_like(piece)
    rim[0, :] = rim[-1, :] = rim[:, 0] = rim[:, -1] = True
    piece = ~_reach(rim, ~piece)  # holes filled: everything the outside cannot reach
    ring = [(origin[0] + ix * CELL_M, origin[1] + iz * CELL_M) for ix, iz in _trace(piece)]
    outline = [[round(x, 1), round(z, 1)] for x, z in _thin(ring, OUTLINE_TOLERANCE_M)]
    return outline, piece, origin


def measure_spawns(matches, piece: np.ndarray | None, origin: tuple[float, float]) -> tuple[list[list[float]], list[float]]:
    """([[x, z, radius], ...], the share of all arrivals at each): the spots players arrive on the map at."""
    if piece is None:
        return [], []
    nx, nz = piece.shape

    def inside(x, z):
        ix = np.clip(((x - origin[0]) / CELL_M).astype(np.int64), 0, nx - 1)
        iz = np.clip(((z - origin[1]) / CELL_M).astype(np.int64), 0, nz - 1)
        return piece[ix, iz]

    arrivals = []
    for players in matches:
        for present, x, z in players:
            on = present & inside(x, z)
            if len(on) < 2:
                continue
            came = np.flatnonzero(on[1:] & ~on[:-1]) + 1
            if on[0]:
                came = np.concatenate(([0], came))
            arrivals.append(np.stack([x[came], z[came]], axis=1))
    if not arrivals:
        return [], []
    pts = np.concatenate(arrivals)
    left = np.ones(len(pts), dtype=bool)
    spawns, shares = [], []
    while left.any():
        cells, counts = np.unique(np.floor(pts[left]).astype(np.int64), axis=0, return_counts=True)
        peak = cells[counts.argmax()] + 0.5
        near = np.hypot(pts[:, 0] - peak[0], pts[:, 1] - peak[1]) <= SPAWN_GATHER_M
        mine = near & left
        if mine.sum() < SPAWN_MIN_SHARE * len(pts):
            break
        middle = np.median(pts[mine], axis=0)
        spawns.append([round(float(middle[0]), 1), round(float(middle[1]), 1), SPAWN_RADIUS_M])
        shares.append(round(float(mine.sum() / len(pts)), 3))
        left &= ~near
    return spawns, shares


def main() -> int:
    settings = Settings.from_env()
    maps = {}
    for name, layout in HEATMAP_LAYOUTS.items():
        matches = read_tracks(name, settings)
        outline, piece, origin = measure_outline(name, matches)
        spawns, shares = measure_spawns(matches, piece, origin)
        b = BOUNDS[name]
        maps[name] = {
            "picture": "../../frontend/public" + minimap_url(name).split("?")[0],
            "layout": {"x_min": layout.x_min, "x_max": layout.x_max, "z_min": layout.z_min, "z_max": layout.z_max,
                       "u_axis": layout.u_axis, "u_flip": layout.u_flip, "v_flip": layout.v_flip},
            "window": dict(zip(("x_min", "x_max", "z_min", "z_max"), window(layout))),
            "box": [[b.x_min, b.z_min], [b.x_max, b.z_min], [b.x_max, b.z_max], [b.x_min, b.z_max]],
            "positions": positions_png(name, matches) if matches else None, "matches": len(matches),
            "measured": {"outline": outline, "spawns": spawns, "shares": shares},
        }
        if matches:
            area = piece.sum() * CELL_M * CELL_M
            print(f"{name}: {len(matches)} matches; outline {len(outline)} points around {area:,.0f} m2; "
                  f"{len(spawns)} spawn points: " + ", ".join(f"({x:g}, {z:g}) {share:.0%}" for (x, z, _), share in zip(spawns, shares)))
        else:
            print(f"{name}: no position data found: no overlay, nothing measured")
    (HERE / "data.js").write_text("window.BOUNDS_DATA = " + json.dumps({"maps": maps, "cell_m": CELL_M}) + ";\n", encoding="utf-8")
    page = HERE / "index.html"
    print("Editor:", page)
    if "--no-open" not in sys.argv:
        webbrowser.open(page.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
