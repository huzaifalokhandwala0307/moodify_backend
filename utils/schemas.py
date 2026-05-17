"""
Moodify — Pydantic v2 Request/Response Schemas
================================================
Defines all data models used across API endpoints.
All fields are JSON-serializable (no raw numpy types).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─── Song Response ────────────────────────────────────────────
class SongResponse(BaseModel):
    """Schema for a single song returned by any endpoint."""

    track_name: str = Field(..., description="Name of the track")
    artist: str | None = Field(None, description="Artist name")
    album: str | None = Field(None, description="Album name")
    cluster: int = Field(..., description="KMeans cluster label")
    similarity: float | None = Field(None, description="Cosine similarity score (0-1)")
    score: float | None = Field(
        None,
        description="Combined score: similarity*0.7 + popularity*0.3",
    )
    popularity: float | None = Field(None, description="Popularity (0-100)")
    album_art: str | None = Field(None, description="Spotify album art URL")
    preview_url: str | None = Field(None, description="Spotify 30s preview URL")
    spotify_url: str | None = Field(None, description="Spotify track URL")
    # NEW
    personalization_score: float | None = Field(None, description="how well it matches user taste")
    recommendation_reason: str | None = Field(None, description="reason for recommendation")


# ─── Health Response ──────────────────────────────────────────
class HealthResponse(BaseModel):
    """Schema for the /health endpoint."""

    status: str = Field(..., description="Service status")
    model_loaded: bool = Field(..., description="Whether the KMeans model is loaded")
    songs_count: int = Field(..., description="Number of songs in the dataset")
    timestamp: str = Field(..., description="ISO-8601 timestamp")


# ─── Recommendation Response ─────────────────────────────────
# CHANGED: Replaced RecommendResponse with RecommendResult
class RecommendResult(BaseModel):
    """Schema for recommendation endpoints."""

    type: str = Field(..., description="Type of recommendation (e.g., personalized, ml_local, trending, hybrid)")
    query: str = Field(..., description="The original query (song name, vibe params, or trending)")
    cluster: int | None = Field(None, description="Cluster used for recommendations")
    dominant_clusters: list[int] = Field(default_factory=list, description="For personalized recommendations")
    total: int = Field(..., description="Total number of results returned")
    results: list[SongResponse] = Field(
        default_factory=list,
        description="List of recommended songs",
    )


# ─── Song Detail Response ────────────────────────────────────
class SongDetailResponse(SongResponse):
    """Extended song response with full feature details."""

    danceability: float | None = None
    energy: float | None = None
    valence: float | None = None
    tempo: float | None = None
    acousticness: float | None = None
    instrumentalness: float | None = None
    liveness: float | None = None
    speechiness: float | None = None
    loudness: float | None = None


# ─── Search Response ──────────────────────────────────────────
class SearchResponse(BaseModel):
    """Schema for the /songs/search endpoint."""

    query: str = Field(..., description="Search query")
    count: int = Field(..., description="Number of results returned")
    results: list[SongResponse] = Field(
        default_factory=list,
        description="List of matching songs",
    )


# ─── Auth Schemas ─────────────────────────────────────────────
class UserRegister(BaseModel):
    email: str
    password: str
    display_name: str | None = None

class UserLogin(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


# ─── User Profile & Data Schemas ──────────────────────────────
class UserProfile(BaseModel):
    id: str
    display_name: str | None = None
    avatar_url: str | None = None
    created_at: str | None = None

class HistoryCreate(BaseModel):
    song_id: str

class LikeCreate(BaseModel):
    song_id: str

class SaveCreate(BaseModel):
    song_id: str

class PreferencesUpdate(BaseModel):
    preferred_energy: float | None = Field(None, ge=0.0, le=1.0)
    preferred_danceability: float | None = Field(None, ge=0.0, le=1.0)
    preferred_valence: float | None = Field(None, ge=0.0, le=1.0)
    preferred_genres: list[str] | None = None
    preferred_clusters: list[int] | None = None


# ─── Personalized Recommendation ──────────────────────────────
class PersonalizedRecommendResponse(BaseModel):
    user_id: str
    mode: str
    dominant_clusters: list[int] = Field(default_factory=list)
    results: list[SongResponse] = Field(default_factory=list)

