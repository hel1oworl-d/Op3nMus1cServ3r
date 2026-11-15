import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import jwt
from packaging import version
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "music.json"

def get_config() -> dict:
    """Dynamically re-reads music.json so changing min_client_version takes effect immediately."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_security_config() -> dict:
    return get_config().get("security", {})

def get_jwt_secret() -> str:
    return get_security_config().get("jwt_secret", "hel1o_default_secret_key_change_in_production")

def get_min_client_version() -> str:
    return get_security_config().get("min_client_version", "1.0.0")

http_bearer = HTTPBearer(auto_error=False)

def verify_client_version(x_client_version: Optional[str] = Header(None)) -> str:
    """
    Enforces minimum client version to completely kill legacy clients (<= 0.0.6).
    Reads min_client_version dynamically from music.json.
    """
    min_ver = get_min_client_version()
    if not x_client_version:
        raise HTTPException(
            status_code=status.HTTP_426_UPGRADE_REQUIRED,
            detail="X-Client-Version header required. Legacy versions are deprecated and not supported."
        )
    try:
        clean_ver = x_client_version.strip().lstrip("v")
        if version.parse(clean_ver) < version.parse(min_ver):
            raise HTTPException(
                status_code=status.HTTP_426_UPGRADE_REQUIRED,
                detail=f"Client version {x_client_version} is deprecated. Minimum required version is {min_ver}. Please update the app."
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid X-Client-Version format: {x_client_version}"
        )
    return x_client_version

def hash_token(token: str) -> str:
    """Hashes refresh tokens using SHA-256 for secure DB storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(user_id: int, tg_id: int, is_admin: bool, device_id: str) -> tuple[str, datetime]:
    sec = get_security_config()
    secret = get_jwt_secret()
    algo = sec.get("jwt_algorithm", "HS256")
    exp_mins = sec.get("access_token_expire_minutes", 30)

    now = datetime.now(timezone.utc)
    expires_delta = timedelta(minutes=exp_mins)
    expire = now + expires_delta
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "tg_id": tg_id,
        "is_admin": bool(is_admin),
        "device_id": device_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access"
    }
    encoded = jwt.encode(payload, secret, algorithm=algo)
    return encoded, expire

def create_refresh_token() -> tuple[str, str, datetime]:
    """Generates raw secure token and its hash."""
    sec = get_security_config()
    exp_days = sec.get("refresh_token_expire_days", 60)
    raw_token = f"rt_{secrets.token_urlsafe(48)}"
    token_hash = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=exp_days)
    return raw_token, token_hash, expires_at

def decode_access_token(token: str) -> Dict[str, Any]:
    sec = get_security_config()
    secret = get_jwt_secret()
    algo = sec.get("jwt_algorithm", "HS256")
    try:
        payload = jwt.decode(token, secret, algorithms=[algo])
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")

async def get_current_user_payload(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    client_version: str = Depends(verify_client_version)
) -> Dict[str, Any]:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return decode_access_token(credentials.credentials)
