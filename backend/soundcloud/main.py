import os
import re
import time
import asyncio
import aiohttp
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import uvicorn

PORT = 8011
HOST = "127.0.0.1"

app = FastAPI(
    title="Op3nMus1c SoundCloud Service",
    description="SoundCloud search and streaming microservice",
    version="1.0.0"
)

class SoundCloudClient:
    def __init__(self):
        self._client_id = None
        self._last_fetched = 0
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

    async def get_client_id(self, session: aiohttp.ClientSession) -> str:
        if self._client_id and (time.time() - self._last_fetched < 86400):
            return self._client_id

        try:
            async with session.get("https://soundcloud.com", headers=self._headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                html = await resp.text()

            script_urls = re.findall(r'https://a-v2\.sndcdn\.com/assets/[a-zA-Z0-9_.-]+\.js', html)
            for s_url in reversed(script_urls):
                try:
                    async with session.get(s_url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=5)) as s_resp:
                        js = await s_resp.text()
                        m = re.search(r"client_id=([a-zA-Z0-9]{32})", js)
                        if m:
                            self._client_id = m.group(1)
                            self._last_fetched = time.time()
                            return self._client_id
                except Exception:
                    continue
        except Exception as e:
            print(f"[SoundCloud] Error fetching client_id: {e}")

        return self._client_id or "swtEGNKrP2w6Z5B8DVvAurWCwNQBlgMd"

    def _clean_cover(self, artwork_url: str, avatar_url: str) -> str:
        cover = artwork_url or avatar_url or ""
        if "default_avatar" in cover:
            cover = ""
        if cover and "-large" in cover:
            cover = cover.replace("-large", "-t500x500")
        return cover

sc = SoundCloudClient()

@app.get("/health")
async def health():
    return {"service": "soundcloud", "status": "healthy"}

@app.get("/search")
async def search(q: str = Query(..., description="Search query"), limit: int = 25):
    async with aiohttp.ClientSession() as session:
        cid = await sc.get_client_id(session)
        url = "https://api-v2.soundcloud.com/search/tracks"
        params = {"q": q.strip(), "client_id": cid, "limit": limit}
        async with session.get(url, params=params, headers=sc._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return {"status": "error", "tracks": []}
            data = await resp.json()

    results = []
    for t in data.get("collection", []):
        if not t.get("id"):
            continue
        artwork = t.get("artwork_url") or ""
        avatar = (t.get("user") or {}).get("avatar_url") or ""
        cover = sc._clean_cover(artwork, avatar)
        dur_sec = int(t.get("duration", 0) / 1000)

        results.append({
            "id": f"sc:{t['id']}",
            "source": "SoundCloud",
            "title": t.get("title", ""),
            "artist": (t.get("user") or {}).get("username", "Unknown Artist"),
            "duration": dur_sec,
            "cover_url": cover,
            "permalink_url": t.get("permalink_url")
        })

    return {"status": "ok", "tracks": results}

@app.get("/stream/{track_id}")
async def get_stream(track_id: str):
    clean_id = track_id.replace("sc:", "")
    async with aiohttp.ClientSession() as session:
        cid = await sc.get_client_id(session)
        url = f"https://api-v2.soundcloud.com/tracks/{clean_id}"
        params = {"client_id": cid}
        async with session.get(url, params=params, headers=sc._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=404, detail="Track not found on SoundCloud")
            data = await resp.json()

        media = data.get("media", {})
        transcodings = media.get("transcodings", [])

        # Filter out snippets if full exists
        full_trans = [t for t in transcodings if not t.get("snipped", False)]
        candidate_list = full_trans if full_trans else transcodings

        target = None
        for trans in candidate_list:
            fmt = trans.get("format", {})
            if fmt.get("protocol") == "progressive" and not trans.get("snipped", False):
                target = trans
                break
        if not target and candidate_list:
            target = candidate_list[0]

        stream_url = None
        if target:
            async with session.get(target["url"], params={"client_id": cid}, headers=sc._headers) as s_resp:
                if s_resp.status == 200:
                    s_data = await s_resp.json()
                    stream_url = s_data.get("url")

        artwork = data.get("artwork_url") or ""
        avatar = (data.get("user") or {}).get("avatar_url") or ""
        cover = sc._clean_cover(artwork, avatar)

        return {
            "status": "ok",
            "id": f"sc:{clean_id}",
            "source": "SoundCloud",
            "title": data.get("title", ""),
            "artist": (data.get("user") or {}).get("username", "Unknown"),
            "duration": int(data.get("duration", 0) / 1000),
            "cover_url": cover,
            "stream_url": stream_url
        }

if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
