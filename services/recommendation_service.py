import os
import pandas as pd
import numpy as np
from typing import Any, Optional
from fastapi import HTTPException
import joblib
from sklearn.metrics.pairwise import cosine_similarity

from utils.schemas import RecommendResult, SongResponse
from services.personalization_service import PersonalizationService
from services.spotify_service import SpotifyService
from services.fallback_service import FallbackService
from cache.recommendation_cache import RecommendationCache

features_list = [
    'danceability', 'energy', 'valence', 'tempo',
    'acousticness', 'instrumentalness',
    'liveness', 'speechiness', 'loudness'
]

class RecommendationService:
    def __init__(self):
        self.personalization = PersonalizationService()
        self.spotify = SpotifyService()
        self.fallback = FallbackService()
        self.cache = RecommendationCache()
        
        # Load local model and CSV
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.model_path = os.getenv("MODEL_PATH", os.path.join(base_dir, "model", "kmeans_model.pkl"))
        self.csv_path = os.getenv("DATA_PATH", os.path.join(base_dir, "data", "songs_clustered.csv"))
        
        try:
            self.model = joblib.load(self.model_path)
        except Exception as e:
            self.model = None
            
        try:
            self.df = pd.read_csv(self.csv_path)
            # Ensure features exist
            self.df = self.df.dropna(subset=features_list)
        except Exception as e:
            self.df = None

    def _row_to_song_response(self, row: dict, score: float = None, reason: str = None, p_score: float = None) -> SongResponse:
        return SongResponse(
            track_name=str(row.get("track_name", "")),
            artist=str(row.get("artist_name", "")) if pd.notna(row.get("artist_name")) else None,
            album=str(row.get("album", "")) if pd.notna(row.get("album")) else None,
            cluster=int(row.get("cluster", -1)),
            similarity=None,
            score=round(float(score), 4) if score is not None else None,
            popularity=round(float(row.get("popularity", 0)), 2) if pd.notna(row.get("popularity")) else None,
            album_art=row.get("album_art") if pd.notna(row.get("album_art")) else None,
            preview_url=row.get("preview_url") if pd.notna(row.get("preview_url")) else None,
            spotify_url=row.get("spotify_url") if pd.notna(row.get("spotify_url")) else None,
            personalization_score=round(float(p_score), 4) if p_score is not None else None,
            recommendation_reason=reason
        )

    def _enrich_and_format(self, results: list[dict], result_type: str, query: str, cluster: int = None, dominant_clusters: list[int] = None) -> RecommendResult:
        # Try to enrich top 5 with Spotify
        try:
            results = self.spotify.enrich_batch(results, max_enrich=5)
        except Exception:
            pass
            
        song_responses = []
        for r in results:
            song_responses.append(self._row_to_song_response(r, score=r.get("score"), reason=r.get("reason"), p_score=r.get("p_score")))
            
        return RecommendResult(
            type=result_type,
            query=query,
            cluster=cluster,
            dominant_clusters=dominant_clusters or [],
            total=len(song_responses),
            results=song_responses
        )

    async def recommend_by_song(self, song_name: str, n: int = 10, user_id: Optional[str] = None) -> RecommendResult:
        if self.model is None or self.df is None:
            raise HTTPException(status_code=500, detail="Core recommendation files (model/csv) missing.")
            
        cache_key = self.cache.make_key("song", f"{song_name}:{n}")
        if not user_id:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
                
        # 1. Find song in local CSV (case-insensitive contains)
        matches = self.df[self.df['track_name'].str.contains(song_name, case=False, na=False)]
        # 2. If not found -> raise 404
        if matches.empty:
            raise HTTPException(status_code=404, detail=f"Song '{song_name}' not found in local dataset.")
            
        target_song = matches.iloc[0]
        # 3. Get song cluster
        target_cluster = int(target_song['cluster'])
        target_features = target_song[features_list].values.astype(float).reshape(1, -1)
        
        dominant_clusters = []
        cluster_weights = {}
        result_type = "ml_local"
        
        # 4. Try personalization
        if user_id:
            try:
                cluster_weights = await self.personalization.get_user_cluster_weights(user_id)
                dominant_clusters = await self.personalization.get_dominant_clusters(user_id)
                if dominant_clusters:
                    result_type = "hybrid"
            except Exception:
                pass
                
        # 5. Filter same cluster from CSV
        cluster_df = self.df[self.df['cluster'] == target_cluster].copy()
        
        if cluster_df.empty:
            return await self.get_trending(n)
            
        cluster_features = cluster_df[features_list].values.astype(float)
        
        # 6. Compute cosine similarity
        similarities = cosine_similarity(target_features, cluster_features)[0]
        popularity_values = cluster_df['popularity'].fillna(0).values.astype(float)
        
        # 7. Blend scores
        scores = similarities * 0.5 + (popularity_values / 100.0) * 0.3
        
        p_scores = np.zeros(len(cluster_df))
        if result_type == "hybrid":
            for i, c in enumerate(cluster_df['cluster']):
                w = cluster_weights.get(c, 0.0)
                p_scores[i] = w
                scores[i] += w * 0.2
                
        cluster_df['score'] = scores
        cluster_df['p_score'] = p_scores
        cluster_df['similarity'] = similarities
        cluster_df['reason'] = "Similar to " + str(target_song['track_name'])
        
        # Exclude the query song itself
        cluster_df = cluster_df[cluster_df['track_name'] != target_song['track_name']]
        
        top_df = cluster_df.sort_values(by='score', ascending=False).head(n)
        results = top_df.to_dict('records')
        
        # 8. Try Spotify enrichment (in _enrich_and_format)
        res = self._enrich_and_format(results, result_type, song_name, target_cluster, dominant_clusters)
        
        if not user_id:
            self.cache.set(cache_key, res)
            
        # 9. Return
        return res

    async def recommend_by_vibe(self, energy: float, danceability: float, valence: float, n: int = 10, user_id: Optional[str] = None) -> RecommendResult:
        if self.model is None or self.df is None:
            raise HTTPException(status_code=500, detail="Core recommendation files (model/csv) missing.")
            
        cache_key = self.cache.make_key("vibe", f"{energy}:{danceability}:{valence}:{n}")
        if not user_id:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
                
        # 1. Build vibe vector
        vibe = {
            "danceability": danceability, "energy": energy, "valence": valence,
            "tempo": 120.0, "acousticness": 0.3, "instrumentalness": 0.0,
            "liveness": 0.2, "speechiness": 0.1, "loudness": -6.0,
        }
        vibe_vector = np.array([[vibe[f] for f in features_list]], dtype=float)
        
        # 2. Predict cluster
        predicted_cluster = int(self.model.predict(vibe_vector)[0])
        
        dominant_clusters = []
        cluster_weights = {}
        result_type = "ml_local"
        
        # 3. Try personalization
        if user_id:
            try:
                cluster_weights = await self.personalization.get_user_cluster_weights(user_id)
                dominant_clusters = await self.personalization.get_dominant_clusters(user_id)
                if dominant_clusters:
                    result_type = "hybrid"
            except Exception:
                pass
                
        # 4. Filter cluster songs from LOCAL CSV
        cluster_df = self.df[self.df['cluster'] == predicted_cluster].copy()
        
        # 5. If cluster songs empty -> use TIER 3 fallback
        if cluster_df.empty:
            return await self.get_trending(n)
            
        cluster_features = cluster_df[features_list].values.astype(float)
        
        # 6. Compute cosine similarity
        similarities = cosine_similarity(vibe_vector, cluster_features)[0]
        popularity_values = cluster_df['popularity'].fillna(0).values.astype(float)
        
        # 7. Blend scores
        scores = similarities * 0.5 + (popularity_values / 100.0) * 0.3
        
        p_scores = np.zeros(len(cluster_df))
        if result_type == "hybrid":
            for i, c in enumerate(cluster_df['cluster']):
                w = cluster_weights.get(c, 0.0)
                p_scores[i] = w
                scores[i] += w * 0.2
                
        cluster_df['score'] = scores
        cluster_df['p_score'] = p_scores
        cluster_df['similarity'] = similarities
        cluster_df['reason'] = "Matches your requested vibe"
        
        top_df = cluster_df.sort_values(by='score', ascending=False).head(n)
        results = top_df.to_dict('records')
        
        query_str = f"energy={energy}, danceability={danceability}, valence={valence}"
        res = self._enrich_and_format(results, result_type, query_str, predicted_cluster, dominant_clusters)
        
        if not user_id:
            self.cache.set(cache_key, res)
            
        return res

    async def get_trending(self, n: int = 10) -> RecommendResult:
        if self.df is None:
            raise HTTPException(status_code=500, detail="Core recommendation CSV missing.")
            
        cache_key = self.cache.make_key("trending", f"{n}")
        cached = self.cache.get(cache_key)
        if cached:
            return cached
            
        # 1. Sort local CSV by popularity descending
        # 2. Return top n songs
        top_df = self.df.sort_values(by='popularity', ascending=False).head(n).copy()
        top_df['reason'] = "Trending locally"
        results = top_df.to_dict('records')
        
        # 3. Try Spotify metadata enrichment
        res = self._enrich_and_format(results, "trending", "trending", None, [])
        self.cache.set(cache_key, res)
        return res

    async def get_personalized(self, user_id: str, n: int = 10) -> RecommendResult:
        if self.df is None:
            raise HTTPException(status_code=500, detail="Core recommendation CSV missing.")
            
        try:
            has_history = await self.personalization.has_enough_history(user_id, 1)
            if not has_history:
                return await self.get_trending(n)
                
            cluster_weights = await self.personalization.get_user_cluster_weights(user_id)
            dominant_clusters = await self.personalization.get_dominant_clusters(user_id)
            
            if not dominant_clusters:
                return await self.get_trending(n)
                
            # Filter + score CSV songs
            cluster_df = self.df[self.df['cluster'].isin(dominant_clusters)].copy()
            if cluster_df.empty:
                cluster_df = self.df.copy()
                
            popularity_values = cluster_df['popularity'].fillna(0).values.astype(float)
            scores = (popularity_values / 100.0) * 0.4
            
            p_scores = np.zeros(len(cluster_df))
            for i, c in enumerate(cluster_df['cluster']):
                w = cluster_weights.get(c, 0.0)
                p_scores[i] = w
                scores[i] += w * 0.6
                
            cluster_df['score'] = scores
            cluster_df['p_score'] = p_scores
            cluster_df['reason'] = "Based on your recent listening history"
            
            # Add some randomness to top 50 before taking n
            top_df = cluster_df.sort_values(by='score', ascending=False).head(max(50, n))
            if len(top_df) > n:
                top_df = top_df.sample(n)
            
            top_df = top_df.sort_values(by='score', ascending=False)
            results = top_df.to_dict('records')
            
            return self._enrich_and_format(results, "personalized", f"user:{user_id}", None, dominant_clusters)
        except Exception:
            return await self.get_trending(n)

recommendation_service = RecommendationService()
