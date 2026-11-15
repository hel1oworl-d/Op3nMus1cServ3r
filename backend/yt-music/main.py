import os
import re
import time
import asyncio
import aiohttp
from typing import Optional, List
from collections import OrderedDict
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import uvicorn
import yt_dlp
from ytmusicapi import YTMusic

PORT = 8010
HOST = "127.0.0.1"

app = FastAPI(
    title="Op3nMus1c YouTube Music Service",
    description="YouTube Music search, metadata and direct audio stream resolution",
    version="1.0.0"
)

class StreamUrlCache:
    def __init__(self, ttl=10800, maxsize=1000): # 3 hours TTL
        self.ttl = ttl
        self.maxsize = maxsize
        self._cache = OrderedDict()

    def get(self, key):
        if key in self._cache:
            url, ts = self._cache[key]
            if time.time() - ts < self.ttl:
                self._cache.move_to_end(key)
                return url
            else:
                del self._cache[key]
        return None

    def set(self, key, url):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (url, time.time())
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)

stream_cache = StreamUrlCache()

class YouTubeMusicClient:
    def __init__(self):
        self.yt = YTMusic()
        self._ydl_opts = {
            "format": "ba/b",
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"]
                }
            }
        }
        self._ydl = yt_dlp.YoutubeDL(self._ydl_opts)

    def _get_hd_cover(self, thumbnails: list, size: int = 540) -> str:
        if not thumbnails:
            return ""
        raw_url = thumbnails[-1].get("url", "")
        if "googleusercontent.com" in raw_url:
            return re.sub(r'=w\d+-h\d+.*', f'=w{size}-h{size}-l90-rj', raw_url)
        return raw_url

    async def search(self, query: str, limit: int = 25) -> list[dict]:
        url = 'https://music.youtube.com/youtubei/v1/search'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Content-Type': 'application/json',
        }
        body = {
            'context': {
                'client': {
                    'clientName': 'WEB_REMIX',
                    'clientVersion': '1.20240101.01.00',
                    'hl': 'ru',
                    'gl': 'RU'
                }
            },
            'query': query,
            'params': 'EgWKAQIIAWoQEAMQBBAJEAoQBRAREBAQFQ%3D%3D'
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
            except Exception as e:
                print(f"[YTMusic] Search error: {e}")
                return []

        results = []
        try:
            sections = data['contents']['tabbedSearchResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents']
            for sec in sections:
                music_shelf = sec.get('musicShelfRenderer')
                if not music_shelf:
                    continue
                for item in music_shelf.get('contents', []):
                    flex_item = item.get('musicResponsiveListItemRenderer')
                    if not flex_item:
                        continue
                    cols = flex_item.get('flexColumns', [])
                    title = 'Unknown'
                    artist = 'Unknown'
                    vid = flex_item.get('playlistItemData', {}).get('videoId')
                    if not vid:
                        menu = flex_item.get('menu', {})
                        for m_item in menu.get('menuRenderer', {}).get('items', []):
                            nav = m_item.get('menuNavigationItemRenderer', {}).get('navigationEndpoint', {})
                            vid = nav.get('watchEndpoint', {}).get('videoId')
                            if vid:
                                break
                    if cols:
                        runs0 = cols[0].get('musicResponsiveListItemFlexColumnRenderer', {}).get('text', {}).get('runs', [])
                        if runs0:
                            title = runs0[0].get('text', title)
                        if len(cols) > 1:
                            runs1 = cols[1].get('musicResponsiveListItemFlexColumnRenderer', {}).get('text', {}).get('runs', [])
                            if runs1:
                                artist = runs1[0].get('text', artist)

                    thumbs = flex_item.get('thumbnail', {}).get('musicThumbnailRenderer', {}).get('thumbnail', {}).get('thumbnails', [])
                    cover = self._get_hd_cover(thumbs, size=300)

                    if vid and title != 'Unknown':
                        results.append({
                            'id': f'yt:{vid}',
                            'source': 'YT Music',
                            'title': title,
                            'artist': artist,
                            'album': '',
                            'duration': 180,
                            'cover_url': cover
                        })
                        if len(results) >= limit:
                            break
                if len(results) >= limit:
                    break
        except Exception as e:
            print(f"[YTMusic] Extract error: {e}")

        return results

    async def get_stream(self, video_id: str) -> dict:
        clean_id = video_id.replace("yt:", "")
        cached_url = stream_cache.get(clean_id)
        if cached_url:
            return {
                "id": f"yt:{clean_id}",
                "source": "YT Music",
                "stream_url": cached_url
            }

        def _extract():
            return self._ydl.extract_info(f"https://www.youtube.com/watch?v={clean_id}", download=False)

        info = await asyncio.to_thread(_extract)
        stream_url = info.get("url")
        if stream_url:
            stream_cache.set(clean_id, stream_url)

        return {
            "id": f"yt:{clean_id}",
            "source": "YT Music",
            "title": info.get("title", "Track"),
            "artist": info.get("uploader", "Unknown"),
            "duration": int(info.get("duration", 0)),
            "cover_url": info.get("thumbnail", ""),
            "stream_url": stream_url
        }

yt_client = YouTubeMusicClient()

@app.get("/health")
async def health():
    return {"service": "youtube_music", "status": "healthy"}

@app.get("/search")
async def search(q: str = Query(..., description="Search query"), limit: int = 25):
    tracks = await yt_client.search(q, limit=limit)
    return {"status": "ok", "tracks": tracks}

@app.get("/stream/{video_id}")
async def get_stream(video_id: str):
    try:
        data = await yt_client.get_stream(video_id)
        if not data.get("stream_url"):
            raise HTTPException(status_code=404, detail="Stream URL not found")
        return {"status": "ok", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
