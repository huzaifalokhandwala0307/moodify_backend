import time

class RecommendationCache:
    _cache: dict = {}
    TTL: int = 300  # 5 minutes

    def get(self, key: str) -> list | dict | None:
        self.clear_expired()
        if key in self.__class__._cache:
            entry = self.__class__._cache[key]
            if time.time() < entry['expires_at']:
                return entry['value']
            else:
                del self.__class__._cache[key]
        return None

    def set(self, key: str, value: any) -> None:
        self.__class__._cache[key] = {
            'value': value,
            'expires_at': time.time() + self.__class__.TTL
        }

    def make_key(self, mode: str, params: str) -> str:
        return f"{mode}:{params}"

    def clear_expired(self) -> None:
        now = time.time()
        expired_keys = [k for k, v in self.__class__._cache.items() if now >= v['expires_at']]
        for k in expired_keys:
            del self.__class__._cache[k]
