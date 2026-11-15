import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from contextlib import asynccontextmanager

from backend.auth.routes import router as auth_router
from backend.core.streaming import router as streaming_router
from backend.core.playlists import router as playlists_router
from backend.auth.security import get_current_user_payload
from database.db import init_db_pool, close_db_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    yield
    await close_db_pool()

app = FastAPI(
    title="Hel1oMus1c Core Gateway",
    description="Secured Microservices Authentication & Gateway API for Hel1oMus1c",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(streaming_router)
app.include_router(playlists_router)

@app.get("/")
async def root():
    return {
        "service": "Hel1oMus1c Core Gateway",
        "status": "online",
        "version": "1.0.0",
        "auth_security": "JWT + Encrypted Challenge (HMAC-SHA256)"
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=False)
