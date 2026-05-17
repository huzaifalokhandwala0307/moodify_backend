import os
import sys
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv
import time
import math

# Add the parent directory to sys.path to allow importing backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.recommender import get_spotify_metadata

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "songs_clustered.csv")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY missing.")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def seed():
    if not os.path.exists(DATA_PATH):
        print(f"File not found: {DATA_PATH}")
        sys.exit(1)
        
    df = pd.read_csv(DATA_PATH)
    total = len(df)
    print(f"Loaded {total} songs. Seeding to Supabase...")
    
    failed = []
    
    # Process in chunks
    chunk_size = 50
    for i in range(0, total, chunk_size):
        chunk = df.iloc[i:i+chunk_size]
        records = []
        
        for _, row in chunk.iterrows():
            record = {
                "track_name": str(row["track_name"]),
                "artist_name": str(row["artist"]) if pd.notna(row.get("artist")) else None,
                "album": str(row["album"]) if pd.notna(row.get("album")) else None,
                "popularity": int(row["popularity"]) if pd.notna(row.get("popularity")) else 0,
                "danceability": float(row["danceability"]) if pd.notna(row.get("danceability")) else None,
                "energy": float(row["energy"]) if pd.notna(row.get("energy")) else None,
                "valence": float(row["valence"]) if pd.notna(row.get("valence")) else None,
                "tempo": float(row["tempo"]) if pd.notna(row.get("tempo")) else None,
                "acousticness": float(row["acousticness"]) if pd.notna(row.get("acousticness")) else None,
                "instrumentalness": float(row["instrumentalness"]) if pd.notna(row.get("instrumentalness")) else None,
                "liveness": float(row["liveness"]) if pd.notna(row.get("liveness")) else None,
                "speechiness": float(row["speechiness"]) if pd.notna(row.get("speechiness")) else None,
                "loudness": float(row["loudness"]) if pd.notna(row.get("loudness")) else None,
                "cluster": int(row["cluster"]) if pd.notna(row.get("cluster")) else None,
            }
            
            # Optional Spotify Metadata Enrichment
            # Note: Rate limiting will apply. To seed fast, disable this or use sleep.
            # metadata = get_spotify_metadata(record["track_name"], record["artist_name"])
            # record.update(metadata)
            
            records.append(record)
            
        try:
            # Using insert with count instead of upsert since spotify_id might be missing
            # If you enrich with spotify_id, you can use upsert on spotify_id
            supabase.table("songs").insert(records).execute()
        except Exception as e:
            print(f"Error inserting chunk {i}-{i+chunk_size}: {e}")
            failed.extend(records)
            
        print(f"Progress: {min(i+chunk_size, total)} / {total}")
        time.sleep(0.1) # Small delay to avoid hammering DB
        
    if failed:
        print(f"Failed to insert {len(failed)} rows. Saving to failed_songs.csv")
        pd.DataFrame(failed).to_csv("failed_songs.csv", index=False)
    else:
        print("Seeding completed successfully!")

if __name__ == "__main__":
    seed()
