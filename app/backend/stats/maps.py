from typing import NamedTuple

from parser.models import Vec3

MAP_NAMES = {
    "mpl_combat_combustion": "combustion",
    "mpl_combat_dyson": "dyson",
    "mpl_combat_fission": "fission",
    "mpl_combat_gauss": "surge",
}


# Game mode is fixed per map. Older replays (before ~2022 Q4) have no `payload` block, so the
# mode cannot be inferred from the fields present.
MAP_MODES = {"combustion": "capture_point", "dyson": "capture_point", "fission": "payload", "surge": "payload"}


class Bounds(NamedTuple):
    x_min: float
    x_max: float
    z_min: float
    z_max: float


# Old app's play-area bounds (ReplayData.MD); leaving them is counted as a death.
BOUNDS = {
    "dyson": Bounds(-100, 100, -40, 40),
    "combustion": Bounds(-100, 100, -20, 60),
    "surge": Bounds(-50, 70, -60, 150),
    "fission": Bounds(-30, 40, -80, 130),
}


def map_name(map_code: str) -> str:
    return MAP_NAMES.get(map_code, "unknown")


def in_bounds(position: Vec3, b: Bounds) -> bool:
    x, _, z = position
    return b.x_min <= x <= b.x_max and b.z_min <= z <= b.z_max


class HeatmapLayout(NamedTuple):
    """How world (x, z) maps onto the minimap image (docs/reference/minimaps, low-res versions).
    Extents from the old HeatMap.py; axis/flip verified by plotting sample positions (2026-10-30)."""

    x_min: float
    x_max: float
    z_min: float
    z_max: float
    u_axis: str  # world axis along the image width: "x" or "z"
    u_flip: bool  # True: image left = axis max
    v_flip: bool  # True: image top = axis min (False: top = axis max)


HEATMAP_LAYOUTS = {
    "dyson": HeatmapLayout(-54.625, 54.625, -41.125, 28.375, "x", False, False),
    "fission": HeatmapLayout(-74.125, 124.5, -23.125, 34.125, "x", False, False),
    "surge": HeatmapLayout(-55.625, 149.5, -47, 62.625, "x", False, True),
    "combustion": HeatmapLayout(-18.25, 55.625, -87.625, 86.625, "z", False, True),
}
