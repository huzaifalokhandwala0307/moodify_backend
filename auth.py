import os
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

# Note: In production, Supabase signs JWTs with your project's JWT Secret.
# You can verify them on the backend using the `jose` library without making a network request.

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """
    Verify the Supabase JWT token and return the user ID.
    Raises an HTTP 401 exception if the token is invalid or missing.
    """
    token = credentials.credentials
    if not SUPABASE_JWT_SECRET:
        # Fallback for development if secret isn't provided, though highly insecure.
        # Ideally, always provide SUPABASE_JWT_SECRET in .env
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_JWT_SECRET environment variable not set."
        )

    try:
        # Supabase uses HS256 for JWTs
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing subject")
        return user_id
    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
