from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.database import get_db
from backend.utils.schemas import UserRegister, UserLogin, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register")
def register(user_data: UserRegister):
    """
    Registers a new user via Supabase Auth.
    """
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        res = db.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password,
            "options": {
                "data": {
                    "display_name": user_data.display_name or user_data.email.split("@")[0]
                }
            }
        })
        return {"message": "User registered successfully", "user": res.user}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login", response_model=TokenResponse)
def login(user_data: UserLogin):
    """
    Logs in a user and returns a JWT token from Supabase.
    """
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        res = db.auth.sign_in_with_password({
            "email": user_data.email,
            "password": user_data.password
        })
        return TokenResponse(
            access_token=res.session.access_token,
            user_id=res.user.id
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid email or password")
