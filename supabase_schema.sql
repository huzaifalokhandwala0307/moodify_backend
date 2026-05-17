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
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- 3. User Preferences Table
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE UNIQUE,
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
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    song_id UUID REFERENCES songs(id),
    played_at TIMESTAMP DEFAULT now()
);

-- 5. Liked Tracks Table
CREATE TABLE liked_tracks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    song_id UUID REFERENCES songs(id),
    liked_at TIMESTAMP DEFAULT now(),
    UNIQUE(user_id, song_id)
);

-- 6. Saved Tracks Table
CREATE TABLE saved_tracks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    song_id UUID REFERENCES songs(id),
    saved_at TIMESTAMP DEFAULT now(),
    UNIQUE(user_id, song_id)
);

-- 7. Recommendation Logs Table
CREATE TABLE recommendation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id),
    mode TEXT, -- 'song', 'vibe', 'personalized'
    query TEXT,
    cluster_assigned INTEGER,
    results_count INTEGER,
    created_at TIMESTAMP DEFAULT now()
);

-- ROW LEVEL SECURITY (RLS) POLICIES

-- Enable RLS on all tables
ALTER TABLE songs ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE listening_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE liked_tracks ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_tracks ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_logs ENABLE ROW LEVEL SECURITY;

-- songs: public read, no public write
CREATE POLICY "Public can read songs" ON songs FOR SELECT USING (true);
-- Service role (backend) will bypass RLS for inserts/updates

-- profiles: user can only read/update their own row
CREATE POLICY "Users can view own profile" ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);

-- user_preferences: user can only read/update their own
CREATE POLICY "Users can view own preferences" ON user_preferences FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own preferences" ON user_preferences FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own preferences" ON user_preferences FOR UPDATE USING (auth.uid() = user_id);

-- listening_history: user can insert + read their own only
CREATE POLICY "Users can view own history" ON listening_history FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own history" ON listening_history FOR INSERT WITH CHECK (auth.uid() = user_id);

-- liked_tracks: user can insert/delete/read their own only
CREATE POLICY "Users can view own liked tracks" ON liked_tracks FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own liked tracks" ON liked_tracks FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own liked tracks" ON liked_tracks FOR DELETE USING (auth.uid() = user_id);

-- saved_tracks: user can insert/delete/read their own only
CREATE POLICY "Users can view own saved tracks" ON saved_tracks FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own saved tracks" ON saved_tracks FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own saved tracks" ON saved_tracks FOR DELETE USING (auth.uid() = user_id);

-- recommendation_logs: user can read their own only, insert own
CREATE POLICY "Users can view own logs" ON recommendation_logs FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own logs" ON recommendation_logs FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Set up a trigger to automatically create a profile when a new user signs up in Supabase Auth
CREATE OR REPLACE FUNCTION public.handle_new_user() 
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, display_name)
  VALUES (new.id, new.raw_user_meta_data->>'display_name');
  
  INSERT INTO public.user_preferences (user_id)
  VALUES (new.id);
  
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
