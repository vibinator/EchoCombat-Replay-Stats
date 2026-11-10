"""All-time heat per map for the home page's "Matches per map" cards: where players have been over every counted
match - both teams, or only while holding one weapon, ordnance or tac mod - as one small PNG per map laid over the
minimap thumbnail.

The whole archive is far too much to rasterise for a request (33 000 matches, ~300 million samples: minutes on the
NAS), so the counts are kept: per map one grid of CELL_M cells per layer (LAYERS: the two teams and every gear code),
saved in the data folder with the replay ids already added. It is counted once per calendar month (user,
2026-11-10), on the first visit of the month, a batch at a time in a background thread; the cards keep showing last
month's counts until the new ones are complete. All time is counted from nothing each month (since 2026-11-10: what
a match adds also comes from the database and from files that are written again when a replay is reprocessed -
the arm, the deaths, the upside-down flags - and adding only new replays never picked that up); it
goes into a second file (map-heat.next.npz) and takes the place of the first when done, so a restart half way
carries on where it was. A time range (below) is brought up to date in place: it only reads the tracks of replays
that are new, and subtracts those that left it or stopped counting (a duplicate recording, D13).

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

Two more groups of layers since 2026-11-10 (user), counted in the same pass:
- hand: left- and right-handed players. The arm setting is one value per player and match, already in the database
  (match_players.frames_left_arm / frames_right_arm); a player whose arm is unknown is in neither layer.
- pose: upside down and upright. From the flags of tracks.bin (version 3, 2026-11-10: the body's up points down,
  exactly the "Inverted" statistic). Matches processed before that have no flags: for those the head's roll in
  tracks3d.bin (5 Hz, version 3 and up) stands in when that file exists (measured against the stored upside-down
  share of 2,465 players: correlation 0.96, a little lower because the head is not the body), and a match with
  neither is in no pose layer ("upright" is the rest of the same matches, which keeps the "favoured" view fair).
  Reading the archive again (console: reprocess-all) gives every match the flags.

Two more since the same day (user's pick from a list). (A third, the winners and the losers of decided matches, was
made too and taken out again the same evening: "meaningless", user. FORMAT 6.)
- speed: the four speed bands of the match heatmaps (heatmaps.SPEED_BANDS), from the movement to the next sample.
- death: the estimated deaths (events of type death_est: the last spot in bounds before a player left them). Points,
  not time: about six a cell over the whole archive, so they are smoothed over a metre (SPARSE_BLUR) and their
  "favoured" view measures against where everybody is (deaths per time spent there), not against a group of their own.

Payload maps also get the payload's own movement (user, 2026-11-10), from the payload distance series of tracks.bin:
per metre of the route how long it was there, how long it stood still and how fast it went forward (payload_counts),
drawn as a band along the route (PAYLOAD_LAYERS).

And any layer can be laid against any other ("compare", render_compare): where the one is relatively more often than
the other, each in its own colour.

Time ranges (user, 2026-11-10): besides all time, the last RANGES days. Each range is a MapHeat of its own with its own
file (map-heat-30d.npz): the matches that started in the range, brought up to date once a day (the day's new matches
added, those that fell out of the range taken away again: the same two steps as above, a few hundred matches). Their
counts would triple the memory, so a range is only held while it is looked at: loaded from its file on the first
request (well under a second) and let go after IDLE_S without one. Its answers stay in the response cache meanwhile.

Delete the file to build it again from nothing (also done when FORMAT, the cell size, a map's extents or the gear
tables change)."""

import base64
import io
import json
import logging
import os
import struct
import threading
import time
import zlib
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import select

from . import heatmaps, tracks
from .duplicates import counted
from .gear import ORDNANCES, TACMODS, WEAPONS
from .models import Event, Match, MatchPlayer, Player
from .stats.map_objects import PAYLOAD_ROUTES
from .stats.maps import HEATMAP_LAYOUTS

log = logging.getLogger(__name__)

FORMAT = 6  # of the saved file: another number = start again (3: Fission turned top to bottom; 4: hand and pose;
# 5: result, speed and death; 6: result taken out)
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
# Groups that are not gear: (group, ((code, label), ...)). Like gear, the layers of one group never overlap, and
# together they are "everybody this is known of": what the favoured view measures against.
EXTRA_GROUPS = (("hand", (("left", "Left-handed"), ("right", "Right-handed"))),
                ("pose", (("upside", "Upside down"), ("upright", "Upright"))),
                ("speed", tuple((code, label) for _, code, label in heatmaps.SPEED_BANDS)),
                ("death", (("all", "Deaths"),)))
# Groups measured against where everybody is instead of against the group itself ("favoured" view), and smoothed more:
# events, a few per cell, not time spent.
SPARSE_GROUPS = ("death",)
SPARSE_BLUR = 3  # cells each way: about a metre
SPARSE_MIN_EXPECTED = 1.0  # per cell after smoothing (FAVOURED_MIN_EXPECTED is for time: 2 samples a second)
LAYERS = ([f"team:{t}" for t in TEAMS] + [f"{group}:{code}" for group, _, _, table in GEAR_GROUPS for code in table]
          + [f"{group}:{code}" for group, codes in EXTRA_GROUPS for code, _ in codes])
LAYER_INDEX = {key: i for i, key in enumerate(LAYERS)}
# what a request may name: both teams ("team"), one team, a layer of a group, or a payload picture
LAYER_PATTERN = r"^(team|(team|weapon|ordnance|tacmod|hand|pose|speed|death|payload):[a-z0-9]{1,16})$"
# The payload's movement, per metre of its route (payload maps only). Not player positions: no favoured view, no compare.
# "speed" first: what was asked for (user, 2026-11-10: the payload's speed; the share of time it stands still, the
# first picture made, "is meaningless to me" and is gone). Standing still and rolling back count as no progress in it,
# so a spot where pushes stall is slow; "moving" leaves those moments out.
PAYLOAD_LAYERS = {"payload:speed": "Speed", "payload:moving": "Speed while moving", "payload:back": "Rollback"}
PAYLOAD_MAPS = tuple(m for m in HEATMAP_LAYOUTS if m in PAYLOAD_ROUTES)
P_TIME, P_STOPPED, P_FORWARD, P_FORWARD_CM, P_BACK = range(5)  # columns of the payload counts (samples; centimetres)
PAYLOAD_MAX_STEP_M = 2.0  # between two samples (0.5 s): more is a reset or a glitch (it moves at 2.7 m/s at most)
PAYLOAD_MIN_SAMPLES = 240  # a metre of route needs two minutes of payload time over the archive to be drawn
PAYLOAD_BAND_M = 1.5  # half the width of the band drawn along the route
PAYLOAD_SMOOTH = np.array([1, 2, 3, 2, 1]) / 9
PAYLOAD_SHARES = {"payload:back": P_BACK}  # layers that are a share of the payload's time
PAYLOAD_SPEEDS = {"payload:speed": P_TIME, "payload:moving": P_FORWARD}  # metres forward per second of this time
BATCH = 500  # replays added between two saves (and two looks at the cards while it builds)
READ_CHUNK = 64  # files decoded at once
FLUSH_SAMPLES = 2_000_000  # samples gathered per map before they are counted (memory: ~70 MB at the peak)
FILE_NAME = "map-heat.npz"
RETRY_S = 600  # after an update that failed
RANGES = (0, 90, 30)  # days back from today a heat can be asked for; 0 = all time
IDLE_S = 600  # a time range's counts are let go this long after the last request for them
UPSIDE_ROLL = (64, 192)  # tracks3d roll (256 steps, 128 = upside down): from a quarter turn either way
POSE_MIN_VERSION = 3  # of tracks3d.bin: the first with the roll


def _shape(map_: str) -> tuple[int, int]:
    cols, rows = heatmaps.grid_size(HEATMAP_LAYOUTS[map_], CELL_M)
    return rows, cols


def _gear_layers(header: dict, codes_field: str, group: str) -> np.ndarray:
    """Index in a tracks file's own gear list (255 = none) -> layer number, -1 = not counted."""
    out = np.full(256, -1, dtype=np.int64)
    for i, code in enumerate(header.get(codes_field, [])[:255]):
        out[i] = LAYER_INDEX.get(f"{group}:{code}", -1)
    return out


def pose_layers(n: int, hz: int, pose: tuple[int, bytes, bytes] | None) -> np.ndarray | None:
    """Layer number (upside down / upright, -1 = not known) of each of a 2 Hz track's n samples, from the player's
    (hz, team, roll) of tracks3d.bin: the 3D sample at the same moment, when the player is present in it."""
    if pose is None:
        return None
    hz3d, team3d, roll = pose
    if not len(roll):
        return None
    j = np.clip(np.rint(np.arange(n) * (hz3d / hz)).astype(np.int64), 0, len(roll) - 1)
    r = np.frombuffer(roll, dtype=np.uint8)[j]
    upside = (r >= UPSIDE_ROLL[0]) & (r < UPSIDE_ROLL[1])
    out = np.where(upside, LAYER_INDEX["pose:upside"], LAYER_INDEX["pose:upright"]).astype(np.int64)
    out[np.frombuffer(team3d, dtype=np.uint8)[j] == 0] = -1
    return out


def death_keys(map_: str, xs: np.ndarray, zs: np.ndarray) -> np.ndarray:
    """Deaths at (xs, zs) metres as layer * cells + cell, like sample_keys; those off the picture are left out."""
    rows, cols = _shape(map_)
    col, row, _ = heatmaps.cells_of(HEATMAP_LAYOUTS[map_], xs + NUDGE_M, zs + NUDGE_M, CELL_M)
    return LAYER_INDEX["death:all"] * (rows * cols) + row * cols + col


_SPEED_LAYERS = np.array([LAYER_INDEX[f"speed:{code}"] for _, code, _ in heatmaps.SPEED_BANDS] + [-1])  # [-1] = none


def sample_keys(map_: str, header: dict, players: dict, hands: dict[str, int] | None = None,
                poses: dict[str, tuple[int, bytes, bytes]] | None = None) -> np.ndarray:
    """Every sample of one match as layer * cells + cell, once per layer it belongs to (its team, the three pieces
    of gear held, its speed band, the player's hand when `hands` knows it: user id -> layer, and upside down or
    upright from the track's own flags or, without them, when `poses` has the player: user id -> (hz, team, roll) of
    the 3D tracks)."""
    layout = HEATMAP_LAYOUTS[map_]
    rows, cols = _shape(map_)
    lookups = [(field, _gear_layers(header, codes_field, group)) for group, field, codes_field, _ in GEAR_GROUPS]
    keys = []
    for uid, t in players.items():
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
        layers.append(_SPEED_LAYERS[heatmaps._sample_keys(t, "speed", header.get("hz", tracks.HZ))[where]])
        if hands and uid in hands:
            layers.append(np.full(len(where), hands[uid], dtype=np.int64))
        if len(t.get("flags", b"")) == len(team):  # recorded with the track: exact
            upside = np.frombuffer(t["flags"], dtype=np.uint8)[where] & tracks.UPSIDE_DOWN
            layers.append(np.where(upside != 0, LAYER_INDEX["pose:upside"], LAYER_INDEX["pose:upright"]))
        else:
            pose = pose_layers(len(team), header.get("hz", tracks.HZ), poses.get(uid)) if poses else None
            if pose is not None:
                layers.append(pose[where])
        for layer in layers:
            known = layer >= 0
            keys.append(layer[known] * (rows * cols) + cell[known])
    return np.concatenate(keys) if keys else np.zeros(0, dtype=np.int64)


def payload_counts(map_: str, header: dict) -> np.ndarray | None:
    """One match's payload movement per metre of the route: rows = metres, columns P_TIME ... P_BACK. Only between
    the payload's first and last move: before the round starts and after it ends it stands at one spot for minutes,
    which says nothing about the push. None: not a payload map, or it never moved."""
    route = PAYLOAD_ROUTES.get(map_)
    series = header.get("series", {}).get("payload_distance")
    if not route or not series:
        return None
    d = np.array([np.nan if v is None else v for v in series], dtype=np.float64)
    step = np.diff(d)
    moved = np.flatnonzero(np.nan_to_num(step) != 0)
    if not len(moved):
        return None
    at, step = d[moved[0]:moved[-1] + 1], step[moved[0]:moved[-1] + 1]
    ok = ~np.isnan(step) & (np.abs(step) <= PAYLOAD_MAX_STEP_M)
    at, step = at[ok], step[ok]
    metre = np.clip(at.astype(np.int64), 0, len(route) - 1)
    out = np.zeros((len(route), 5), dtype=np.int64)
    for column, which, weight in ((P_TIME, slice(None), None), (P_STOPPED, step == 0, None), (P_FORWARD, step > 0, None),
                                  (P_FORWARD_CM, step > 0, np.rint(step * 100)), (P_BACK, step < 0, None)):
        w = None if weight is None else weight[which]
        out[:, column] = np.rint(np.bincount(metre[which], weights=w, minlength=len(route))).astype(np.int64)
    return out


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
# spawn rooms would otherwise set the scale and leave the rest faint). 0.99 since 2026-11-10 (was 0.999): with 0.3 m
# cells the 99.9 % cell is a spot somebody stood parked on, 30 to 280 times a usual cell, and the maps looked faded
# (user; Combustion's usual cell was drawn at 9 % strength).
PEAK_QUANTILE = 0.99
# Teams (reviewed 2026-11-10: the first version was a grey wash over the whole map). The floor everybody drifts over
# stays clear (below TEAM_FLOOR), a cell takes the colour of the team that is there most (the share is stretched by
# TEAM_CONTRAST, so only a really even cell is neutral), and the busiest cells turn towards white.
TEAM_RGB = {"blue": (0x38, 0xB6, 0xFF), "orange": (0xFF, 0x8A, 0x1E)}
TEAM_FLOOR, TEAM_GAMMA, TEAM_MAX_ALPHA = 0.08, 0.7, 0.95  # gamma 0.7 (was 0.85): the quieter routes show
TEAM_CONTRAST, TEAM_WHITE = 2.2, 0.4  # white 0.4 (was 0.55): more cells reach the top now, they keep their team colour
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
# Blur: one cell (0.3 m) each way since 2026-11-10 (user: gear as fine as the teams). It was about a metre, which drew
# every favoured spot as a round blob three to four metres across whatever the cell size.
FAVOURED_BLUR = 1  # cells
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


def render_gear(total: np.ndarray, blur: int = 0) -> bytes | None:
    """The same for one piece of gear: everywhere it was held ("all" view). `blur`: smoothed first (SPARSE_GROUPS)."""
    if blur and total.any():
        total = _blur(total, blur)
        total = np.where(total >= total.max() * 0.01, total, 0)  # without the smoothing's faint skirt
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


def render_favoured(gear: np.ndarray, group: np.ndarray, blur: int = FAVOURED_BLUR,
                    min_expected: float = FAVOURED_MIN_EXPECTED, info: dict | None = None) -> bytes | None:
    """One piece of gear against all gear of its group (same map): bright where it is held more often than on the
    map as a whole ("favoured" view). None when there is too little of it to say. `blur`, `min_expected`: for layers
    of events instead of time (SPARSE_GROUPS)."""
    gear, group = gear.astype(np.float64), group.astype(np.float64)
    if gear.sum() <= 0:
        return None
    cap = float(np.quantile(group[group > 0], FAVOURED_CAP_QUANTILE))
    # ... nor for more than FAVOURED_SPIKE times its surroundings: a lone parked player beside the map, where nobody
    # else ever is, would still stand out after the cap above
    around = _blur(np.minimum(group, cap), blur)
    weight = np.minimum(1.0, np.minimum(cap, FAVOURED_SPIKE * around) / np.maximum(group, 1.0))
    held, everyone = _blur(gear * weight, blur), _blur(group * weight, blur)
    usual = held.sum() / everyone.sum()
    enough = everyone * usual >= min_expected
    lift = np.divide(held, everyone * usual, out=np.zeros(held.shape), where=enough)
    favoured = lift >= FAVOURED_FROM
    if not favoured.any():
        return None
    top = float(np.clip(np.quantile(lift[favoured], FAVOURED_QUANTILE), *FAVOURED_TOP))
    if info is not None:
        info["top"] = round(top, 3)  # times as often as usual at the last palette entry (the read-out, READ)
    strength = np.clip((lift - FAVOURED_FROM) / (top - FAVOURED_FROM), 0, 1)
    index = np.where(favoured, 1 + np.rint(strength * (GEAR_STEPS - 1)), 0)
    return heatmaps.png_indexed(index.astype(np.uint8), FAVOURED_PALETTE)


# "compare": one layer against another (user, 2026-11-10). Each is taken as a share of its own total, so a layer with
# a tenth of the samples compares fairly; a cell is drawn in the colour of the one that is relatively more often
# there, from COMPARE_FROM (1.2 times as often) up to the picture's own COMPARE_QUANTILE cell, kept within COMPARE_TOP.
# A cell needs COMPARE_MIN_EXPECTED samples of the smaller layer's size expected in it, and no cell counts for more
# than its layer's FAVOURED_CAP_QUANTILE cell (a parked player).
COMPARE_RGB = ((0xFF, 0x4F, 0xA3), (0x2F, 0xD6, 0x9B))  # the chosen layer: pink; the one it is compared with: green
COMPARE_FROM = 0.045  # share of the two - 0.5: 0.545 = 1.2 times as often
COMPARE_QUANTILE = 0.995
COMPARE_TOP = (0.12, 0.35)  # 1.6 to 5.7 times as often
COMPARE_ALPHA = (0.30, 0.95)
COMPARE_STEPS = 127
COMPARE_MIN_EXPECTED = FAVOURED_MIN_EXPECTED


def _compare_palette() -> np.ndarray:
    palette = np.zeros((1 + 2 * COMPARE_STEPS, 4))
    level = np.arange(COMPARE_STEPS) / (COMPARE_STEPS - 1)
    for side, rgb in enumerate(COMPARE_RGB):
        rows = slice(1 + side * COMPARE_STEPS, 1 + (side + 1) * COMPARE_STEPS)
        white = 0.45 * level ** 3  # the strongest cells turn pale
        for ch in range(3):
            palette[rows, ch] = rgb[ch] * (0.75 + 0.25 * level) * (1 - white) + 255 * white
        palette[rows, 3] = (COMPARE_ALPHA[0] + (COMPARE_ALPHA[1] - COMPARE_ALPHA[0]) * level) * 255
    return np.rint(palette).astype(np.uint8)


COMPARE_PALETTE = _compare_palette()


def render_compare(one: np.ndarray, other: np.ndarray, blur: int = FAVOURED_BLUR,
                   min_expected: float = COMPARE_MIN_EXPECTED, info: dict | None = None) -> bytes | None:
    """Where `one` is relatively more often than `other` (first colour) and the other way round (second colour).
    None when either is empty or they differ nowhere."""
    grids = []
    for grid in (one.astype(np.float64), other.astype(np.float64)):
        if grid.sum() <= 0:
            return None
        grids.append(_blur(np.minimum(grid, np.quantile(grid[grid > 0], FAVOURED_CAP_QUANTILE)), blur))
    a, b = grids
    smaller = min(a.sum(), b.sum())
    pa, pb = a / a.sum(), b / b.sum()
    both = pa + pb
    enough = both * smaller / 2 >= min_expected
    lean = np.divide(pa, both, out=np.full(both.shape, 0.5), where=enough) - 0.5
    apart = np.abs(lean) >= COMPARE_FROM
    if not apart.any():
        return None
    top = float(np.clip(np.quantile(np.abs(lean[apart]), COMPARE_QUANTILE), *COMPARE_TOP))
    if info is not None:
        info["top"] = round(top, 3)
    strength = np.clip((np.abs(lean) - COMPARE_FROM) / (top - COMPARE_FROM), 0, 1)
    index = 1 + np.where(lean < 0, COMPARE_STEPS, 0) + np.rint(strength * (COMPARE_STEPS - 1))
    return heatmaps.png_indexed(np.where(apart, index, 0).astype(np.uint8), COMPARE_PALETTE)


def payload_values(counts: np.ndarray, layer: str, hz: int = tracks.HZ) -> np.ndarray:
    """Per metre of the route: the payload's average speed there in m/s ("payload:speed": metres forward per second
    it was there, standing still and rolling back included as no progress; "payload:moving": only while it went
    forward), or the share of its time it rolled back ("payload:back"); NaN where the archive has too little to say."""
    # over five metres, the middle one counting most: single metres are noisy and would draw the band as beads
    counts = np.stack([np.convolve(column, PAYLOAD_SMOOTH, mode="same") for column in counts.astype(np.float64).T], axis=1)
    if layer in PAYLOAD_SHARES:
        value, basis = counts[:, PAYLOAD_SHARES[layer]] / np.maximum(counts[:, P_TIME], 1), counts[:, P_TIME]
    else:
        basis = counts[:, PAYLOAD_SPEEDS[layer]]
        value = counts[:, P_FORWARD_CM] / 100 * hz / np.maximum(basis, 1)
    return np.where(basis >= PAYLOAD_MIN_SAMPLES, value, np.nan)


def payload_average(counts: np.ndarray, layer: str, hz: int = tracks.HZ) -> float | None:
    """The same value over the whole route of one map (None: no payload time)."""
    total = counts.sum(axis=0).astype(np.float64)
    if layer in PAYLOAD_SHARES:
        return float(total[PAYLOAD_SHARES[layer]] / total[P_TIME]) if total[P_TIME] else None
    basis = total[PAYLOAD_SPEEDS[layer]]
    return float(total[P_FORWARD_CM] / 100 * hz / basis) if basis else None


def payload_scale(values: list[np.ndarray]) -> tuple[float, float] | None:
    """The values the ramp starts and ends at: the 5 % and 95 % metre over all payload maps together, so two maps
    compare; None when there is nothing to draw."""
    known = np.concatenate([v[~np.isnan(v)] for v in values]) if values else np.zeros(0)
    if not len(known):
        return None
    low, high = (float(q) for q in np.quantile(known, (0.05, 0.95)))
    return (low, high) if high > low else (low, low + 1e-6)


def render_payload(map_: str, values: np.ndarray, scale: tuple[float, float]) -> bytes | None:
    """A band along the payload's route in the gear ramp: dark = low, pale = high. None when no metre has a value."""
    known = ~np.isnan(values)
    if not known.any():
        return None
    route = np.array(PAYLOAD_ROUTES[map_], dtype=np.float64)
    fine = np.arange(0, len(route) - 1 + 1e-9, CELL_M / 2)  # a point every half cell along the route
    x, z = np.interp(fine, np.arange(len(route)), route[:, 0]), np.interp(fine, np.arange(len(route)), route[:, 1])
    nearest = np.clip(np.rint(fine).astype(np.int64), 0, len(route) - 1)
    value = np.interp(fine, np.flatnonzero(known), values[known])  # between two metres: in between
    level = np.clip((value - scale[0]) / (scale[1] - scale[0]), 0, 1)
    entry = np.where(known[nearest], 1 + np.rint(level * (GEAR_STEPS - 1)), 0).astype(np.uint8)
    rows, cols = _shape(map_)
    col, row, inside = heatmaps.cells_of(HEATMAP_LAYOUTS[map_], x, z, CELL_M)
    entry = entry[inside]
    index = np.zeros((rows, cols), dtype=np.uint8)
    reach = round(PAYLOAD_BAND_M / CELL_M)
    for dr in range(-reach, reach + 1):
        for dc in range(-reach, reach + 1):
            if dr * dr + dc * dc <= reach * reach:
                r, c = row + dr, col + dc
                ok = (r >= 0) & (r < rows) & (c >= 0) & (c < cols) & (entry > 0)
                index[r[ok], c[ok]] = entry[ok]
    return heatmaps.png_indexed(index, PAYLOAD_PALETTE) if index.any() else None


PAYLOAD_PALETTE = _gear_palette((0.9, 1.0))  # a band on the dimmed minimap: solid


# What a palette entry of each picture means, for the page's read-out under the pointer (it reads the PNG's entries):
# favoured: entry 1 .. steps = `from` .. the map's `top` times as often as usual; compare: 1 .. steps = the chosen
# layer, steps + 1 .. 2 * steps = the other one, each `from` .. `top` as (its share of the two) - 0.5; all: the square
# root of the count against the busiest cells; payload: `scale` min .. max; teams: 1 + share step * alpha_steps +
# strength step, the share of orange stretched by `contrast` around a half.
READ = {
    "favoured": {"steps": GEAR_STEPS, "from": FAVOURED_FROM},
    "compare": {"steps": COMPARE_STEPS, "from": COMPARE_FROM},
    "all": {"steps": GEAR_STEPS},
    "payload": {"steps": GEAR_STEPS},
    "teams": {"share_steps": SHARE_STEPS, "alpha_steps": ALPHA_STEPS, "contrast": TEAM_CONTRAST},
}


class _Settings:
    """What a MapHeat needs of the app's settings (for the one _recount makes)."""

    def __init__(self, processed_dir: Path, data_dir: Path, cache_refresh_s: float):
        self.processed_dir, self.data_dir, self.cache_refresh_s = processed_dir, data_dir, cache_refresh_s


class MapHeat:
    """The counts in memory (~85 MB), their file, and the background update. One per app."""

    def __init__(self, sessions, settings, days: int = 0):
        self.sessions = sessions
        self.days = days  # 0 = all time; else only the matches started in the last `days` days
        self.used_at = time.monotonic()
        self.processed_dir: Path = settings.processed_dir
        name = FILE_NAME if not days else FILE_NAME.replace(".npz", f"-{days}d.npz")
        self.path: Path = settings.data_dir / "database" / name
        self.refresh_s: float = settings.cache_refresh_s
        self.lock = threading.Lock()  # counts, included, revision, updated_on
        self.updating = threading.Lock()  # one update at a time
        self.counts: dict[str, np.ndarray] = {}  # map -> layers x rows x cols
        self.included: dict[int, str] = {}  # replay id -> map it was added to
        self.posed: set[int] = set()  # of those, the replays whose 3D tracks gave poses (upside down / upright)
        self.payload: dict[str, np.ndarray] = {}  # payload map -> metres of route x 5 (payload_counts)
        self.revision = 0  # changes whenever the counts do: part of the cache key of the answer
        self.building = False
        self.updated_on: str | None = None  # day the last complete update finished (ISO); None = never finished
        self.tried_at = 0.0
        self.loaded = False
        self.fresh: bool | None = None  # True: this is the second file of a recount (_recount)

    # -- file ---------------------------------------------------------------------------------------------------

    def _empty(self) -> None:
        self.counts = {m: np.zeros((len(LAYERS), *_shape(m)), dtype=np.uint32) for m in HEATMAP_LAYOUTS}
        self.payload = {m: np.zeros((len(PAYLOAD_ROUTES[m]), 5), dtype=np.int64) for m in PAYLOAD_MAPS}
        self.included = {}
        self.posed = set()
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
                payload = {m: saved[f"payload_{m}"] for m in self.payload}
                if any(payload[m].shape != self.payload[m].shape for m in payload):
                    return  # a route was measured again
                maps = [str(m) for m in saved["maps"]]
                self.included = {int(r): maps[int(i)] for r, i in zip(saved["replay_ids"], saved["replay_maps"])}
                self.counts = {m: c.astype(np.uint32) for m, c in counts.items()}
                self.payload = {m: c.astype(np.int64) for m, c in payload.items()}
                self.posed = {int(r) for r in saved["pose_ids"]}
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
            pose_ids=np.fromiter(self.posed, dtype=np.int64, count=len(self.posed)),
            **{f"payload_{m}": c for m, c in self.payload.items()},
            **{f"counts_{m}": c for m, c in self.counts.items()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(buffer.getvalue())
        os.replace(tmp, self.path)

    # -- update -------------------------------------------------------------------------------------------------

    def _wanted(self) -> dict[int, str]:
        query = select(Match.replay_id, Match.map).where(counted(Match.id), Match.map.in_(HEATMAP_LAYOUTS))
        if self.days:  # started_at is ISO text: compares as text
            query = query.where(Match.started_at >= (date.today() - timedelta(days=self.days)).isoformat())
        with self.sessions() as db:
            return {replay_id: map_ for replay_id, map_ in db.execute(query)}

    def update(self) -> None:
        """Bring the counts up to date with the archive. All time, once a complete count exists: count everything
        again beside it (recount) and take that. Otherwise (the first count, a time range) in place: new replays
        added, those that no longer count taken out."""
        with self.updating:
            if not self.loaded:
                with self.lock:
                    self._load()
            if not self.days and self.updated_on is not None and self.fresh is None:
                self._recount()
                return
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

    def _recount(self) -> None:
        """Count all time from nothing in a MapHeat of its own (its file: map-heat.next.npz, saved after every batch,
        so a restart carries on), then take its counts. Visitors see the old counts meanwhile; `building` is not set,
        nothing they see is half done. Twice the memory while it runs (minutes, once a month)."""
        fresh = MapHeat(self.sessions, _Settings(self.processed_dir, self.path.parent.parent, self.refresh_s))
        fresh.path = self.path.with_name(self.path.stem + ".next.npz")
        fresh.fresh = True  # counts in place: it is the second file
        fresh.update()
        with self.lock:
            self.counts, self.payload, self.included, self.posed = fresh.counts, fresh.payload, fresh.included, fresh.posed
            self.updated_on = fresh.updated_on
            self.revision += 1
            self._save()
        fresh.path.unlink(missing_ok=True)

    def _deaths(self, replay_ids: list[int]) -> dict[int, tuple[np.ndarray, np.ndarray]]:
        """replay id -> (x, z) in metres of its estimated deaths."""
        spots: dict[int, list[tuple[float, float]]] = {}
        with self.sessions() as db:
            for start in range(0, len(replay_ids), 500):
                ids = replay_ids[start:start + 500]
                rows = db.execute(select(Match.replay_id, Event.data).join(Event, Event.match_id == Match.id)
                                  .where(Match.replay_id.in_(ids), Event.type == "death_est"))
                for replay_id, data in rows:
                    try:
                        spot = json.loads(data)
                        spots.setdefault(replay_id, []).append((float(spot["x"]), float(spot["z"])))
                    except (TypeError, ValueError, KeyError):
                        continue
        return {r: (np.array([x for x, _ in s]), np.array([z for _, z in s])) for r, s in spots.items()}

    def _hands(self, replay_ids: list[int]) -> dict[int, dict[str, int]]:
        """replay id -> {user id: hand layer} for the players whose arm setting is known (the arm used most in the
        match: it is a setting, so nearly always all of it)."""
        left, right = LAYER_INDEX["hand:left"], LAYER_INDEX["hand:right"]
        out: dict[int, dict[str, int]] = {}
        with self.sessions() as db:
            for start in range(0, len(replay_ids), 500):
                rows = db.execute(
                    select(Match.replay_id, Player.user_id, MatchPlayer.frames_left_arm, MatchPlayer.frames_right_arm)
                    .join(MatchPlayer, MatchPlayer.match_id == Match.id).join(Player, Player.id == MatchPlayer.player_id)
                    .where(Match.replay_id.in_(replay_ids[start:start + 500])))
                for replay_id, user_id, n_left, n_right in rows:
                    if n_left or n_right:
                        out.setdefault(replay_id, {})[user_id] = right if (n_right or 0) >= (n_left or 0) else left
        return out

    def _apply(self, batch: list[tuple[int, str]], sign: int) -> None:
        # read and work out the cells outside the lock (the slow part), count under it
        found: dict[str, np.ndarray] = {}
        pending: dict[str, list[np.ndarray]] = {}
        seen: list[tuple[int, str, bool, bool]] = []
        payload: dict[str, np.ndarray] = {}
        hands = self._hands([replay_id for replay_id, _ in batch])
        deaths = self._deaths([replay_id for replay_id, _ in batch])

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
                seen.append((replay_id, map_, data is not None, bool(data and (data[2] or has_flags(data[0])))))
                if data is None:
                    continue
                header, players, poses = data
                if (moved := payload_counts(map_, header)) is not None:
                    payload[map_] = payload.get(map_, 0) + moved
                pending.setdefault(map_, []).append(
                    sample_keys(map_, header, players, hands.get(replay_id), poses))
                if replay_id in deaths:
                    pending[map_].append(death_keys(map_, *deaths[replay_id]))
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
            for map_, moved in payload.items():
                self.payload[map_] = np.maximum(self.payload[map_] + sign * moved, 0)
            for replay_id, map_, readable, posed in seen:
                if sign < 0:
                    self.included.pop(replay_id, None)
                    self.posed.discard(replay_id)
                elif readable:  # no tracks yet (still importing): looked at again at the next update
                    self.included[replay_id] = map_
                    if posed:
                        self.posed.add(replay_id)
            self.revision += 1
            self._save()

    def due(self) -> bool:
        """Never finished, or last finished in an earlier month (a time range: on an earlier day)."""
        same = 10 if self.days else 7  # characters of the ISO day that must match
        return self.updated_on is None or self.updated_on[:same] != date.today().isoformat()[:same]

    def release_if_idle(self) -> None:
        """A time range nobody has asked for in IDLE_S gives its counts back (they are in its file). All time stays."""
        if not self.days or not self.loaded or time.monotonic() - self.used_at < IDLE_S:
            return
        if self.updating.acquire(blocking=False):
            try:
                with self.lock:  # really gone, not arrays of zeros: _load() makes them again
                    self.counts, self.payload, self.included, self.posed = {}, {}, {}, set()
                    self.updated_on, self.loaded = None, False
            finally:
                self.updating.release()

    def ensure(self) -> None:
        """Called with every request for the cards: load what was saved, and start the month's update when it is due.
        cache_refresh_s = 0 (the tests): update before answering."""
        self.used_at = time.monotonic()
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

    def answer(self, layer: str = TEAM_LAYER, view: str = VIEWS[0], against: str | None = None) -> dict:
        """The cards' overlays for one layer, and the layers there are (gear hardly ever held is left out; the most
        held first within its group). `view` (not for both teams): "favoured" = where it is more than usual, "all" =
        everywhere it was. `against` = another layer: the two compared (render_compare), whatever the view."""
        teams = [LAYER_INDEX[f"team:{t}"] for t in TEAMS]
        group = layer.partition(":")[0]
        in_group = [i for key, i in LAYER_INDEX.items() if key.startswith(group + ":")]
        sparse = group in SPARSE_GROUPS or (against or "").partition(":")[0] in SPARSE_GROUPS
        if group in SPARSE_GROUPS:
            in_group = teams  # against where everybody is

        def grid(counts: np.ndarray, key: str) -> np.ndarray:
            return counts[teams].sum(axis=0, dtype=np.int64) if key == TEAM_LAYER else counts[LAYER_INDEX[key]].copy()

        scale, averages = None, {}
        self.used_at = time.monotonic()
        with self.lock:
            if not self.loaded:  # a time range let go between the request's ensure() and here
                self._load()
            if layer in PAYLOAD_LAYERS:
                against = None
                values = {m: payload_values(c, layer) for m, c in self.payload.items()}
                scale = payload_scale(list(values.values()))
                picked = {m: [m, v, scale] for m, v in values.items()} if scale else {}
                averages = {m: payload_average(c, layer) for m, c in self.payload.items()}
            elif against:
                picked = {m: [grid(c, layer), grid(c, against)] for m, c in self.counts.items()}
                if sparse:
                    picked = {m: [*grids, SPARSE_BLUR, SPARSE_MIN_EXPECTED] for m, grids in picked.items()}
            elif layer == TEAM_LAYER:
                picked = {m: [c[i].copy() for i in teams] for m, c in self.counts.items()}
            elif view == "all":
                picked = {m: [c[LAYER_INDEX[layer]].copy(), SPARSE_BLUR if sparse else 0] for m, c in self.counts.items()}
            else:
                picked = {m: [c[LAYER_INDEX[layer]].copy(), c[in_group].sum(axis=0, dtype=np.int64),
                              *((SPARSE_BLUR, SPARSE_MIN_EXPECTED) if sparse else ())]
                          for m, c in self.counts.items()}
            samples = sum(c.sum(axis=(1, 2), dtype=np.int64) for c in self.counts.values()) if self.counts else []
            per_map: dict[str, int] = {}
            pose_only = group == "pose" or (against or "").startswith("pose:")  # from the matches with 3D tracks only
            for replay_id, map_ in self.included.items():
                if not pose_only or replay_id in self.posed:
                    per_map[map_] = per_map.get(map_, 0) + 1
            has_payload = any(c[:, P_TIME].any() for c in self.payload.values())
            building, updated_on = self.building, self.updated_on
        draw = (render_payload if layer in PAYLOAD_LAYERS else render_compare if against
                else render_teams if layer == TEAM_LAYER else render_gear if view == "all" else render_favoured)
        maps = {}
        tops = draw in (render_favoured, render_compare)
        for map_, grids in picked.items():
            info: dict = {}
            png = draw(*grids, info=info) if tops else draw(*grids)
            if png:
                maps[map_] = {"image": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                              "matches": per_map.get(map_, 0), **info}
                if averages.get(map_) is not None:
                    maps[map_]["average"] = round(averages[map_], 3)  # payload: the value over the whole route
        layers = [{"key": TEAM_LAYER, "group": "team", "label": "Both teams"}]
        for name, _, _, table in GEAR_GROUPS:
            held = [(int(samples[LAYER_INDEX[f"{name}:{code}"]]), code) for code in table] if len(samples) else []
            total = sum(n for n, _ in held)
            for n, code in sorted(held, key=lambda item: -item[0]):
                if n and n / total >= MIN_LAYER_SHARE:
                    layers.append({"key": f"{name}:{code}", "group": name, "code": code,
                                   "label": table[code].display_name, "cut": table[code].cut,
                                   "share": round(n / total, 4)})
        for name, codes in EXTRA_GROUPS:
            held = [int(samples[LAYER_INDEX[f"{name}:{code}"]]) for code, _ in codes] if len(samples) else []
            for (code, label), n in zip(codes, held):
                if n:
                    layers.append({"key": f"{name}:{code}", "group": name, "code": code, "label": label,
                                   **({"share": round(n / sum(held), 4)} if len(codes) > 1 else {})})
        if has_payload:
            layers += [{"key": key, "group": "payload", "code": key.partition(":")[2], "label": label}
                       for key, label in PAYLOAD_LAYERS.items()]
        shown = ("payload" if layer in PAYLOAD_LAYERS else "compare" if against
                 else "teams" if layer == TEAM_LAYER else view)
        return {"layer": layer, "view": shown, "against": against, "maps": maps, "layers": layers, "read": READ[shown],
                "scale": None if scale is None else {"min": round(scale[0], 3), "max": round(scale[1], 3)},
                "days": self.days, "matches": len(per_map) and sum(per_map.values()),
                "building": building, "updated_on": updated_on}


def _read(path: Path):
    """One tracks file and the poses of its 3D tracks (None without them), not kept in the tracks cache: an
    archive-wide pass would push out what visitors are using."""
    try:
        header, players = tracks.decode(path.read_bytes())
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - one unreadable file must not stop the pass
        log.warning("Unreadable tracks file %s left out of the all-time map heat", path)
        return None
    return header, players, None if has_flags(header) else read_poses(path.with_name("tracks3d.bin"))


def has_flags(header: dict) -> bool:
    """The tracks file says itself who is upside down: the 3D tracks are not needed (nor read)."""
    return header.get("version", 1) >= 3


def read_poses(path: Path) -> dict[str, tuple[int, bytes, bytes]] | None:
    """user id -> (hz, team, roll) of a tracks3d.bin, without decoding the rest of it (tracks3d.decode builds 13 arrays
    per player; this pass reads the whole archive). None: no file, or one from before the roll was kept."""
    try:
        raw = zlib.decompress(path.read_bytes())
        (length,) = struct.unpack_from("<I", raw)
        header = json.loads(raw[4:4 + length])
        if header.get("version", 1) < POSE_MIN_VERSION:
            return None
        # per player: x, y, z (int16) | yaw | pitch | team | six hand bytes | roll = 16 bytes a sample (tracks3d.py)
        n, at, out = header["samples"], 4 + length, {}
        for user_id in header["players"]:
            out[user_id] = (header.get("hz", 5), raw[at + 8 * n:at + 9 * n], raw[at + 15 * n:at + 16 * n])
            at += 16 * n
        return out if at <= len(raw) else None
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - the match then counts without poses
        log.warning("Unreadable 3D tracks file %s: no upside-down heat from it", path)
        return None
