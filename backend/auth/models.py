"""Data models for PayShield AI User, Identity, and Session management."""

from dataclasses import dataclass, field
from typing import List, Optional
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class User:
    id: str
    primary_email: str
    full_name: str
    avatar_url: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class AuthIdentity:
    id: str
    user_id: str
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool
    linked_at: str = ""
    last_login_at: str = ""


@dataclass(frozen=True)
class UserSession:
    session_id: str
    user_id: str
    expires_at: str
    created_at: str = ""
    revoked_at: Optional[str] = None
    user_agent: str = ""
    ip_address: str = ""


class IdentityPublic(BaseModel):
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool
    linked_at: str
    last_login_at: str


class UserPublicProfile(BaseModel):
    id: str
    primary_email: str
    full_name: str
    avatar_url: str
    identities: List[IdentityPublic] = Field(default_factory=list)


class OAuthInitResponse(BaseModel):
    authorization_url: str
    state: str
    provider: str


class EmailAuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(EmailAuthRequest):
    name: str = Field(min_length=1, max_length=120)
    confirm_password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=1, max_length=128)
