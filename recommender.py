"""
Moodify — ML Recommender Engine
=================================
All recommendation logic lives here.
Uses Supabase for data + pre-trained KMeans model.
Spotify is used optionally for metadata enrichment.

STRICT RULES:
  - NEVER call sp.audio_features()
  - NEVER do bulk Spotify enrichment at startup
  - sp.search() is OPTIONAL and only for metadata display
"""

from __future__ import annotations

import os
import logging
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv
from backend.database import get_db
from backend.utils.personalization import get_dominant_clusters

from pathlib import Path

# BASE_DIR = Path(__file__).resolve().parent
# DEFAULT_MODEL_PATH = BASE_DIR / "model" / "kmeans_model.pkl"
# DEFAULT_DATA_PATH = BASE_DIR / "data" / "songs_clustered.csv"

load_dotenv()

logger = logging.getLogger("moodify.recommender")

# ─── Feature Columns — use exactly these everywhere ──────────
features_list = [
    "danceability",
    "energy",
    "valence",
    "tempo",
    "acousticness",
    "instrumentalness",
    "liveness",
    "speechiness",
    "loudness",
]

# ─── Module-level state ──────────────────────────────────────
_model = None
_spotify_client = None

# ═════════════════════════════════════════════════════════════
# DATA & MODEL LOADING
# ═════════════════════════════════════════════════════════════

def load_model(path: str | None = None):
    """
    Load the pre-trained KMeans model from a pickle file.
    Returns the loaded model (sklearn Pipeline or KMeans object).
    """
    global _model
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    model_path = os.getenv("MODEL_PATH", os.path.join(BASE_DIR, "model", "kmeans_model.pkl"))
    try:
        _model = joblib.load(model_path)
        logger.info("KMeans model loaded from %s", model_path)
        return _model
    except Exception as exc:
        logger.error("Failed to load model from %s: %s", model_path, exc)
        raise RuntimeError(f"Could not load KMeans model: {exc}") from exc

def get_model():
    """Return the loaded model (or None if not loaded)."""
    return _model

# ═════════════════════════════════════════════════════════════
# OPTIONAL SPOTIFY CLIENT
# ═════════════════════════════════════════════════════════════

def _init_spotify():
    global _spotify_client
    if _spotify_client is not None:
        return _spotify_client

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        _spotify_client = spotipy.Spotify(auth_manager=auth_manager)
        return _spotify_client
    except Exception as exc:
        return None

def get_spotify_metadata(track_name: str, artist: str | None = None) -> dict[str, Any]:
    result = {"album_art": None, "preview_url": None, "spotify_url": None}
    try:
        sp = _init_spotify()
        if sp is None:
            return result
        query = f"track:{track_name}"
        if artist:
            query += f" artist:{artist}"
        search_results = sp.search(q=query, type="track", limit=1)
        tracks = search_results.get("tracks", {}).get("items", [])
        if not tracks:
            return result
        track = tracks[0]
        result["spotify_url"] = track.get("external_urls", {}).get("spotify")
        result["preview_url"] = track.get("preview_url")
        images = track.get("album", {}).get("images", [])
        if images:
            result["album_art"] = images[1]["url"] if len(images) > 1 else images[0]["url"]
    except Exception:
        pass
    return result

# ═════════════════════════════════════════════════════════════
# HELPER: Build song dict from DB row
# ═════════════════════════════════════════════════════════════

def _row_to_dict(row: dict, similarity: float | None = None, score: float | None = None) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "track_name": str(row.get("track_name", "")),
        "artist": str(row.get("artist_name")) if row.get("artist_name") else None,
        "album": str(row.get("album")) if row.get("album") else None,
        "cluster": int(row.get("cluster", -1)),
        "similarity": round(float(similarity), 4) if similarity is not None else None,
        "score": round(float(score), 4) if score is not None else None,
        "popularity": round(float(row.get("popularity", 0)), 2),
        "album_art": row.get("album_art"),
        "preview_url": row.get("preview_url"),
        "spotify_url": row.get("spotify_url"),
    }

# ═════════════════════════════════════════════════════════════
# CORE: Recommend by Song Name
# ═════════════════════════════════════════════════════════════

def recommend_by_song(song_name: str, n: int = 10, user_id: str | None = None) -> dict[str, Any]:
    db = get_db()
    
    # 1. Search Supabase for the input song
    res = db.table("songs").select("*").ilike("track_name", f"%{song_name}%").limit(1).execute()
    if not res.data:
        return {"query": song_name, "cluster": -1, "results": []}
    
    target_song = res.data[0]
    target_cluster = int(target_song["cluster"])
    
    # 2. Fetch songs in the same cluster
    cluster_res = db.table("songs").select("*").eq("cluster", target_cluster).neq("id", target_song["id"]).limit(500).execute()
    if not cluster_res.data:
        return {"query": song_name, "cluster": target_cluster, "results": []}
    
    cluster_df = pd.DataFrame(cluster_res.data)
    cluster_df = cluster_df.dropna(subset=features_list)
    
    if cluster_df.empty:
        return {"query": song_name, "cluster": target_cluster, "results": []}
        
    # User personalization (warm start)
    dominant_clusters = []
    if user_id:
        dominant_clusters = get_dominant_clusters(user_id)
        # Fetch some songs from dominant clusters too if different
        for d_cluster in dominant_clusters:
            if d_cluster != target_cluster:
                d_res = db.table("songs").select("*").eq("cluster", d_cluster).limit(100).execute()
                d_df = pd.DataFrame(d_res.data)
                d_df = d_df.dropna(subset=features_list)
                cluster_df = pd.concat([cluster_df, d_df])
                
    cluster_df = cluster_df.drop_duplicates(subset=['id'])
    
    target_features = np.array([[target_song.get(f, 0.5) for f in features_list]], dtype=float)
    cluster_features = cluster_df[features_list].values.astype(float)
    similarities = cosine_similarity(target_features, cluster_features)[0]
    
    popularity_values = cluster_df["popularity"].fillna(0).values.astype(float)
    
    # Base score
    scores = similarities * 0.7 + (popularity_values / 100.0) * 0.3
    
    # Add personalization weight
    if dominant_clusters:
        cluster_weights = np.array([0.3 if c in dominant_clusters else 0.0 for c in cluster_df["cluster"]])
        scores += cluster_weights
        
    top_indices = np.argsort(scores)[::-1][:n]
    
    results = []
    for idx in top_indices:
        row = cluster_df.iloc[idx].to_dict()
        results.append(_row_to_dict(row, similarity=similarities[idx], score=scores[idx]))
        
    return {"query": song_name, "cluster": target_cluster, "results": results}

# ═════════════════════════════════════════════════════════════
# CORE: Recommend by Vibe (Feature Vector)
# ═════════════════════════════════════════════════════════════

def recommend_by_vibe(energy: float = 0.5, danceability: float = 0.5, valence: float = 0.5, n: int = 10, user_id: str | None = None) -> dict[str, Any]:
    if _model is None:
        raise RuntimeError("KMeans model not loaded")
    
    db = get_db()
    
    vibe = {
        "danceability": danceability, "energy": energy, "valence": valence,
        "tempo": 120.0, "acousticness": 0.3, "instrumentalness": 0.0,
        "liveness": 0.2, "speechiness": 0.1, "loudness": -6.0,
    }
    vibe_vector = np.array([[vibe[f] for f in features_list]], dtype=float)
    predicted_cluster = int(_model.predict(vibe_vector)[0])
    
    cluster_res = db.table("songs").select("*").eq("cluster", predicted_cluster).limit(500).execute()
    cluster_df = pd.DataFrame(cluster_res.data)
    
    if cluster_df.empty:
        query_str = f"energy={energy}, danceability={danceability}, valence={valence}"
        return {"query": query_str, "cluster": predicted_cluster, "results": []}
        
    cluster_df = cluster_df.dropna(subset=features_list)
    
    dominant_clusters = []
    if user_id:
        dominant_clusters = get_dominant_clusters(user_id)
        for d_cluster in dominant_clusters:
            if d_cluster != predicted_cluster:
                d_res = db.table("songs").select("*").eq("cluster", d_cluster).limit(100).execute()
                d_df = pd.DataFrame(d_res.data)
                d_df = d_df.dropna(subset=features_list)
                cluster_df = pd.concat([cluster_df, d_df])
                
    cluster_df = cluster_df.drop_duplicates(subset=['id'])
    
    cluster_features = cluster_df[features_list].values.astype(float)
    similarities = cosine_similarity(vibe_vector, cluster_features)[0]
    
    popularity_values = cluster_df["popularity"].fillna(0).values.astype(float)
    scores = similarities * 0.7 + (popularity_values / 100.0) * 0.3
    
    if dominant_clusters:
        cluster_weights = np.array([0.3 if c in dominant_clusters else 0.0 for c in cluster_df["cluster"]])
        scores += cluster_weights
        
    top_indices = np.argsort(scores)[::-1][:n]
    
    query_str = f"energy={energy}, danceability={danceability}, valence={valence}"
    results = []
    for idx in top_indices:
        row = cluster_df.iloc[idx].to_dict()
        results.append(_row_to_dict(row, similarity=similarities[idx], score=scores[idx]))
        
    return {"query": query_str, "cluster": predicted_cluster, "results": results}

def recommend_personalized(user_id: str, n: int = 10) -> dict[str, Any]:
    dominant_clusters = get_dominant_clusters(user_id)
    if not dominant_clusters:
        # Cold start fallback: recommend by default vibe
        res = recommend_by_vibe(0.7, 0.7, 0.7, n=n)
        return {"mode": "cold_start", "dominant_clusters": [], "results": res["results"]}
    
    db = get_db()
    # Warm start: Get songs from top clusters, prioritize popularity
    cluster_res = db.table("songs").select("*").in_("cluster", dominant_clusters).order("popularity", desc=True).limit(200).execute()
    cluster_df = pd.DataFrame(cluster_res.data)
    
    if cluster_df.empty:
        res = recommend_by_vibe(0.7, 0.7, 0.7, n=n)
        return {"mode": "cold_start", "dominant_clusters": [], "results": res["results"]}
        
    # Get previously listened/liked songs to filter them out
    history = db.table("listening_history").select("song_id").eq("user_id", user_id).execute()
    likes = db.table("liked_tracks").select("song_id").eq("user_id", user_id).execute()
    
    seen_ids = set([h["song_id"] for h in history.data] + [l["song_id"] for l in likes.data])
    
    cluster_df = cluster_df[~cluster_df['id'].isin(seen_ids)]
    
    if cluster_df.empty:
        # If all seen, just return the most popular ones
        cluster_df = pd.DataFrame(cluster_res.data)
        
    # Take top N by popularity with a slight randomization
    top_songs = cluster_df.sample(min(n, len(cluster_df)))
    
    results = []
        
    return {"mode": "personalized", "dominant_clusters": dominant_clusters, "results": results}

# ═════════════════════════════════════════════════════════════
# SEARCH: Local CSV Search -> Now Supabase
# ═════════════════════════════════════════════════════════════

def search_songs(query: str, limit: int = 10) -> list[dict[str, Any]]:
    db = get_db()
    res = db.table("songs").select("*").ilike("track_name", f"%{query}%").limit(limit).execute()
    
    results = []
    for row in res.data:
        results.append(_row_to_dict(row))
    return results

# ═════════════════════════════════════════════════════════════
# DETAIL: Get Single Song
# ═════════════════════════════════════════════════════════════

def get_song_detail(track_name: str, enrich: bool = True) -> dict[str, Any] | None:
    db = get_db()
    res = db.table("songs").select("*").ilike("track_name", track_name).limit(1).execute()
    
    if not res.data:
        return None
        
    row = res.data[0]
    song = _row_to_dict(row)
    
    for feat in features_list:
        val = row.get(feat)
        song[feat] = round(float(val), 4) if val is not None else None
        
    if enrich:
        metadata = get_spotify_metadata(track_name=song["track_name"], artist=song.get("artist"))
        song.update(metadata)
        
    return song

