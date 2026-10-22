"""
Baseline Cybersecurity: Authentication & Role-Based Access Control (RBAC).
Roles: viewer (read), operator (acknowledge alerts, run simulations), admin (config, user management).
Tokens: Short-lived JWT stored in HttpOnly, Secure, SameSite=Strict cookies.
Passwords: Salted & hashed using bcrypt.
"""

import os
import time
import json
import base64
import hmac
import hashlib
import secrets
import sqlite3
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

try:
    from jose import jwt, JWTError
    HAS_JOSE = True
except ImportError:
    HAS_JOSE = False
    JWTError = Exception

logger = logging.getLogger("bwssb.security.auth")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "security.db")

# In production mode (ENVIRONMENT=production), refuse default secrets
ENV = os.environ.get("ENVIRONMENT", "development")
JWT_SECRET = os.environ.get("JWT_SECRET", "bwssb-dev-secret-key-32-chars-long-min!!")
if ENV == "production" and JWT_SECRET == "bwssb-dev-secret-key-32-chars-long-min!!":
    raise RuntimeError("CRITICAL CYBERSECURITY FAILURE: Refusing to start in production mode with default JWT_SECRET!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

class UserLoginRequest(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=128)

class UserProfile(BaseModel):
    username: str
    role: str
    full_name: str
    created_at: str

def hash_password(password: str) -> str:
    if HAS_BCRYPT:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100_000)
    return f"pbkdf2:sha256:100000${salt}${dk.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if hashed_password.startswith("pbkdf2:"):
            parts = hashed_password.split("$")
            salt = parts[1]
            expected_hex = parts[2]
            dk = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), 100_000)
            return hmac.compare_digest(dk.hex(), expected_hex)
        elif HAS_BCRYPT:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        return False
    except Exception:
        return False

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def _b64url_decode(s: str) -> bytes:
    s += '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)

def _jwt_encode(payload: dict) -> str:
    if HAS_JOSE:
        return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
    header = {"alg": "HS256", "typ": "JWT"}
    h_bytes = _b64url_encode(json.dumps(header).encode('utf-8'))
    p_bytes = _b64url_encode(json.dumps(payload, default=str).encode('utf-8'))
    signing_input = f"{h_bytes}.{p_bytes}".encode('utf-8')
    sig = _b64url_encode(hmac.new(JWT_SECRET.encode('utf-8'), signing_input, hashlib.sha256).digest())
    return f"{h_bytes}.{p_bytes}.{sig}"

def _jwt_decode(token: str) -> dict:
    if HAS_JOSE:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    parts = token.split('.')
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Malformed JWT")
    h_bytes, p_bytes, sig = parts
    signing_input = f"{h_bytes}.{p_bytes}".encode('utf-8')
    expected_sig = _b64url_encode(hmac.new(JWT_SECRET.encode('utf-8'), signing_input, hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=401, detail="Invalid token signature")
    payload = json.loads(_b64url_decode(p_bytes).decode('utf-8'))
    exp = payload.get("exp")
    if exp:
        exp_ts = exp if isinstance(exp, (int, float)) else datetime.fromisoformat(str(exp)).timestamp()
        if time.time() > exp_ts:
            raise HTTPException(status_code=401, detail="Session expired")
    return payload

def init_security_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                full_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        # Seed initial admin if empty
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            admin_user = os.environ.get("ADMIN_USERNAME", "admin")
            admin_pass = os.environ.get("ADMIN_PASSWORD", "Bwssb@2026!Admin")
            pwd_hash = hash_password(admin_pass)
            cur.execute("""
                INSERT INTO users (username, password_hash, role, full_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (admin_user, pwd_hash, "admin", "System Administrator", datetime.utcnow().isoformat()))

            # Also seed operator and viewer for test workflows
            op_hash = hash_password("Operator@2026!")
            cur.execute("""
                INSERT INTO users (username, password_hash, role, full_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("operator", op_hash, "operator", "SCADA Operator", datetime.utcnow().isoformat()))

            vw_hash = hash_password("Viewer@2026!")
            cur.execute("""
                INSERT INTO users (username, password_hash, role, full_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("viewer", vw_hash, "viewer", "Auditor Viewer", datetime.utcnow().isoformat()))
            conn.commit()
            logger.info("Seeded initial users: admin, operator, viewer.")

init_security_db()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        return dict(row) if row else None

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire.timestamp(), "type": "access"})
    return _jwt_encode(to_encode)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire.timestamp(), "type": "refresh"})
    return _jwt_encode(to_encode)

async def get_current_user(request: Request) -> Dict[str, Any]:
    # Check HttpOnly cookie first, then fallback to Authorization header
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        # Default anonymous read-only access for existing dev/GIS views if auth is soft,
        # but for protected routes require_role will reject
        return {"username": "anonymous", "role": "viewer"}

    try:
        payload = _jwt_decode(token)
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid session token")
    except Exception as ex:
        if isinstance(ex, HTTPException):
            raise ex
        raise HTTPException(status_code=401, detail="Session expired or invalid signature")

    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="User account not found")
    return user

def require_role(allowed_roles: List[str]):
    async def role_checker(user: Dict[str, Any] = Depends(get_current_user)):
        role = user.get("role", "viewer")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Insufficient privileges. Required role in {allowed_roles}, your role is '{role}'."
            )
        return user
    return role_checker
