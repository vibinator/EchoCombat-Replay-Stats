"""Head positions from .echoreplay files for check.mjs (docs/WebReplayer-Review.MD, Phase 1).

    python -I sample_heads.py <replay folder> heads.json [replays per map, default 10]

Every 20th frame of each replay, all players on the two teams: {map_name: [[x, y, z], ...]}. Read-only on the replays."""
import collections
import glob
import io
import json
import os
import sys
import zipfile


def frames(path):
    data = open(path, "rb").read()
    if data[:4] == b"PK\x03\x04":  # zipped .echoreplay
        z = zipfile.ZipFile(io.BytesIO(data))
        data = z.read(z.namelist()[0])
    for i, line in enumerate(data.decode("utf-8", "replace").splitlines()):
        if i % 20 == 0 and "\t" in line:
            try:
                yield json.loads(line.split("\t", 1)[1])
            except ValueError:
                continue


def main(root, out, per_map=10):
    heads = collections.defaultdict(list)
    used = collections.Counter()
    for path in sorted(glob.glob(os.path.join(root, "**", "*.echoreplay"), recursive=True)):
        map_name = None
        for frame in frames(path):
            map_name = frame.get("map_name", map_name)
            if used[map_name] >= per_map:
                break
            for team in frame.get("teams", [])[:2]:
                for p in team.get("players", []):
                    if pos := p.get("head", {}).get("position"):
                        heads[map_name].append([round(v, 2) for v in pos])
        if map_name:
            used[map_name] += 1
    with open(out, "w") as f:
        json.dump(heads, f)
    print({k: (min(used[k], per_map), len(v)) for k, v in heads.items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10)
