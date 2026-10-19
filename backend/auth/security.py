"""Security utilities for PKCE, token hashing, session management, and safe account linking."""

import base64
import hashlib
import os
import secrets
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from backend.auth.db import AuthDatabase
from backend.auth.models import AuthIdentity, User


SESSION_COOKIE_NAME = "payshield_session"
DEFAULT_SESSION_DURATION_DAYS = 7
PASSWORD_HASHER = PasswordHasher()
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")


class AccountConflictError(ValueError):
    """Raised when an incoming login conflicts with an existing unlinked account."""
    pass


class UnverifiedEmailError(ValueError):
    """Raised when a provider presents an unverified email address for linking."""
    pass


def generate_secure_token(nbytes: int = 48) -> str:
    """Generate a cryptographically random URL-safe token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Produce a SHA-256 hash of a session token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    clean = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(clean) or clean.count("@") != 1:
        raise ValueError("Enter a valid email address.")
    return clean


def validate_password(password: str) -> str:
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Password must be between 12 and 128 characters.")
    if not any(char.isupper() for char in password):
        raise ValueError("Password must include an uppercase letter.")
    if not any(char.islower() for char in password):
        raise ValueError("Password must include a lowercase letter.")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must include a number.")
    return password


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(validate_password(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def generate_pkce_pair() -> Tuple[str, str]:
    """
    Generate PKCE code_verifier and code_challenge (S256).
    RFC 7636 compliant.
    """
    verifier_bytes = secrets.token_bytes(32)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).decode("utf-8").rstrip("=")

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def generate_oauth_state() -> str:
    """Generate a high-entropy state token to prevent CSRF attacks."""
    return secrets.token_urlsafe(32)


def get_session_expiry_iso(days: int = DEFAULT_SESSION_DURATION_DAYS) -> str:
    """Return ISO-8601 timestamp for session expiry."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def get_cookie_settings() -> dict:
    """Return standard secure cookie settings for session headers."""
    secure_env = os.getenv("PAYSHIELD_COOKIE_SECURE", "false").lower() in ("true", "1", "yes")
    max_age = int(
        os.getenv(
            "PAYSHIELD_SESSION_MAX_AGE_SECONDS",
            str(DEFAULT_SESSION_DURATION_DAYS * 86400),
        )
    )
    return {
        "httponly": True,
        "secure": secure_env,
        "samesite": "lax",
        "max_age": max_age,
        "path": "/",
    }


def resolve_or_create_user(
    auth_db: AuthDatabase,
    provider: str,
    provider_user_id: str,
    email: str,
    email_verified: bool,
    full_name: str,
    avatar_url: str = "",
    current_user_id: Optional[str] = None,
) -> Tuple[User, AuthIdentity, bool]:
    """
    Safely resolve, link, or register a user from validated identity claims.

    Returns:
        (User, AuthIdentity, is_new_user)

    Rules:
        1. If user is authenticated (current_user_id), perform explicit account linking:
           - Requires email_verified = True.
           - Rejects if this identity is already bound to another user.
        2. If user is unauthenticated:
           - Match existing identity (provider, provider_user_id).
           - If no identity matches, but email matches an existing user:
             Strictly reject automatic linking to prevent pre-hijacking/account takeover.
           - If brand new: create User and AuthIdentity.
    """
    clean_provider = provider.lower().strip()
    clean_provider_id = provider_user_id.strip()
    clean_email = email.lower().strip()

    # Rule 1: Explicit Account Linking from Authenticated Session
    if current_user_id:
        if not email_verified:
            raise UnverifiedEmailError(
                f"Cannot link {clean_provider.title()} account: email is not verified by provider."
            )

        existing_identity = auth_db.get_identity(clean_provider, clean_provider_id)
        if existing_identity:
            if existing_identity.user_id != current_user_id:
                raise AccountConflictError(
                    f"This {clean_provider.title()} account is already connected to another PayShield account."
                )
            user = auth_db.get_user_by_id(current_user_id)
            if not user:
                raise ValueError("Current user session is invalid.")
            auth_db.update_identity_last_login(existing_identity.id)
            return user, existing_identity, False

        # Link identity to current authenticated user
        user = auth_db.get_user_by_id(current_user_id)
        if not user:
            raise ValueError("Current user session is invalid.")

        identity = auth_db.create_identity(
            user_id=current_user_id,
            provider=clean_provider,
            provider_user_id=clean_provider_id,
            email=clean_email,
            email_verified=email_verified,
        )
        return user, identity, False

    # Rule 2: Unauthenticated Sign In or Sign Up
    existing_identity = auth_db.get_identity(clean_provider, clean_provider_id)
    if existing_identity:
        user = auth_db.get_user_by_id(existing_identity.user_id)
        if not user:
            raise ValueError("Linked user account not found.")
        auth_db.update_identity_last_login(existing_identity.id)
        return user, existing_identity, False

    # Check for email collision across different providers
    existing_user_by_email = auth_db.get_user_by_email(clean_email)
    if existing_user_by_email:
        raise AccountConflictError(
            f"An account with email '{clean_email}' already exists. "
            "To prevent unauthorized access, sign in with your original provider and "
            "link this service from Account Settings."
        )

    # Brand new user registration
    user = auth_db.create_user(
        primary_email=clean_email,
        full_name=full_name or clean_email.split("@")[0].title(),
        avatar_url=avatar_url,
    )
    identity = auth_db.create_identity(
        user_id=user.id,
        provider=clean_provider,
        provider_user_id=clean_provider_id,
        email=clean_email,
        email_verified=email_verified,
    )
    return user, identity, True
