import os
import pandas as pd
import random
import logging

logger = logging.getLogger(__name__)

class FallbackService:
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.csv_path = os.getenv("DATA_PATH", os.path.join(base_dir, "data", "songs_clustered.csv"))
        try:
            self.df = pd.read_csv(self.csv_path)
        except Exception as e:
            logger.error(f"FallbackService failed to load CSV: {e}")
            self.df = None

    def get_trending_from_csv(self, n: int = 10) -> list[dict]:
        if self.df is None or self.df.empty:
            return []
            
        try:
            top_df = self.df.sort_values(by='popularity', ascending=False).head(n)
            return top_df.to_dict('records')
        except Exception:
            return []

    def get_random_from_cluster(self, cluster: int, n: int = 10) -> list[dict]:
        if self.df is None or self.df.empty:
            return []
            
        try:
            cluster_df = self.df[self.df['cluster'] == cluster]
            if cluster_df.empty:
                cluster_df = self.df
                
            sample_size = min(n, len(cluster_df))
            sampled = cluster_df.sample(n=sample_size)
            return sampled.to_dict('records')
        except Exception:
            return []
