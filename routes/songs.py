"""
Moodify — Song Routes
======================
Endpoints for searching and retrieving song details from the local dataset.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path

from recommender import search_songs, get_song_detail
from utils.schemas import SongResponse, SongDetailResponse, SearchResponse

router = APIRouter(prefix="/songs", tags=["Songs"])


# ─── Search Songs ─────────────────────────────────────────────
@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search songs by name",
    description="Search the local dataset for songs matching a query string.",
)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results to return"),
) -> SearchResponse:
    """
    Search songs in the local CSV by track name.
    Case-insensitive partial matching.
    """
    try:
        results = search_songs(query=q, limit=limit)
        return SearchResponse(
            query=q,
            count=len(results),
            results=results,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─── Get Single Song Details ─────────────────────────────────
@router.get(
    "/{track_name}",
    response_model=SongDetailResponse,
    summary="Get song details",
    description="Retrieve full details for a specific song. Optionally enriches with Spotify metadata.",
)
async def get_song(
    track_name: str = Path(..., description="Exact or partial track name"),
    enrich: bool = Query(True, description="Enrich with Spotify metadata"),
) -> SongDetailResponse:
    """
    Get detailed information about a single song.
    Includes audio features from the dataset and optional Spotify metadata.
    """
    try:
        song = get_song_detail(track_name=track_name, enrich=enrich)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if song is None:
        raise HTTPException(
            status_code=404,
            detail=f"Song '{track_name}' not found in the dataset",
        )

    return SongDetailResponse(**song)
