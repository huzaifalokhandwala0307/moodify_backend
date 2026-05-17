import numpy as np
import logging
from database import get_db

logger = logging.getLogger(__name__)

class PersonalizationService:
    async def get_user_cluster_weights(self, user_id: str) -> dict[int, float]:
        try:
            db = get_db()
            history = db.table("listening_history").select("song:songs(cluster)").eq("user_id", user_id).execute()
            likes = db.table("liked_tracks").select("song:songs(cluster)").eq("user_id", user_id).execute()
            
            clusters = []
            if history.data:
                for h in history.data:
                    song = h.get("song")
                    if song and song.get("cluster") is not None:
                        clusters.append(song["cluster"])
            
            if likes.data:
                for l in likes.data:
                    song = l.get("song")
                    if song and song.get("cluster") is not None:
                        clusters.append(song["cluster"])
                        clusters.append(song["cluster"]) # double weight for likes
                        
            if not clusters:
                return {}
                
            counts = {}
            for c in clusters:
                counts[c] = counts.get(c, 0) + 1
                
            total = sum(counts.values())
            weights = {c: count / total for c, count in counts.items()}
            return weights
        except Exception as e:
            logger.warning(f"Failed to get user cluster weights: {e}")
            return {}

    async def get_dominant_clusters(self, user_id: str) -> list[int]:
        weights = await self.get_user_cluster_weights(user_id)
        if not weights:
            return []
        sorted_clusters = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        return [c for c, _ in sorted_clusters[:3]]

    async def get_preference_vector(self, user_id: str) -> np.ndarray | None:
        try:
            db = get_db()
            res = db.table("user_preferences").select("*").eq("user_id", user_id).limit(1).execute()
            if not res.data:
                return None
                
            prefs = res.data[0]
            features_list = [
                'danceability', 'energy', 'valence', 'tempo',
                'acousticness', 'instrumentalness',
                'liveness', 'speechiness', 'loudness'
            ]
            
            vector = []
            for f in features_list:
                val = prefs.get(f"preferred_{f}")
                if val is not None:
                    vector.append(float(val))
                else:
                    defaults = {'tempo': 120.0, 'loudness': -6.0}
                    vector.append(defaults.get(f, 0.5))
            return np.array([vector])
        except Exception as e:
            logger.warning(f"Failed to get preference vector: {e}")
            return None

    async def has_enough_history(self, user_id: str, min_songs: int = 5) -> bool:
        try:
            db = get_db()
            h_count = db.table("listening_history").select("id", count="exact").eq("user_id", user_id).execute()
            l_count = db.table("liked_tracks").select("id", count="exact").eq("user_id", user_id).execute()
            
            total = (h_count.count or 0) + (l_count.count or 0)
            return total >= min_songs
        except Exception as e:
            logger.warning(f"Failed to check history count: {e}")
            return False
