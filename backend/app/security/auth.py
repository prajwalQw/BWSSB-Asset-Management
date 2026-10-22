"""
Baseline Cybersecurity: Authentication & Role-Based Access Control (RBAC).
Roles: viewer (read), operator (acknowledge alerts, run simulations), admin (config, user management).
Tokens: Short-lived JWT stored in HttpOnly, Secure, SameSite=Strict cookies.
Passwords: Salted & hashed using bcrypt.
"""

import os
import time
import secrets
import bcrypt
import sqlite3
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer
from jose import jwt, JWTError
from pydantic import BaseModel, Field

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
            salt = bcrypt.gensalt(rounds=12)
            pwd_hash = bcrypt.hashpw(admin_pass.encode("utf-8"), salt).decode("utf-8")
            cur.execute("""
                INSERT INTO users (username, password_hash, role, full_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (admin_user, pwd_hash, "admin", "System Administrator", datetime.utcnow().isoformat()))

            # Also seed operator and viewer for test workflows
            op_hash = bcrypt.hashpw(b"Operator@2026!", salt).decode("utf-8")
            cur.execute("""
                INSERT INTO users (username, password_hash, role, full_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("operator", op_hash, "operator", "SCADA Operator", datetime.utcnow().isoformat()))

            vw_hash = bcrypt.hashpw(b"Viewer@2026!", salt).decode("utf-8")
            cur.execute("""
                INSERT INTO users (username, password_hash, role, full_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("viewer", vw_hash, "viewer", "Auditor Viewer", datetime.utcnow().isoformat()))
            conn.commit()
            logger.info("Seeded initial users: admin, operator, viewer.")

init_security_db()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

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
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

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
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid session token")
    except JWTError:
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
