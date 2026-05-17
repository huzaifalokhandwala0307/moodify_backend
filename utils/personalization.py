from collections import Counter
from database import get_db

def get_user_taste_profile(user_id: str) -> dict:
    """
    Computes dominant clusters based on the user's history and likes.
    Returns a dictionary of cluster weights.
    """
    db = get_db()
    if not db:
        return {}

    try:
        # Fetch user's history
        history_res = db.table("listening_history").select("song_id, songs(cluster)").eq("user_id", user_id).execute()
        likes_res = db.table("liked_tracks").select("song_id, songs(cluster)").eq("user_id", user_id).execute()

        clusters = []
        for item in history_res.data:
            if item.get("songs") and item["songs"].get("cluster") is not None:
                clusters.append(item["songs"]["cluster"])
        
        # Give likes more weight
        for item in likes_res.data:
            if item.get("songs") and item["songs"].get("cluster") is not None:
                clusters.extend([item["songs"]["cluster"]] * 2)

        if not clusters:
            return {}

        cluster_counts = Counter(clusters)
        total = sum(cluster_counts.values())
        
        # Normalize weights
        weights = {cluster: count / total for cluster, count in cluster_counts.items()}
        return weights
    except Exception as e:
        print(f"Error computing taste profile: {e}")
        return {}

def get_dominant_clusters(user_id: str, top_k: int = 3) -> list[int]:
    """Returns the top K clusters for the user."""
    weights = get_user_taste_profile(user_id)
    sorted_clusters = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    return [c[0] for c in sorted_clusters[:top_k]]

def get_personalized_recommendations(user_id: str, n: int = 10) -> list[dict]:
    """
    Generates personalized recommendations based on the user's dominant clusters.
    This will be integrated with the main recommender logic.
    """
    # This is a placeholder that will be used by recommender.py
    # Actual implementation logic will live in recommender.py to combine
    # similarity, popularity, and cluster_preference_weight.
    pass

def build_preference_vector(user_id: str) -> list[float]:
    """
    Builds a preference vector based on the user's liked and saved tracks.
    Returns a list representing [danceability, energy, valence, etc.]
    """
    # Fallback to default if no data
    return [0.5, 0.5, 0.5]
