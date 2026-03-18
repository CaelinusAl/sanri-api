from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import os

from jose import jwt, JWTError
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET missing in environment variables")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    password = password[:72]  # 🔥 FIX
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        password = password[:72]  # 🔥 FIX
        return pwd_context.verify(password, password_hash)
    except Exception as e:
        print("VERIFY ERROR:", e)
        return False

def _build_token(
    data: dict[str, Any],
    expires_delta: timedelta,
    token_type: str,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({
        "exp": expire,
        "type": token_type,
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: dict[str, Any]) -> str:
    return _build_token(
        data=data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )


def create_refresh_token(data: dict[str, Any]) -> str:
    return _build_token(
        data=data,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


def decode_token(token: str) -> Optional[dict[str, Any]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def decode_token_or_raise(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    if not payload:
        raise ValueError("Invalid token")
    return payload


def get_token_subject(token: str) -> Optional[str]:
    payload = decode_token(token)
    if not payload:
        return None
    sub = payload.get("sub")
    return str(sub) if sub is not None else None


def is_refresh_token(payload: dict[str, Any]) -> bool:
    return payload.get("type") == "refresh"


def is_access_token(payload: dict[str, Any]) -> bool:
    return payload.get("type") == "access"