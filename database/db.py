import aiomysql
from .config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME

db_pool: aiomysql.Pool | None = None

async def init_db_pool():
    global db_pool
    if not db_pool:
        db_pool = await aiomysql.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            db=DB_NAME,
            autocommit=True,
            charset="utf8mb4",
            cursorclass=aiomysql.DictCursor,
            minsize=2,
            maxsize=20
        )
    return db_pool

async def get_db_pool() -> aiomysql.Pool:
    global db_pool
    if not db_pool:
        await init_db_pool()
    return db_pool

async def close_db_pool():
    global db_pool
    if db_pool:
        db_pool.close()
        await db_pool.wait_closed()
        db_pool = None

async def get_db():
    """Backwards compatible single connection getter."""
    return await aiomysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        autocommit=True,
        charset="utf8mb4"
    )
