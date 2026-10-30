"""File-download responses for exports (CSV / JSON), and json_response for large API answers. Built in memory:
exports are small."""

import csv
import io
import json

import orjson
from fastapi.responses import Response


def _headers(filename: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def download_csv(rows: list[dict], columns: list[str], name: str) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    # BOM so Excel opens UTF-8 player names correctly
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers=_headers(f"{name}.csv"))


def download_json(data, name: str) -> Response:
    return Response(json.dumps(data, indent=2, ensure_ascii=False), media_type="application/json",
                    headers=_headers(f"{name}.json"))


def json_response(data) -> Response:
    """Plain JSON data (dict / list / str / number) as a response, skipping FastAPI's jsonable_encoder: for answers
    with 100k+ values (heatmaps, playback) that walk takes longer than computing them."""
    return Response(orjson.dumps(data), media_type="application/json")
