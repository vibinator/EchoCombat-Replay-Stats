"""Replays found in the share (D25). Read-only: files are added by the scanner; reprocess / repair are in the
admin console."""

import json

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..admin_actions import hidden_failure
from ..models import Match, RepairRequest, Replay

router = APIRouter(prefix="/api/replays", tags=["replays"])


class ReplayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_path: str
    size_bytes: int
    source_mtime: float
    discovered_at: str
    container: str | None
    status: str
    error_code: str | None
    error_message: str | None
    warnings: list[str]
    parser_version: str | None
    stats_version: str | None
    processed_at: str | None
    match_id: int | None = None
    repair_requested: bool = False

    @field_validator("warnings", mode="before")
    @classmethod
    def _parse_warnings(cls, v):
        return json.loads(v) if isinstance(v, str) else (v or [])


class ReplayPage(BaseModel):
    items: list[ReplayOut]
    total: int


def _get(db: Session, replay_id: int) -> Replay:
    replay = db.get(Replay, replay_id)
    if replay is None:
        raise ApiError(404, "not_found", f"Replay {replay_id} not found")
    return replay


def _with_match_ids(db: Session, query) -> list[ReplayOut]:
    rows = db.execute(query.add_columns(Match.id).outerjoin(Match, Match.replay_id == Replay.id)).all()
    repair = set(db.scalars(select(RepairRequest.source_path)))
    return [ReplayOut.model_validate(r).model_copy(update={"match_id": match_id, "repair_requested": r.source_path in repair})
            for r, match_id in rows]


@router.get("", response_model=ReplayPage)
def list_replays(
    request: Request,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(Replay).where(not_(hidden_failure()))
    if status:
        query = query.where(Replay.status == status)
    with request.app.state.sessionmaker() as db:
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        items = _with_match_ids(db, query.order_by(Replay.source_mtime.desc()).limit(limit).offset(offset))
    return ReplayPage(items=items, total=total)


@router.get("/{replay_id}", response_model=ReplayOut)
def get_replay(request: Request, replay_id: int):
    with request.app.state.sessionmaker() as db:
        _get(db, replay_id)
        return _with_match_ids(db, select(Replay).where(Replay.id == replay_id))[0]
