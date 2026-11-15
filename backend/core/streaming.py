import re
import aiohttp
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from backend.auth.security import get_current_user_payload

router = APIRouter(prefix="/api", tags=["Streaming"])

YT_SERVICE_URL = "http://127.0.0.1:8010"
SC_SERVICE_URL = "http://127.0.0.1:8011"

class StreamUrlRequest(BaseModel):
    user_id: Optional[int] = None
    url: str

class PreloadTrackRequest(BaseModel):
    source: Optional[str] = "all"
    id: str

def parse_track_source_and_id(raw_url: str):
    url = raw_url.strip()
    if url.startswith("sc:") or "soundcloud.com" in url:
        clean = url.replace("sc:", "")
        return "soundcloud", clean
    elif url.startswith("yt:") or "youtube.com" in url or "youtu.be" in url:
        m = re.search(r"(?:v=|\/)([a-zA-Z0-9_-]{11})", url)
        if m:
            return "yt-music", m.group(1)
        clean = url.replace("yt:", "")
        return "yt-music", clean
    else:
        m = re.search(r"(?:v=|\/)([a-zA-Z0-9_-]{11})", url)
        if m:
            return "yt-music", m.group(1)
        return "yt-music", url

_STREAM_MAP = {}

@router.post("/play/url")
async def get_stream_url(
    req: StreamUrlRequest,
    current_user: dict = Depends(get_current_user_payload)
):
    source, track_id = parse_track_source_and_id(req.url)
    
    async with aiohttp.ClientSession() as session:
        target = f"{SC_SERVICE_URL}/stream/{track_id}" if source == "soundcloud" else f"{YT_SERVICE_URL}/stream/{track_id}"

        try:
            async with session.get(target, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=f"Microservice error: {text}")
                res_data = await resp.json()
                stream_info = res_data.get("data", {})
                direct_url = stream_info.get("stream_url")
                if not direct_url:
                    raise HTTPException(status_code=404, detail="Stream URL resolution failed")
                
                key = f"{source}_{track_id}"
                _STREAM_MAP[key] = direct_url
                proxied_url = f"https://hel1o.hel1ow0rld.ru/api/play/stream/{key}"

                return {
                    "status": "ok",
                    "stream_url": proxied_url,
                    "direct_url": direct_url,
                    "title": stream_info.get("title", ""),
                    "artist": stream_info.get("artist", ""),
                    "duration": stream_info.get("duration", 0),
                    "cover_url": stream_info.get("cover_url", ""),
                    "source": source
                }
        except aiohttp.ClientConnectorError:
            raise HTTPException(status_code=503, detail=f"Microservice {source} unavailable")

@router.get("/play/stream/{stream_key}")
async def proxy_audio_stream(stream_key: str, request: Request):
    direct_url = _STREAM_MAP.get(stream_key)
    if not direct_url:
        parts = stream_key.split("_", 1)
        if len(parts) == 2:
            source, track_id = parts
            target = f"{SC_SERVICE_URL}/stream/{track_id}" if source == "soundcloud" else f"{YT_SERVICE_URL}/stream/{track_id}"
            async with aiohttp.ClientSession() as s:
                try:
                    async with s.get(target, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status == 200:
                            d = await r.json()
                            direct_url = d.get("data", {}).get("stream_url")
                            if direct_url:
                                _STREAM_MAP[stream_key] = direct_url
                except Exception:
                    pass

    if not direct_url:
        raise HTTPException(status_code=404, detail="Audio stream expired or not found")

    req_headers = {}
    range_header = request.headers.get("Range")
    if range_header:
        req_headers["Range"] = range_header

    client = aiohttp.ClientSession()
    try:
        upstream = await client.get(direct_url, headers=req_headers)
        res_headers = {}
        for h in ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"]:
            if h in upstream.headers:
                res_headers[h] = upstream.headers[h]

        async def stream_generator():
            try:
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    yield chunk
            finally:
                await upstream.release()
                await client.close()

        return StreamingResponse(
            stream_generator(),
            status_code=upstream.status,
            headers=res_headers
        )
    except Exception as e:
        await client.close()
        raise HTTPException(status_code=502, detail=str(e))

@router.post("/play/preload")
async def preload_track(
    req: PreloadTrackRequest,
    current_user: dict = Depends(get_current_user_payload)
):
    source = req.source.lower() if req.source else "all"
    track_id = req.id
    target_url = f"{SC_SERVICE_URL}/stream/{track_id.replace("sc:", "")}" if ("sc" in source or track_id.startswith("sc:")) else f"{YT_SERVICE_URL}/stream/{track_id.replace("yt:", "")}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=4)):
                pass
    except Exception:
        pass

    return {"status": "ok", "preloaded": True}
