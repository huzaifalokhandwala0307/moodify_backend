"""
Moodify — Recommendation Routes
=================================
Endpoints for song-based and vibe-based music recommendations.
All ML logic uses local CSV + KMeans model only.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional

from backend.services.recommendation_service import recommendation_service
from backend.utils.schemas import RecommendResult
from backend.auth import get_current_user_id

router = APIRouter(prefix="/recommend", tags=["Recommendations"])


# ─── Recommend by Song Name ──────────────────────────────────
@router.get(
    "/song",
    response_model=RecommendResult,
    summary="Get recommendations based on a song",
    description="Find a song in the dataset, determine its cluster, then return similar songs."
)
async def recommend_song(
    song_name: str = Query(..., min_length=1, description="Name of the seed song"),
    n: int = Query(10, ge=1, le=50, description="Number of recommendations"),
    user_id: Optional[str] = Query(None, description="Optional user ID for personalization"),
) -> RecommendResult:
    result = await recommendation_service.recommend_by_song(song_name, n, user_id)
    return result

# ─── Recommend by Vibe ────────────────────────────────────────
@router.get(
    "/vibe",
    response_model=RecommendResult,
    summary="Get recommendations based on a vibe",
    description="Predict a cluster with KMeans, then return similar songs ranked by score."
)
async def recommend_vibe(
    energy: float = Query(0.5, ge=0.0, le=1.0, description="Energy level (0-1)"),
    danceability: float = Query(0.5, ge=0.0, le=1.0, description="Danceability (0-1)"),
    valence: float = Query(0.5, ge=0.0, le=1.0, description="Valence / happiness (0-1)"),
    n: int = Query(10, ge=1, le=50, description="Number of recommendations"),
    user_id: Optional[str] = Query(None, description="Optional user ID for personalization"),
) -> RecommendResult:
    result = await recommendation_service.recommend_by_vibe(energy, danceability, valence, n, user_id)
    return result

# ─── Recommend Trending ───────────────────────────────────────
@router.get(
    "/trending",
    response_model=RecommendResult,
    summary="Get trending recommendations",
)
async def recommend_trending(n: int = Query(10, ge=1, le=50)):
    result = await recommendation_service.get_trending(n)
    return result

# ─── Recommend Personalized ──────────────────────────────────
@router.get(
    "/user/{user_id}",
    response_model=RecommendResult,
    summary="Get personalized recommendations",
    description="Returns recommended songs based on the user's history and likes.",
)
async def get_personalized_recommendation(
    user_id: str,
    n: int = Query(10, ge=1, le=50, description="Number of recommendations"),
    current_user: str = Depends(get_current_user_id)
) -> RecommendResult:
    if user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to get recommendations for this user")
        
    result = await recommendation_service.get_personalized(user_id, n)
    return result
