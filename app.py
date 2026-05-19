"""
Moodify — FastAPI Entry Point
===============================
Production-ready music recommendation API.

Startup:
  - Loads KMeans model from pickle
  - Configures CORS for React frontend
  - Configures rate limiting and request logging
"""

from __future__ import annotations

import logging
import os
import time

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

# ─── Logging configuration ───────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("moodify.app")

# ─── Rate Limiter ────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ─── Lifespan: startup & shutdown ────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    from recommender import load_model

    logger.info("=" * 50)
    logger.info("  Moodify Backend Starting Up")
    logger.info("=" * 50)

    # Load model
    model_path = os.getenv("MODEL_PATH", "model/kmeans_model.pkl")
    try:
        model = load_model(model_path)
        logger.info("✓ KMeans model loaded successfully")
    except RuntimeError as exc:
        logger.error("✗ Failed to load model: %s", exc)

    logger.info("=" * 50)
    logger.info("  Moodify Backend Ready")
    logger.info("=" * 50)

    yield  # ← App is running

    logger.info("Moodify Backend shutting down...")


# ─── Create FastAPI app ──────────────────────────────────────
app = FastAPI(
    title="Moodify API",
    description="Music recommendation engine with Supabase integration.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── CORS middleware ──────────────────────────────────────────
origins = [
    "https://moodify-nu-henna.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Request Logging Middleware ──────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    formatted_process_time = '{0:.2f}'.format(process_time)
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {formatted_process_time}ms")
    return response

# ─── Register route modules ──────────────────────────────────
from routes.health import router as health_router
from routes.songs import router as songs_router
from routes.recommend import router as recommend_router
from routes.user import router as user_router

# Add rate limits to routers
app.include_router(health_router)
app.include_router(songs_router, dependencies=[])
app.include_router(recommend_router)
app.include_router(user_router)


# ─── Root redirect ───────────────────────────────────────────
@app.get("/", include_in_schema=False)
@limiter.limit("60/minute")
async def root(request: Request):
    return {
        "service": "Moodify API",
        "version": "1.0.0",
        "docs": "/docs",
        # "health": "/health",
    }
