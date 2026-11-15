import aiomysql
from datetime import date, timedelta
from typing import Optional, Dict, Any, List
import config

db_pool: Optional[aiomysql.Pool] = None

async def init_db_pool():
    global db_pool
    db_pool = await aiomysql.create_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        db=config.DB_NAME,
        autocommit=True,
        charset="utf8mb4",
        cursorclass=aiomysql.DictCursor
    )

async def close_db_pool():
    global db_pool
    if db_pool:
        db_pool.close()
        await db_pool.wait_closed()

async def is_user_admin(tg_id: int) -> bool:
    if tg_id in config.ADMIN_IDS:
        return True
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT is_admin FROM users WHERE tg_id = %s LIMIT 1;", (tg_id,))
            res = await cur.fetchone()
            return bool(res and res.get("is_admin") == 1)

async def upsert_user(tg_id: int, username: Optional[str], first_name: Optional[str]) -> tuple[int, bool]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE tg_id = %s LIMIT 1;", (tg_id,))
            existing = await cur.fetchone()
            if existing:
                await cur.execute(
                    "UPDATE users SET username = %s, first_name = %s WHERE tg_id = %s;",
                    (username, first_name, tg_id)
                )
                return existing["id"], False
            await cur.execute(
                "INSERT INTO users (tg_id, username, first_name) VALUES (%s, %s, %s);",
                (tg_id, username, first_name)
            )
            return cur.lastrowid, True

async def get_user_profile(tg_id: int) -> Optional[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT 
                    u.id, u.tg_id, u.username, u.first_name, u.beta_access, u.is_admin, s.expires_at, s.plan AS sub_plan,
                    (SELECT COUNT(*) FROM user_uploads WHERE user_id = u.id) AS track_count,
                    (SELECT COUNT(*) FROM playlists WHERE user_id = u.id) AS playlist_count
                FROM users u
                LEFT JOIN subscriptions s ON u.id = s.user_id
                WHERE u.tg_id = %s LIMIT 1;
            """, (tg_id,))
            return await cur.fetchone()

async def get_user_by_identity(identity: str) -> Optional[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            clean = identity.lstrip("@").strip()
            if clean.isdigit():
                await cur.execute("SELECT * FROM users WHERE tg_id = %s OR id = %s LIMIT 1;", (int(clean), int(clean)))
            else:
                await cur.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s) LIMIT 1;", (clean,))
            return await cur.fetchone()

async def set_user_beta_access(target_tg_id: int, status: int = 1) -> None:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE users SET beta_access = %s WHERE tg_id = %s;", (status, target_tg_id))

async def extend_user_subscription(tg_id: int, days: int, plan: str = "lite") -> date:
    today = date.today()
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT s.expires_at FROM subscriptions s 
                JOIN users u ON s.user_id = u.id WHERE u.tg_id = %s LIMIT 1;
            """, (tg_id,))
            sub = await cur.fetchone()
            if sub and sub["expires_at"] and sub["expires_at"] >= today:
                new_date = sub["expires_at"] + timedelta(days=days)
            else:
                new_date = today + timedelta(days=days)

            await cur.execute("""
                INSERT INTO subscriptions (user_id, expires_at, plan)
                VALUES ((SELECT id FROM users WHERE tg_id = %s), %s, %s)
                ON DUPLICATE KEY UPDATE expires_at = VALUES(expires_at), plan = VALUES(plan);
            """, (tg_id, new_date, plan))

            if plan == "burzhuy":
                await cur.execute("UPDATE users SET beta_access = 1 WHERE tg_id = %s;", (tg_id,))

            return new_date

async def cancel_user_subscription(tg_id: int) -> bool:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                DELETE s FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE u.tg_id = %s;
            """, (tg_id,))
            return cur.rowcount > 0

async def get_user_playlists(tg_id: int) -> List[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT p.id, p.title, COUNT(pt.id) AS tracks_cnt
                FROM playlists p
                JOIN users u ON p.user_id = u.id
                LEFT JOIN playlist_tracks pt ON p.id = pt.playlist_id
                WHERE u.tg_id = %s
                GROUP BY p.id;
            """, (tg_id,))
            return await cur.fetchall()

async def get_playlist_title(playlist_id: int) -> str:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT title FROM playlists WHERE id = %s LIMIT 1;", (playlist_id,))
            res = await cur.fetchone()
            return res["title"] if res else "Плейлист"

async def create_playlist_with_track(user_id: int, title: str, track_id: int) -> None:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO playlists (user_id, title) VALUES (%s, %s);", (user_id, title))
            pl_id = cur.lastrowid
            await cur.execute("INSERT INTO playlist_tracks (playlist_id, track_id) VALUES (%s, %s);", (pl_id, track_id))

async def delete_track_completely(track_id: int, tg_id: int, is_admin: bool = False) -> Optional[str]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            if is_admin:
                await cur.execute("SELECT file_path FROM user_uploads WHERE id = %s LIMIT 1;", (track_id,))
            else:
                await cur.execute("""
                    SELECT t.file_path FROM user_uploads t JOIN users u ON t.user_id = u.id
                    WHERE t.id = %s AND u.tg_id = %s LIMIT 1;
                """, (track_id, tg_id))
            track = await cur.fetchone()
            if not track:
                return None
            await cur.execute("DELETE FROM user_uploads WHERE id = %s;", (track_id,))
            return track["file_path"]

async def get_admin_recent_users() -> List[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT u.id, u.tg_id, u.username, u.first_name, u.is_admin, COUNT(t.id) AS tracks_cnt
                FROM users u LEFT JOIN user_uploads t ON u.id = t.user_id
                GROUP BY u.id ORDER BY u.id DESC;
            """,)
            return await cur.fetchall()

async def get_admin_recent_tracks() -> List[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT t.id, t.title, t.artist, u.username, u.first_name
                FROM user_uploads t JOIN users u ON t.user_id = u.id
                ORDER BY t.id DESC LIMIT 50;
            """,)
            return await cur.fetchall()

async def save_client_build(branch_type: str, version_num: str, platform: str, file_path: str, file_name: str) -> None:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO client_builds (branch_type, version_num, platform, file_path, file_name)
                VALUES (%s, %s, %s, %s, %s);
            """, (branch_type, version_num, platform, file_path, file_name))

async def save_user_track(user_id: int, title: str, artist: str, file_path: str, orig_name: str) -> int:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO user_uploads (user_id, title, artist, file_path, original_filename)
                VALUES (%s, %s, %s, %s, %s);
            """, (user_id, title, artist, file_path, orig_name))
            return cur.lastrowid

async def add_track_to_playlist(playlist_id: int, track_id: int) -> None:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT IGNORE INTO playlist_tracks (playlist_id, track_id)
                VALUES (%s, %s);
            """, (playlist_id, track_id))

async def approve_auth_challenge(tg_id: int, challenge: str) -> Optional[Dict[str, Any]]:
    """
    Approves a secure cryptographic challenge for the user.
    Rejects expired challenges.
    """
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE tg_id = %s LIMIT 1;", (tg_id,))
            user = await cur.fetchone()
            if not user:
                return None

            user_id = user["id"]
            await cur.execute("""
                SELECT id, challenge, status, expires_at, device_name, client_version
                FROM auth_challenges
                WHERE challenge = %s AND status = 'pending' AND expires_at > UTC_TIMESTAMP()
                LIMIT 1;
            """, (challenge,))
            ch_data = await cur.fetchone()
            if not ch_data:
                return None

            await cur.execute("""
                UPDATE auth_challenges
                SET status = 'approved', user_id = %s
                WHERE id = %s;
            """, (user_id, ch_data["id"]))
            return ch_data

async def get_user_api_key(tg_id: int) -> Optional[str]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT k.api_key FROM api_keys k
                JOIN users u ON k.user_id = u.id
                WHERE u.tg_id = %s ORDER BY k.id DESC LIMIT 1;
            """, (tg_id,))
            res = await cur.fetchone()
            return res["api_key"] if res else None

async def generate_user_api_key(tg_id: int) -> Optional[str]:
    import secrets
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE tg_id = %s LIMIT 1;", (tg_id,))
            u = await cur.fetchone()
            if not u:
                return None
            user_id = u["id"]
            new_key = f"h1m_{secrets.token_hex(24)}"
            await cur.execute("INSERT INTO api_keys (user_id, api_key) VALUES (%s, %s);", (user_id, new_key))
            return new_key

async def get_user_admin_badges(tg_id: int) -> List[Dict[str, Any]]:
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT id, tg_id, tg_username, admin_name 
                FROM admin_badges 
                WHERE tg_id = %s;
            """, (tg_id,))
            return await cur.fetchall()
