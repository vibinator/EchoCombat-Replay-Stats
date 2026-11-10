"""Bounds editor: draw the play-area outline of each map by hand (user, 2026-11-10: the boxes in stats/maps.py BOUNDS
are not the real play areas).

    bounds_editor.bat            writes app/tools/bounds_editor/data.js and opens index.html in the browser

index.html is the editor (no server, no install: a page opened from disk). This script only prepares what it shows:
- each map's picture layout and its current box (stats/maps.py), so what is drawn comes out in the game's own x / z;
- "where players are": every position of the latest MATCHES counted matches per map, also beyond the minimap picture
  (MARGIN_M around it), from the position tracks in the data folder. Read-only: nothing is written but data.js.
Without a data folder the editor still works, just without that overlay.

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

MATCHES = 400  # latest matches per map in the overlay
MARGIN_M = 30.0  # shown around the minimap picture
CELL_M = 0.5  # of the overlay
RGB = (0x35, 0xE0, 0xFF)


def window(layout) -> tuple[float, float, float, float]:
    """x_min, x_max, z_min, z_max of what the editor shows: the picture and MARGIN_M around it."""
    return layout.x_min - MARGIN_M, layout.x_max + MARGIN_M, layout.z_min - MARGIN_M, layout.z_max + MARGIN_M


def positions_png(map_: str, settings) -> tuple[str | None, int]:
    """(PNG data URL, matches used): where players were, over the editor's window of the map. Drawn in the picture's
    own orientation (as the minimap), brighter where more time was spent (log scale)."""
    db_path = settings.data_dir / "database" / "echovr-stats.db"
    if not db_path.is_file():
        return None, 0
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as db:
        ids = [r for (r,) in db.execute("select replay_id from matches where map = ? order by id desc limit ?", (map_, MATCHES))]
    layout = HEATMAP_LAYOUTS[map_]
    x0, x1, z0, z1 = window(layout)
    wide = layout._replace(x_min=x0, x_max=x1, z_min=z0, z_max=z1)  # same axes and flips, a larger area
    cols, rows = heatmaps.grid_size(wide, CELL_M)
    counts = np.zeros(rows * cols, dtype=np.int64)
    used = 0
    for replay_id in ids:
        try:
            _, players = tracks.decode(tracks.tracks_path(settings.processed_dir, replay_id).read_bytes())
        except (FileNotFoundError, OSError, ValueError):
            continue
        used += 1
        for t in players.values():
            present = np.frombuffer(t["team"], dtype=np.uint8) != 0
            x = np.frombuffer(t["x"], dtype=np.int16)[present] / 10
            z = np.frombuffer(t["z"], dtype=np.int16)[present] / 10
            col, row, _ = heatmaps.cells_of(wide, x, z, CELL_M)
            counts += np.bincount(row * cols + col, minlength=rows * cols)
    if not counts.any():
        return None, used
    level = np.log1p(counts) / np.log1p(counts.max())
    index = np.where(counts > 0, 1 + np.rint(level * 254), 0).astype(np.uint8).reshape(rows, cols)
    palette = np.zeros((256, 4), dtype=np.uint8)
    palette[1:, :3] = RGB
    palette[1:, 3] = np.rint(255 * (0.25 + 0.7 * np.arange(255) / 254))
    png = heatmaps.png_indexed(index, palette)
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii"), used


def main() -> int:
    settings = Settings.from_env()
    maps = {}
    for name, layout in HEATMAP_LAYOUTS.items():
        heat, used = positions_png(name, settings)
        b = BOUNDS[name]
        maps[name] = {
            "picture": "../../frontend/public" + minimap_url(name).split("?")[0],
            "layout": {"x_min": layout.x_min, "x_max": layout.x_max, "z_min": layout.z_min, "z_max": layout.z_max,
                       "u_axis": layout.u_axis, "u_flip": layout.u_flip, "v_flip": layout.v_flip},
            "window": dict(zip(("x_min", "x_max", "z_min", "z_max"), window(layout))),
            "box": [[b.x_min, b.z_min], [b.x_max, b.z_min], [b.x_max, b.z_max], [b.x_min, b.z_max]],
            "positions": heat, "matches": used,
        }
        print(f"{name}: overlay from {used} matches" if heat else f"{name}: no position data found, no overlay")
    (HERE / "data.js").write_text("window.BOUNDS_DATA = " + json.dumps({"maps": maps, "cell_m": CELL_M}) + ";\n", encoding="utf-8")
    page = HERE / "index.html"
    print("Editor:", page)
    if "--no-open" not in sys.argv:
        webbrowser.open(page.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
