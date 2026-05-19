import os
import time
import json
import uuid
import urllib.request
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()

# ─── Firebase Certificate Verification Configuration ───────────
GOOGLE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"

# Keep an in-memory cache of Google's public certificates to prevent slow network requests
_certs_cache = {}
_certs_expire_at = 0

def get_google_public_keys():
    """
    Fetches and caches Google's public x509 certificates used to sign Firebase ID tokens.
    """
    global _certs_cache, _certs_expire_at
    now = time.time()
    
    if not _certs_cache or now >= _certs_expire_at:
        try:
            # Send HTTP request using built-in urllib to keep dependencies lightweight
            with urllib.request.urlopen(GOOGLE_CERTS_URL, timeout=5) as response:
                headers = response.info()
                # Parse Cache-Control to respect Google's token rotation schedule
                cache_control = headers.get("Cache-Control", "")
                max_age = 3600  # Default fallback cache duration (1 hour)
                
                for part in cache_control.split(","):
                    if "max-age" in part:
                        try:
                            max_age = int(part.split("=")[1].strip())
                        except Exception:
                            pass
                
                _certs_cache = json.loads(response.read().decode("utf-8"))
                _certs_expire_at = now + max_age
        except Exception as e:
            # If the network call fails, return the stale cache if we have one; otherwise, raise
            if _certs_cache:
                print(f"[Firebase Auth] Failed to refresh certs, using cached: {e}")
                return _certs_cache
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch Firebase signing certificates: {str(e)}"
            )
            
    return _certs_cache

def ensure_user_profile_exists(user_id_uuid: str, email: str, name: str):
    """
    Ensures that a user profile and default user preferences exist in the Supabase database.
    This replaces the trigger database actions of the legacy Supabase Auth system.
    """
    from database import get_db
    db = get_db()
    
    try:
        # 1. Check if user profile already exists
        profile_res = db.table("profiles").select("id").eq("id", user_id_uuid).execute()
        if not profile_res.data:
            print(f"[Firebase Auth] Provisioning new database profile for UUID: {user_id_uuid}")
            # Insert profile
            display_name = name or email.split("@")[0] or "User"
            db.table("profiles").insert({
                "id": user_id_uuid,
                "display_name": display_name
            }).execute()
            
            # 2. Insert default user preferences for personalization fallbacks
            try:
                db.table("user_preferences").insert({
                    "user_id": user_id_uuid
                }).execute()
            except Exception as pref_err:
                print(f"[Firebase Auth] Preferences already existed or failed to insert: {pref_err}")
                
    except Exception as e:
        # Log database error, but do not prevent login/auth from completing
        print(f"[Firebase Auth] DB profile check/insert failed: {e}")

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Verify the Firebase ID token and return the mapped database user ID (deterministic UUID).
    Raises an HTTP 401 exception if the token is invalid, expired, or missing.
    """
    token = credentials.credentials
    
    # Firebase Project ID is required to verify token audience
    firebase_project_id = os.getenv("VITE_FIREBASE_PROJECT_ID") or os.getenv("FIREBASE_PROJECT_ID")
    if not firebase_project_id:
        raise HTTPException(
            status_code=500,
            detail="FIREBASE_PROJECT_ID (or VITE_FIREBASE_PROJECT_ID) environment variable not set."
        )

    try:
        # 1. Inspect unverified token header to retrieve the key ID ('kid')
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Invalid token: missing 'kid' header.")

        # 2. Match Key ID with Google's public certificates
        public_keys = get_google_public_keys()
        public_key = public_keys.get(kid)
        if not public_key:
            raise HTTPException(status_code=401, detail="Invalid token: unknown signing key ID.")

        # 3. Decode and verify RS256 JWT signature and claims
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=firebase_project_id,
            issuer=f"https://securetoken.google.com/{firebase_project_id}",
            options={"verify_aud": True}
        )

        # 4. Extract standard claims from the verified token
        firebase_uid = payload.get("sub")
        email = payload.get("email", "")
        name = payload.get("name", "")

        if not firebase_uid:
            raise HTTPException(status_code=401, detail="Invalid token: missing subject ('sub') claim.")

        # 5. Deterministically map the alphanumeric Firebase UID to a valid RFC4122 UUIDv5
        # This keeps all database tables (foreign keys, UUID types) completely intact!
        user_id_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, firebase_uid))

        # 6. Lazy-provision database entries if this is a newly registered user
        ensure_user_profile_exists(user_id_uuid, email, name)

        return user_id_uuid

    except JWTError as jwt_err:
        raise HTTPException(
            status_code=401,
            detail=f"Could not validate credentials: {str(jwt_err)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from jwt_err
