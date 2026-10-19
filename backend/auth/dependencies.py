"""FastAPI dependencies for PayShield AI authentication and database access."""

import os
from typing import Optional
from fastapi import Cookie, Depends, HTTPException, Request

from backend.audit.audit_logger import AuditLogger
from backend.auth.db import AuthDatabase
from backend.auth.models import User
from backend.auth.security import SESSION_COOKIE_NAME, hash_token


_auth_db_instance: Optional[AuthDatabase] = None


def get_auth_db() -> AuthDatabase:
    """Dependency returning the shared AuthDatabase instance."""
    global _auth_db_instance
    if _auth_db_instance is None:
        db_path = os.getenv("PAYSHIELD_DB_PATH", "payshield_payments.sqlite3")
        _auth_db_instance = AuthDatabase(db_path)
    return _auth_db_instance


def get_audit_logger() -> AuditLogger:
    """Dependency returning the AuditLogger instance."""
    return AuditLogger()


def get_optional_current_user(
    request: Request,
    auth_db: AuthDatabase = Depends(get_auth_db),
) -> Optional[User]:
    """Return the currently authenticated User if a valid session cookie is present."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        # Also check Authorization: Bearer <token> fallback
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    token_hash = hash_token(token)
    session = auth_db.get_valid_session(token_hash)
    if not session:
        return None

    return auth_db.get_user_by_id(session.user_id)


def get_current_user(
    user: Optional[User] = Depends(get_optional_current_user),
) -> User:
    """Require an authenticated user; raises HTTP 401 Unauthorized otherwise."""
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in.",
        )
    return user

