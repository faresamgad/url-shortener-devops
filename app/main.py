"""Minimal URL shortener: Postgres stores links, Redis caches lookups."""
import os
import secrets
import string

import psycopg
import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

# Configuration comes from environment variables (12-factor style),
# so the same image runs on your laptop, in CI, and in Kubernetes.
DATABASE_URL = os.environ["DATABASE_URL"]  # e.g. postgresql://user:pass@host:5432/db
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = 3600

app = FastAPI(title="url-shortener")
cache = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def db():
    return psycopg.connect(DATABASE_URL, autocommit=True)


@app.on_event("startup")
def create_table() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                code       VARCHAR(10) PRIMARY KEY,
                url        TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


class ShortenRequest(BaseModel):
    url: HttpUrl


def new_code(length: int = 6) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@app.get("/health")
def health() -> dict:
    status = {"postgres": "ok", "redis": "ok"}
    try:
        with db() as conn:
            conn.execute("SELECT 1")
    except Exception:
        status["postgres"] = "down"
    try:
        cache.ping()
    except Exception:
        status["redis"] = "down"
    if "down" in status.values():
        raise HTTPException(status_code=503, detail=status)
    return status


@app.post("/shorten", status_code=201)
def shorten(req: ShortenRequest) -> dict:
    code = new_code()
    with db() as conn:
        conn.execute("INSERT INTO links (code, url) VALUES (%s, %s)", (code, str(req.url)))
    return {"code": code, "short_url": f"/{code}"}


@app.get("/{code}")
def resolve(code: str):
    url = cache.get(code)
    if url is None:
        with db() as conn:
            row = conn.execute("SELECT url FROM links WHERE code = %s", (code,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        url = row[0]
        cache.set(code, url, ex=CACHE_TTL_SECONDS)
    return RedirectResponse(url, status_code=307)
