"""
Moodify — Health Check Route
==============================
Provides a simple health check endpoint.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from backend.recommender import get_model
from backend.database import get_db
from backend.utils.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Returns service status, model load state, song count, and timestamp.",
)
async def health_check() -> HealthResponse:
    model = get_model()
    db = get_db()

    model_loaded = model is not None
    
    songs_count = 0
    db_connected = False
    
    if db:
        try:
            res = db.table("songs").select("id", count="exact").limit(1).execute()
            songs_count = res.count if res.count else 0
            db_connected = True
        except Exception as e:
            db_connected = False

    status = "ok" if (model_loaded and db_connected) else "degraded"

    return HealthResponse(
        status=status,
        model_loaded=model_loaded,
        songs_count=songs_count,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
