-- SUPABASE DATABASE SCHEMA & RLS POLICIES

-- Enable pgcrypto for UUIDs if not already enabled
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Songs Table
CREATE TABLE songs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    spotify_id TEXT UNIQUE,
    track_name TEXT NOT NULL,
    artist_name TEXT,
    album TEXT,
    album_art TEXT,
    preview_url TEXT,
    spotify_url TEXT,
    popularity INTEGER DEFAULT 0,
    danceability FLOAT,
    energy FLOAT,
    valence FLOAT,
    tempo FLOAT,
    acousticness FLOAT,
    instrumentalness FLOAT,
    liveness FLOAT,
    speechiness FLOAT,
    loudness FLOAT,
    cluster INTEGER,
    genre TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- 2. Profiles Table
-- NOTE: id is TEXT (Firebase UID), NOT a FK to auth.users.
-- This app uses Firebase Auth, not Supabase Auth, so auth.users is not populated.
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    display_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- 3. User Preferences Table
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES profiles(id) ON DELETE CASCADE UNIQUE,
    preferred_energy FLOAT DEFAULT 0.5,
    preferred_danceability FLOAT DEFAULT 0.5,
    preferred_valence FLOAT DEFAULT 0.5,
    preferred_genres TEXT[],
    preferred_clusters INTEGER[],
    updated_at TIMESTAMP DEFAULT now()
);

-- 4. Listening History Table
CREATE TABLE listening_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
    song_id UUID REFERENCES songs(id),
    played_at TIMESTAMP DEFAULT now()
);

-- 5. Liked Tracks Table
CREATE TABLE liked_tracks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
    song_id UUID REFERENCES songs(id),
    liked_at TIMESTAMP DEFAULT now(),
    UNIQUE(user_id, song_id)
);

-- 6. Saved Tracks Table
CREATE TABLE saved_tracks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
    song_id UUID REFERENCES songs(id),
    saved_at TIMESTAMP DEFAULT now(),
    UNIQUE(user_id, song_id)
);

-- 7. Recommendation Logs Table
CREATE TABLE recommendation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES profiles(id),
    mode TEXT, -- 'song', 'vibe', 'personalized'
    query TEXT,
    cluster_assigned INTEGER,
    results_count INTEGER,
    created_at TIMESTAMP DEFAULT now()
);

-- ROW LEVEL SECURITY (RLS) POLICIES
-- NOTE: This app uses Firebase Auth (not Supabase Auth), so auth.uid() is always NULL.
-- The backend uses the Supabase SERVICE_ROLE key, which bypasses RLS entirely.
-- RLS is enabled for safety but policies allow service role through (default Supabase behavior).
-- Do NOT use auth.uid() checks — they will never match a Firebase user.

-- Enable RLS on all tables
ALTER TABLE songs ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE listening_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE liked_tracks ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_tracks ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_logs ENABLE ROW LEVEL SECURITY;

-- songs: public read
CREATE POLICY "Public can read songs" ON songs FOR SELECT USING (true);

-- All other tables: service role (backend) bypasses RLS automatically.
-- These permissive policies allow the anon key to also read (adjust if needed):
CREATE POLICY "Service role manages profiles" ON profiles FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role manages preferences" ON user_preferences FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role manages history" ON listening_history FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role manages liked_tracks" ON liked_tracks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role manages saved_tracks" ON saved_tracks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role manages rec_logs" ON recommendation_logs FOR ALL USING (true) WITH CHECK (true);

-- NOTE: The handle_new_user trigger on auth.users is NOT used here because
-- this app authenticates via Firebase, not Supabase Auth. auth.users is never
-- populated. Profile creation is handled in auth.py → ensure_user_profile_exists()
-- on every request, using the Supabase service_role key to bypass RLS.