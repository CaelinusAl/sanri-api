from datetime import datetime, timedelta, timezone
from typing import Optional
import os

from jose import jwt, JWTError
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("JWT_SECRET", "SUPER_SECRET_CHANGE_THIS")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})

    print("CREATE SECRET PREFIX =", SECRET_KEY[:8])
    print("CREATE DATA =", to_encode)

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        print("DECODE SECRET PREFIX =", SECRET_KEY[:8])
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("DECODE PAYLOAD =", payload)
        return payload
    except JWTError as e:
        print("JWT DECODE ERROR =", str(e))
        return None
    
    REFRESH_TOKEN_EXPIRE_DAYS = 7

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)