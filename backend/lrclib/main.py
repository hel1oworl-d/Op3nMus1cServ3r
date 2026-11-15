import os
from pathlib import Path
from typing import Optional, List
import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import uvicorn

# Load .env
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

APP_ID = os.getenv("APP_ID", "")
LRCLIB_API_KEY = os.getenv("LRCLIB_API_KEY", "")
PORT = int(os.getenv("PORT", 8012))
HOST = os.getenv("HOST", "127.0.0.1")

LRCLIB_BASE_URL = "https://lrclib.net/api"

app = FastAPI(
    root_path="/lrclib",
    title="Op3nMus1c LRCLIB Service",
    description="Microservice for fetching synchronized and plain lyrics via LRCLIB",
    version="1.0.0"
)

def get_headers() -> dict:
    user_agent = f"Hel1oMus1c ({APP_ID})" if APP_ID else "Hel1oMus1c/1.0"
    headers = {
        "User-Agent": user_agent,
        "Lrclib-Client": user_agent
    }
    if LRCLIB_API_KEY:
        headers["Authorization"] = f"Bearer {LRCLIB_API_KEY}"
        headers["X-Api-Key"] = LRCLIB_API_KEY
    return headers

class LyricsResponse(BaseModel):
    status: str
    id: Optional[int] = None
    track_name: Optional[str] = None
    artist_name: Optional[str] = None
    album_name: Optional[str] = None
    duration: Optional[float] = None
    instrumental: bool = False
    plain_lyrics: Optional[str] = None
    synced_lyrics: Optional[str] = None

@app.get("/health")
async def health_check():
    return {
        "service": "lrclib",
        "status": "healthy",
        "app_id_configured": bool(APP_ID),
        "api_key_configured": bool(LRCLIB_API_KEY)
    }

@app.get("/lyrics", response_model=LyricsResponse)
async def get_lyrics(
    track_name: str = Query(..., description="Track or song title"),
    artist_name: str = Query(..., description="Artist or performer name"),
    album_name: Optional[str] = Query(None, description="Album title"),
    duration: Optional[int] = Query(None, description="Duration in seconds")
):
    """
    Get synchronized lyrics by track name and artist name (exact match or closest candidate)
    """
    params = {
        "track_name": track_name.strip(),
        "artist_name": artist_name.strip(),
    }
    if album_name and album_name.strip():
        params["album_name"] = album_name.strip()
    if duration and duration > 0:
        params["duration"] = str(duration)

    headers = get_headers()

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. Exact match via /api/get
            async with session.get(
                f"{LRCLIB_BASE_URL}/get",
                params=params,
                timeout=aiohttp.ClientTimeout(total=6)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return LyricsResponse(
                        status="success",
                        id=data.get("id"),
                        track_name=data.get("trackName"),
                        artist_name=data.get("artistName"),
                        album_name=data.get("albumName"),
                        duration=data.get("duration"),
                        instrumental=bool(data.get("instrumental")),
                        plain_lyrics=data.get("plainLyrics"),
                        synced_lyrics=data.get("syncedLyrics")
                    )

            # 2. Fallback to search query if exact match not found
            search_query = f"{artist_name} {track_name}".strip()
            async with session.get(
                f"{LRCLIB_BASE_URL}/search",
                params={"q": search_query},
                timeout=aiohttp.ClientTimeout(total=6)
            ) as resp:
                if resp.status == 200:
                    items = await resp.json()
                    if isinstance(items, list) and items:
                        best = items[0]
                        return LyricsResponse(
                            status="success",
                            id=best.get("id"),
                            track_name=best.get("trackName"),
                            artist_name=best.get("artistName"),
                            album_name=best.get("albumName"),
                            duration=best.get("duration"),
                            instrumental=bool(best.get("instrumental")),
                            plain_lyrics=best.get("plainLyrics"),
                            synced_lyrics=best.get("syncedLyrics")
                        )

        return LyricsResponse(status="not_found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LRCLIB request error: {e}")

@app.get("/lyrics/by_id/{lyrics_id}", response_model=LyricsResponse)
async def get_lyrics_by_id(lyrics_id: int):
    headers = get_headers()
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                f"{LRCLIB_BASE_URL}/get/{lyrics_id}",
                timeout=aiohttp.ClientTimeout(total=6)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return LyricsResponse(
                        status="success",
                        id=data.get("id"),
                        track_name=data.get("trackName"),
                        artist_name=data.get("artistName"),
                        album_name=data.get("albumName"),
                        duration=data.get("duration"),
                        instrumental=bool(data.get("instrumental")),
                        plain_lyrics=data.get("plainLyrics"),
                        synced_lyrics=data.get("syncedLyrics")
                    )
        return LyricsResponse(status="not_found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LRCLIB request error: {e}")

if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
