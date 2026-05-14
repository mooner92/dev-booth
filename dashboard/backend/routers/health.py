from __future__ import annotations

from fastapi import APIRouter

from .. import config
from ..services.models import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        ok=True,
        version=config.VERSION,
        sessions_root=str(config.SESSIONS_ROOT),
    )
