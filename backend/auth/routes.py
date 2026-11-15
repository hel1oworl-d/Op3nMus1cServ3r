import string
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, Request, status, Header

from database.db import get_db_pool
from backend.auth.security import (
    verify_client_version,
    create_access_token,
    create_refresh_token,
    hash_token,
    get_current_user_payload
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class InitiateAuthRequest(BaseModel):
    device_id: str = Field(..., min_length=4, max_length=128)
    device_name: Optional[str] = Field(None, max_length=128)

class ExchangeAuthRequest(BaseModel):
    challenge: str = Field(..., min_length=6, max_length=128)
    device_id: str = Field(..., min_length=4, max_length=128)

class RefreshAuthRequest(BaseModel):
    refresh_token: str = Field(...)
    device_id: str = Field(..., min_length=4, max_length=128)

class LogoutRequest(BaseModel):
    refresh_token: str = Field(...)

@router.post("/initiate")
async def initiate_auth(
    req: InitiateAuthRequest,
    request: Request,
    client_ver: str = Depends(verify_client_version)
):
    """
    Initiates a secure login attempt. Returns a one-time cryptographic challenge
    and deep link to Telegram bot. Expires in 120 seconds.
    """
    challenge = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    client_ip = request.client.host if request.client else "unknown"

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO auth_challenges 
                (challenge, status, client_version, device_name, ip_address, expires_at)
                VALUES (%s, 'pending', %s, %s, %s, %s)
                """,
                (challenge, client_ver, req.device_name, client_ip, expires_at)
            )

    bot_username = "Hel1oMus1c_bot"
    tg_url = f"https://t.me/{bot_username}?start={challenge}"
    return {
        "challenge": challenge,
        "deep_link": tg_url,
        "expires_in": 600
    }

@router.get("/challenge_status")
async def check_challenge_status(
    challenge: str,
    client_ver: str = Depends(verify_client_version)
):
    """
    Polling status endpoint for clients waiting for the user to approve login in Telegram.
    """
    pool = await get_db_pool()
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT status, expires_at FROM auth_challenges WHERE challenge = %s LIMIT 1;",
                (challenge,)
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Challenge not found")
            
            exp = row["expires_at"]
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
                
            if now > exp:
                await cur.execute("UPDATE auth_challenges SET status = 'expired' WHERE challenge = %s;", (challenge,))
                return {"status": "expired"}

            return {"status": row["status"]}

@router.post("/exchange")
async def exchange_challenge_for_tokens(
    req: ExchangeAuthRequest,
    request: Request,
    client_ver: str = Depends(verify_client_version)
):
    """
    Exchanges an approved challenge for Access and Refresh tokens.
    Challenge is consumed immediately and cannot be reused.
    """
    pool = await get_db_pool()
    now = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else "unknown"

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, user_id, status, expires_at FROM auth_challenges WHERE challenge = %s LIMIT 1;",
                (req.challenge,)
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Invalid auth challenge")

            exp = row["expires_at"]
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)

            if now > exp or row["status"] == "expired":
                raise HTTPException(status_code=400, detail="Auth challenge has expired")

            if row["status"] != "approved" or not row["user_id"]:
                raise HTTPException(status_code=400, detail="Auth challenge not yet approved or already used")

            user_id = row["user_id"]
            # Mark consumed immediately
            await cur.execute(
                "UPDATE auth_challenges SET status = 'consumed' WHERE id = %s;",
                (row["id"],)
            )

            # Get user info
            await cur.execute("SELECT id, tg_id, username, first_name, is_admin FROM users WHERE id = %s LIMIT 1;", (user_id,))
            user = await cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            access_token, acc_exp = create_access_token(
                user_id=user["id"],
                tg_id=user.get("tg_id") or 0,
                is_admin=bool(user.get("is_admin")),
                device_id=req.device_id
            )
            raw_refresh, ref_hash, ref_exp = create_refresh_token()

            await cur.execute(
                """
                INSERT INTO user_refresh_tokens
                (user_id, token_hash, device_id, ip_address, client_version, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user["id"], ref_hash, req.device_id, client_ip, client_ver, ref_exp)
            )

            return {
                "access_token": access_token,
                "refresh_token": raw_refresh,
                "token_type": "bearer",
                "access_token_expires_at": acc_exp.isoformat(),
                "user": {
                    "id": user["id"],
                    "tg_id": user.get("tg_id"),
                    "username": user.get("username"),
                    "first_name": user.get("first_name"),
                    "is_admin": bool(user.get("is_admin"))
                }
            }

@router.post("/refresh")
async def refresh_tokens(
    req: RefreshAuthRequest,
    request: Request,
    client_ver: str = Depends(verify_client_version)
):
    """
    Rotates refresh token and provides new access token.
    Detects reuse and revokes compromised sessions.
    """
    token_hash = hash_token(req.refresh_token)
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, user_id, device_id, revoked, expires_at
                FROM user_refresh_tokens
                WHERE token_hash = %s LIMIT 1;
                """,
                (token_hash,)
            )
            token_row = await cur.fetchone()
            if not token_row:
                raise HTTPException(status_code=401, detail="Invalid refresh token")

            if token_row["revoked"]:
                # Suspicious token reuse attempt: revoke all tokens for this device/user
                await cur.execute(
                    "UPDATE user_refresh_tokens SET revoked = 1 WHERE user_id = %s AND device_id = %s;",
                    (token_row["user_id"], token_row["device_id"])
                )
                raise HTTPException(status_code=401, detail="Compromised token detected. Session terminated.")

            exp = token_row["expires_at"]
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)

            if now > exp:
                await cur.execute("UPDATE user_refresh_tokens SET revoked = 1 WHERE id = %s;", (token_row["id"],))
                raise HTTPException(status_code=401, detail="Refresh token expired. Please re-authenticate.")

            # Check device_id binding
            if token_row["device_id"] != req.device_id:
                await cur.execute("UPDATE user_refresh_tokens SET revoked = 1 WHERE id = %s;", (token_row["id"],))
                raise HTTPException(status_code=401, detail="Device mismatch. Session revoked.")

            # Invalidate old refresh token (Token Rotation)
            await cur.execute("UPDATE user_refresh_tokens SET revoked = 1 WHERE id = %s;", (token_row["id"],))

            # Fetch user
            await cur.execute("SELECT id, tg_id, username, first_name, is_admin FROM users WHERE id = %s LIMIT 1;", (token_row["user_id"],))
            user = await cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            new_access_token, acc_exp = create_access_token(
                user_id=user["id"],
                tg_id=user.get("tg_id") or 0,
                is_admin=bool(user.get("is_admin")),
                device_id=req.device_id
            )
            new_raw_refresh, new_ref_hash, new_ref_exp = create_refresh_token()

            await cur.execute(
                """
                INSERT INTO user_refresh_tokens
                (user_id, token_hash, device_id, ip_address, client_version, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user["id"], new_ref_hash, req.device_id, client_ip, client_ver, new_ref_exp)
            )

            return {
                "access_token": new_access_token,
                "refresh_token": new_raw_refresh,
                "token_type": "bearer",
                "access_token_expires_at": acc_exp.isoformat()
            }

@router.post("/logout")
async def logout(
    req: LogoutRequest,
    current_user: dict = Depends(get_current_user_payload)
):
    token_hash = hash_token(req.refresh_token)
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE user_refresh_tokens SET revoked = 1 WHERE token_hash = %s AND user_id = %s;",
                (token_hash, current_user["user_id"])
            )
    return {"status": "ok", "detail": "Logged out successfully"}

@router.get("/me")
async def get_current_user_info(
    current_user: dict = Depends(get_current_user_payload)
):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT u.id, u.tg_id, u.username, u.first_name, u.beta_access, u.is_admin,
                       s.expires_at AS sub_expires, s.plan AS sub_plan
                FROM users u
                LEFT JOIN subscriptions s ON u.id = s.user_id
                WHERE u.id = %s LIMIT 1;
            """, (current_user["user_id"],))
            user = await cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return {"user": user}
