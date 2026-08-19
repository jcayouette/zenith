from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/dew", tags=["dew"])


class DewPatch(BaseModel):
    mode: str | None = Field(default=None)
    interval_min: int | None = Field(default=None, ge=1, le=60)
    rh_on: float | None = None
    spread_c: float | None = None


@router.get("")
def dew_status(request: Request):
    return request.app.state.dew.snapshot()


@router.post("")
async def dew_apply(request: Request, patch: DewPatch):
    data = patch.model_dump(exclude_none=True)
    return await request.app.state.dew.apply(data)
