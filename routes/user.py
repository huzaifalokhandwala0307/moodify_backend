from fastapi import APIRouter, HTTPException, Depends
from typing import List
from database import get_db
from auth import get_current_user_id
from utils.schemas import (
    UserProfile, HistoryCreate, LikeCreate, SaveCreate, PreferencesUpdate, SongResponse
)

router = APIRouter(prefix="/user", tags=["user"])

@router.get("/profile/{user_id}", response_model=UserProfile)
def get_profile(user_id: str, current_user: str = Depends(get_current_user_id)):
    if user_id == "me":
        user_id = current_user
    elif user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to access this profile")
    
    db = get_db()
    res = db.table("profiles").select("*").eq("id", user_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return res.data

@router.post("/history")
def log_history(data: HistoryCreate, current_user: str = Depends(get_current_user_id)):
    db = get_db()
    try:
        db.table("listening_history").insert({
            "user_id": current_user,
            "song_id": data.song_id
        }).execute()
        return {"message": "History logged"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/likes")
def like_song(data: LikeCreate, current_user: str = Depends(get_current_user_id)):
    db = get_db()
    try:
        db.table("liked_tracks").insert({
            "user_id": current_user,
            "song_id": data.song_id
        }).execute()
        return {"message": "Song liked"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Song already liked or error occurred")

@router.delete("/likes/{song_id}")
def unlike_song(song_id: str, current_user: str = Depends(get_current_user_id)):
    db = get_db()
    try:
        db.table("liked_tracks").delete().eq("user_id", current_user).eq("song_id", song_id).execute()
        return {"message": "Song unliked"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/saves")
def save_song(data: SaveCreate, current_user: str = Depends(get_current_user_id)):
    db = get_db()
    try:
        db.table("saved_tracks").insert({
            "user_id": current_user,
            "song_id": data.song_id
        }).execute()
        return {"message": "Song saved"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Song already saved or error occurred")

@router.delete("/saves/{song_id}")
def unsave_song(song_id: str, current_user: str = Depends(get_current_user_id)):
    db = get_db()
    try:
        db.table("saved_tracks").delete().eq("user_id", current_user).eq("song_id", song_id).execute()
        return {"message": "Song unsaved"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/history/{user_id}")
def get_user_history(user_id: str, current_user: str = Depends(get_current_user_id)):
    if user_id == "me":
        user_id = current_user
    elif user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    db = get_db()
    res = db.table("listening_history").select("songs(*)").eq("user_id", user_id).order("played_at", desc=True).limit(50).execute()
    return [item.get("songs") for item in res.data if item.get("songs")]

@router.get("/likes/{user_id}")
def get_user_likes(user_id: str, current_user: str = Depends(get_current_user_id)):
    if user_id == "me":
        user_id = current_user
    elif user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    db = get_db()
    res = db.table("liked_tracks").select("songs(*)").eq("user_id", user_id).order("liked_at", desc=True).execute()
    return [item.get("songs") for item in res.data if item.get("songs")]

@router.get("/saves/{user_id}")
def get_user_saves(user_id: str, current_user: str = Depends(get_current_user_id)):
    if user_id == "me":
        user_id = current_user
    elif user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    db = get_db()
    res = db.table("saved_tracks").select("songs(*)").eq("user_id", user_id).order("saved_at", desc=True).execute()
    return [item.get("songs") for item in res.data if item.get("songs")]

@router.post("/preferences")
def update_preferences(data: PreferencesUpdate, current_user: str = Depends(get_current_user_id)):
    db = get_db()
    try:
        db.table("user_preferences").upsert({
            "user_id": current_user,
            **data.model_dump(exclude_unset=True)
        }).execute()
        return {"message": "Preferences updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
