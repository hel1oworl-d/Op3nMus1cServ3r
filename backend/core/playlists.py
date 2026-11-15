from fastapi import APIRouter
from database.db import get_db_pool

router = APIRouter(prefix="/api", tags=["Playlists"])

@router.get("/user/playlists/{playlist_id}/tracks")
@router.get("/playlists/{playlist_id}/tracks")
async def get_playlist_tracks(playlist_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, playlist_id, track_id, title, artist, url, source, thumbnail, added_at FROM playlist_tracks WHERE playlist_id = %s ORDER BY id ASC;", (playlist_id,))
            tracks = await cur.fetchall()
            return {"status": "ok", "tracks": tracks}

@router.get("/user/favorites")
async def get_user_favorites(user_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, title, artist, url, thumbnail, source, created_at FROM user_favorites WHERE user_id = %s ORDER BY id DESC;", (user_id,))
            favs = await cur.fetchall()
            return {"status": "ok", "favorites": favs, "tracks": favs}

