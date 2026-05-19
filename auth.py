import os
import time
import json
import uuid
import urllib.request
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()

GOOGLE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
_certs_cache = {}
_certs_expire_at = 0


def get_google_public_keys():
    global _certs_cache, _certs_expire_at
    now = time.time()

    if not _certs_cache or now >= _certs_expire_at:
        try:
            with urllib.request.urlopen(GOOGLE_CERTS_URL, timeout=10) as response:
                cache_control = response.info().get("Cache-Control", "")
                max_age = 3600
                for part in cache_control.split(","):
                    if "max-age" in part:
                        try:
                            max_age = int(part.split("=")[1].strip())
                        except Exception:
                            pass
                _certs_cache = json.loads(response.read().decode("utf-8"))
                _certs_expire_at = now + max_age
        except Exception as e:
            if _certs_cache:
                print(f"[Firebase Auth] Using cached certs: {e}")
                return _certs_cache
            # Don't raise HTTPException here — raise a plain exception
            raise RuntimeError(f"Failed to fetch Firebase certs: {e}")

    return _certs_cache


def ensure_user_profile_exists(user_id_uuid: str, email: str, name: str):
    try:
        from database import get_db
        db = get_db()

        profile_res = db.table("profiles").select("id").eq("id", user_id_uuid).execute()
        if not profile_res.data:
            display_name = name or (email.split("@")[0] if email else "User")
            db.table("profiles").insert({
                "id": user_id_uuid,
                "display_name": display_name
            }).execute()

            try:
                db.table("user_preferences").insert({
                    "user_id": user_id_uuid
                }).execute()
            except Exception:
                pass  # preferences already exist

    except Exception as e:
        # Never crash auth because of DB issue
        print(f"[Firebase Auth] Profile provision failed (non-fatal): {e}")


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    token = credentials.credentials

    firebase_project_id = (
        os.getenv("FIREBASE_PROJECT_ID") or
        os.getenv("VITE_FIREBASE_PROJECT_ID")
    )

    if not firebase_project_id:
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: FIREBASE_PROJECT_ID not set."
        )

    # Step 1 — get Google public keys
    try:
        public_keys = get_google_public_keys()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Step 2 — get kid from token header
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token format.")

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Invalid token: missing kid.")

    public_key = public_keys.get(kid)
    if not public_key:
        raise HTTPException(status_code=401, detail="Invalid token: unknown signing key.")

    # Step 3 — verify and decode JWT
    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=firebase_project_id,
            issuer=f"https://securetoken.google.com/{firebase_project_id}",
            options={"verify_aud": True}
        )
    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 4 — extract claims
    firebase_uid = payload.get("sub")
    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub.")

    email = payload.get("email", "")
    name = payload.get("name", "")

    # Step 5 — map Firebase UID to deterministic UUID
    user_id_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, firebase_uid))

    # Step 6 — provision profile (never crashes auth)
    ensure_user_profile_exists(user_id_uuid, email, name)

    return user_id_uuid