import os
import logging

logger = logging.getLogger(__name__)

class SpotifyService:
    def __init__(self):
        self._spotify_client = None
        self._initialized = False

    def _init_spotify(self):
        if self._initialized:
            return self._spotify_client
            
        self._initialized = True
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            return None

        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials
            auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
            self._spotify_client = spotipy.Spotify(auth_manager=auth_manager)
        except Exception as exc:
            logger.warning(f"Spotify client initialization failed: {exc}")
            self._spotify_client = None
            
        return self._spotify_client

    def enrich_song(self, track_name: str, artist: str = None) -> dict:
        result = {"album_art": None, "preview_url": None, "spotify_url": None}
        try:
            sp = self._init_spotify()
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
        except Exception as e:
            logger.warning(f"Spotify enrich failed for {track_name}: {e}")
            
        return result

    def enrich_batch(self, songs: list[dict], max_enrich: int = 5) -> list[dict]:
        enriched = []
        for i, song in enumerate(songs):
            if i < max_enrich:
                meta = self.enrich_song(song.get("track_name", ""), song.get("artist"))
                song.update(meta)
            else:
                song.setdefault("album_art", None)
                song.setdefault("preview_url", None)
                song.setdefault("spotify_url", None)
            enriched.append(song)
        return enriched
