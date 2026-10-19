"""Database persistence layer for PayShield AI authentication and identity."""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from backend.auth.models import AuthIdentity, User, UserSession


class AuthDatabase:
    """Manages users, linked identities, sessions, and OAuth states in SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(
            db_path or os.getenv("PAYSHIELD_DB_PATH", "payshield_payments.sqlite3")
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_tables(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    primary_email TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    avatar_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            if "password_hash" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS auth_identities (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    linked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    last_login_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    UNIQUE(provider, provider_user_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    revoked_at TEXT,
                    user_agent TEXT NOT NULL DEFAULT '',
                    ip_address TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    code_verifier TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)

            # Fast index on session token hash
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_token_hash
                ON user_sessions(token_hash)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    preferences_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

    def create_user(
        self,
        primary_email: str,
        full_name: str,
        avatar_url: str = "",
        user_id: Optional[str] = None,
    ) -> User:
        user_id = user_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, primary_email, full_name, avatar_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, primary_email.lower().strip(), full_name.strip(), avatar_url.strip(), now, now),
            )
        return User(
            id=user_id,
            primary_email=primary_email.lower().strip(),
            full_name=full_name.strip(),
            avatar_url=avatar_url.strip(),
            created_at=now,
            updated_at=now,
        )

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, primary_email, full_name, avatar_url, created_at, updated_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return User(
            id=row[0],
            primary_email=row[1],
            full_name=row[2],
            avatar_url=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, primary_email, full_name, avatar_url, created_at, updated_at FROM users WHERE primary_email = ?",
                (email.lower().strip(),),
            ).fetchone()
        if not row:
            return None
        return User(
            id=row[0],
            primary_email=row[1],
            full_name=row[2],
            avatar_url=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                         (password_hash, datetime.now(timezone.utc).isoformat(), user_id))

    def get_password_hash(self, user_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        return row[0] if row else None

    def create_password_identity(self, user_id: str, email: str) -> AuthIdentity:
        existing = self.get_identity("password", email)
        if existing:
            return existing
        return self.create_identity(user_id, "password", email, email, True)

    def save_password_reset_token(self, token_hash: str, user_id: str, expires_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at),
            )

    def consume_password_reset_token(self, token_hash: str) -> Optional[str]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM password_reset_tokens WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
                (token_hash, now),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ? AND used_at IS NULL",
                (now, token_hash),
            )
            return row[0]

    def create_identity(
        self,
        user_id: str,
        provider: str,
        provider_user_id: str,
        email: str,
        email_verified: bool,
    ) -> AuthIdentity:
        identity_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_identities (
                    id, user_id, provider, provider_user_id, email, email_verified, linked_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity_id,
                    user_id,
                    provider.lower().strip(),
                    provider_user_id.strip(),
                    email.lower().strip(),
                    1 if email_verified else 0,
                    now,
                    now,
                ),
            )
        return AuthIdentity(
            id=identity_id,
            user_id=user_id,
            provider=provider.lower().strip(),
            provider_user_id=provider_user_id.strip(),
            email=email.lower().strip(),
            email_verified=email_verified,
            linked_at=now,
            last_login_at=now,
        )

    def get_identity(self, provider: str, provider_user_id: str) -> Optional[AuthIdentity]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, provider, provider_user_id, email, email_verified, linked_at, last_login_at
                FROM auth_identities
                WHERE provider = ? AND provider_user_id = ?
                """,
                (provider.lower().strip(), provider_user_id.strip()),
            ).fetchone()
        if not row:
            return None
        return AuthIdentity(
            id=row[0],
            user_id=row[1],
            provider=row[2],
            provider_user_id=row[3],
            email=row[4],
            email_verified=bool(row[5]),
            linked_at=row[6],
            last_login_at=row[7],
        )

    def get_identities_for_user(self, user_id: str) -> List[AuthIdentity]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, provider, provider_user_id, email, email_verified, linked_at, last_login_at
                FROM auth_identities
                WHERE user_id = ?
                ORDER BY linked_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [
            AuthIdentity(
                id=r[0],
                user_id=r[1],
                provider=r[2],
                provider_user_id=r[3],
                email=r[4],
                email_verified=bool(r[5]),
                linked_at=r[6],
                last_login_at=r[7],
            )
            for r in rows
        ]

    def update_identity_last_login(self, identity_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE auth_identities SET last_login_at = ? WHERE id = ?",
                (now, identity_id),
            )

    def unlink_identity(self, user_id: str, provider: str) -> bool:
        """Unlink an identity only if the user has more than one identity connected."""
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM auth_identities WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
            if count <= 1:
                raise ValueError("Cannot unlink the only active authentication method.")

            cursor = conn.execute(
                "DELETE FROM auth_identities WHERE user_id = ? AND provider = ?",
                (user_id, provider.lower().strip()),
            )
            return cursor.rowcount > 0

    def create_session(
        self,
        user_id: str,
        token_hash: str,
        expires_at: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> UserSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_sessions (
                    session_id, user_id, token_hash, expires_at, created_at, user_agent, ip_address
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, token_hash, expires_at, now, user_agent, ip_address),
            )
        return UserSession(
            session_id=session_id,
            user_id=user_id,
            expires_at=expires_at,
            created_at=now,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    def get_valid_session(self, token_hash: str) -> Optional[UserSession]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, user_id, expires_at, created_at, revoked_at, user_agent, ip_address
                FROM user_sessions
                WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
        if not row:
            return None
        return UserSession(
            session_id=row[0],
            user_id=row[1],
            expires_at=row[2],
            created_at=row[3],
            revoked_at=row[4],
            user_agent=row[5],
            ip_address=row[6],
        )

    def revoke_session(self, session_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE user_sessions SET revoked_at = ? WHERE session_id = ? AND revoked_at IS NULL",
                (now, session_id),
            )
            return cursor.rowcount > 0

    def revoke_all_user_sessions(self, user_id: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE user_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            return cursor.rowcount

    def save_oauth_state(
        self,
        state: str,
        provider: str,
        code_verifier: str,
        redirect_uri: str,
        expires_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO oauth_states (
                    state, provider, code_verifier, redirect_uri, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (state, provider.lower().strip(), code_verifier, redirect_uri, expires_at),
            )

    def get_and_consume_oauth_state(self, state: str) -> Optional[dict]:
        """Atomically fetch and delete an OAuth state so it is strictly single-use."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT state, provider, code_verifier, redirect_uri, expires_at
                FROM oauth_states
                WHERE state = ? AND expires_at > ?
                """,
                (state, now),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            return {
                "state": row[0],
                "provider": row[1],
                "code_verifier": row[2],
                "redirect_uri": row[3],
                "expires_at": row[4],
            }

    def get_preferences(self, user_id: str) -> dict:
        """Return the user's persisted preference document (empty if unset)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT preferences_json FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row or not row[0]:
            return {}
        try:
            parsed = json.loads(row[0])
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def save_preferences(self, user_id: str, preferences: dict) -> dict:
        """Persist the user's preference document, replacing the previous value."""
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(preferences or {}, separators=(",", ":"), sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, preferences_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferences_json = excluded.preferences_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, payload, now),
            )
        return preferences or {}
