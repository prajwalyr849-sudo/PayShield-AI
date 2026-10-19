"""Endpoint and router logic tests for PayShield AI authentication."""

from unittest.mock import Mock, patch
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from backend.audit.audit_logger import AuditLogger
from backend.auth.db import AuthDatabase
from backend.auth.dependencies import get_current_user, get_optional_current_user
from backend.auth.oidc import OIDCUserClaims
from backend.auth.router import (
    demo_login,
    get_current_user_profile,
    logout,
    oauth_callback,
    oauth_login,
    unlink_provider_identity,
)
from backend.auth.security import (
    SESSION_COOKIE_NAME,
    generate_secure_token,
    get_session_expiry_iso,
    hash_token,
)


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "router_test.sqlite3"
    return AuthDatabase(str(db_file))


@pytest.fixture
def test_audit(tmp_path):
    log_file = tmp_path / "router_audit.jsonl"
    return AuditLogger(str(log_file))


def make_request(headers=None, cookies=None, query_string=""):
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin1"), v.encode("latin1")))
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode("latin1")))

    scope = {
        "type": "http",
        "method": "GET",
        "headers": raw_headers,
        "query_string": query_string.encode("latin1"),
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_oauth_login_initiation(test_db, test_audit, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-secret")

    res = oauth_login(
        provider="google",
        link=False,
        current_user=None,
        auth_db=test_db,
        audit_logger=test_audit,
    )

    assert res.provider == "google"
    assert res.state
    assert "https://accounts.google.com/o/oauth2/v2/auth" in res.authorization_url


def test_unsupported_provider_login(test_db, test_audit):
    with pytest.raises(HTTPException) as exc:
        oauth_login(
            provider="unsupported",
            link=False,
            current_user=None,
            auth_db=test_db,
            audit_logger=test_audit,
        )
    assert exc.value.status_code == 400


def test_callback_with_provider_error(test_db, test_audit):
    req = make_request()
    res = oauth_callback(
        provider="google",
        request=req,
        error="access_denied",
        error_description="User denied authorization",
        auth_db=test_db,
        audit_logger=test_audit,
        current_user=None,
    )

    assert res.status_code == 307
    assert "/login?error=" in res.headers["location"]


def test_callback_with_invalid_state_triggers_csrf_defense(test_db, test_audit):
    req = make_request()
    res = oauth_callback(
        provider="google",
        request=req,
        code="sample-code",
        state="forged-or-expired-state",
        auth_db=test_db,
        audit_logger=test_audit,
        current_user=None,
    )

    assert res.status_code == 307
    assert "expired" in res.headers["location"].lower() or "error" in res.headers["location"]


def test_callback_successful_login_and_cookie_issuance(test_db, test_audit, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-secret")

    # Step 1: Initialize login
    init_res = oauth_login(
        provider="google",
        link=False,
        current_user=None,
        auth_db=test_db,
        audit_logger=test_audit,
    )
    state = init_res.state

    mock_claims = OIDCUserClaims(
        provider="google",
        provider_user_id="google-sub-999",
        email="testpilot@example.com",
        email_verified=True,
        full_name="Test Pilot",
        avatar_url="https://avatar.test/photo.jpg",
    )

    req = make_request()

    # Step 2: Callback with valid state
    with patch(
        "backend.auth.oidc.GoogleOIDCClient.exchange_code_for_user",
        return_value=mock_claims,
    ):
        cb_res = oauth_callback(
            provider="google",
            request=req,
            code="auth-code-valid",
            state=state,
            auth_db=test_db,
            audit_logger=test_audit,
            current_user=None,
        )

    assert cb_res.status_code == 303
    assert "/?login_success=1" in cb_res.headers["location"]
    set_cookie_headers = cb_res.headers.getlist("set-cookie")
    assert any(SESSION_COOKIE_NAME in h for h in set_cookie_headers)


def test_get_current_user_dependency_unauthorized(test_db):
    req = make_request()
    user = get_optional_current_user(req, auth_db=test_db)
    assert user is None

    with pytest.raises(HTTPException) as exc:
        get_current_user(user)
    assert exc.value.status_code == 401


def test_get_current_user_dependency_authorized(test_db):
    user = test_db.create_user("sam@example.com", "Sam Vance")
    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    test_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=get_session_expiry_iso(days=1),
    )

    req = make_request(cookies={SESSION_COOKIE_NAME: raw_token})
    resolved_user = get_optional_current_user(req, auth_db=test_db)
    assert resolved_user is not None
    assert resolved_user.id == user.id

    guarded_user = get_current_user(resolved_user)
    assert guarded_user.id == user.id


def test_get_current_user_profile(test_db):
    user = test_db.create_user("profile@example.com", "Profile User")
    test_db.create_identity(
        user_id=user.id,
        provider="google",
        provider_user_id="google-profile-1",
        email="profile@example.com",
        email_verified=True,
    )

    profile = get_current_user_profile(user=user, auth_db=test_db)
    assert profile.primary_email == "profile@example.com"
    assert profile.full_name == "Profile User"
    assert len(profile.identities) == 1
    assert profile.identities[0].provider == "google"


def test_logout_revokes_session(test_db, test_audit):
    user = test_db.create_user("logout@example.com", "Logout User")
    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    session = test_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=get_session_expiry_iso(days=1),
    )

    req = make_request(cookies={SESSION_COOKIE_NAME: raw_token})
    res = Response()
    result = logout(
        request=req,
        response=res,
        auth_db=test_db,
        audit_logger=test_audit,
        current_user=user,
    )

    assert result["status"] == "logged_out"
    assert test_db.get_valid_session(token_hash) is None


def test_unlink_sole_identity_rejected(test_db, test_audit):
    user = test_db.create_user("unlink@example.com", "Unlink User")
    test_db.create_identity(
        user_id=user.id,
        provider="google",
        provider_user_id="google-unlink-1",
        email="unlink@example.com",
        email_verified=True,
    )

    with pytest.raises(HTTPException) as exc:
        unlink_provider_identity(
            provider="google",
            user=user,
            auth_db=test_db,
            audit_logger=test_audit,
        )
    assert exc.value.status_code == 400
    assert "Cannot unlink the only active authentication method" in exc.value.detail


def test_demo_login_creates_session_and_identities(test_db, test_audit):
    res = Response()
    profile = demo_login(response=res, auth_db=test_db, audit_logger=test_audit)

    assert profile.primary_email == "alex@payshield.ai"
    assert profile.full_name == "Alex Smith"
    providers = {i.provider for i in profile.identities}
    assert "google" in providers
    assert "paypal" in providers
    assert SESSION_COOKIE_NAME in res.headers.get("set-cookie", "")


def test_demo_login_disabled(test_db, test_audit, monkeypatch):
    monkeypatch.setenv("PAYSHIELD_ALLOW_DEMO_LOGIN", "false")
    res = Response()
    with pytest.raises(HTTPException) as exc:
        demo_login(response=res, auth_db=test_db, audit_logger=test_audit)
    assert exc.value.status_code == 403

