"""Comprehensive unit tests for PayShield AI Authentication Core, Database, and OIDC."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
import pytest

from backend.auth.db import AuthDatabase
from backend.auth.models import User
from backend.auth.oidc import (
    GoogleOIDCClient,
    OIDCAuthenticationError,
    OIDCConfigurationError,
    PayPalIdentityClient,
    PayPalIdentityUnavailableError,
)
from backend.auth.security import (
    AccountConflictError,
    UnverifiedEmailError,
    generate_oauth_state,
    generate_pkce_pair,
    generate_secure_token,
    get_cookie_settings,
    get_session_expiry_iso,
    hash_token,
    resolve_or_create_user,
)


@pytest.fixture
def auth_db(tmp_path):
    db_file = tmp_path / "test_auth.sqlite3"
    return AuthDatabase(str(db_file))


# =====================================================================
# Database & User Management Tests
# =====================================================================

def test_user_creation_and_retrieval(auth_db):
    user = auth_db.create_user(
        primary_email="alice@example.com",
        full_name="Alice Smith",
        avatar_url="https://example.com/avatar.png",
    )

    assert user.id
    assert user.primary_email == "alice@example.com"
    assert user.full_name == "Alice Smith"

    by_id = auth_db.get_user_by_id(user.id)
    assert by_id is not None
    assert by_id.primary_email == "alice@example.com"

    by_email = auth_db.get_user_by_email("alice@example.com")
    assert by_email is not None
    assert by_email.id == user.id

    assert auth_db.get_user_by_email("nonexistent@example.com") is None


def test_identity_creation_and_unlinking_rules(auth_db):
    user = auth_db.create_user("bob@example.com", "Bob Jones")
    identity1 = auth_db.create_identity(
        user_id=user.id,
        provider="google",
        provider_user_id="google-bob-123",
        email="bob@example.com",
        email_verified=True,
    )

    assert identity1.user_id == user.id
    identities = auth_db.get_identities_for_user(user.id)
    assert len(identities) == 1

    # Cannot unlink sole identity
    with pytest.raises(ValueError, match="Cannot unlink the only active authentication method"):
        auth_db.unlink_identity(user.id, "google")

    # Add second identity (PayPal)
    identity2 = auth_db.create_identity(
        user_id=user.id,
        provider="paypal",
        provider_user_id="paypal-bob-456",
        email="bob.paypal@example.com",
        email_verified=True,
    )

    identities_after = auth_db.get_identities_for_user(user.id)
    assert len(identities_after) == 2

    # Now unlinking PayPal succeeds
    assert auth_db.unlink_identity(user.id, "paypal") is True
    assert len(auth_db.get_identities_for_user(user.id)) == 1


def test_session_lifecycle_and_invalidation(auth_db):
    user = auth_db.create_user("charlie@example.com", "Charlie Brown")
    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    future_expiry = get_session_expiry_iso(days=1)

    session = auth_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=future_expiry,
        user_agent="PyTestClient",
        ip_address="127.0.0.1",
    )

    assert session.session_id
    assert session.user_id == user.id

    valid_session = auth_db.get_valid_session(token_hash)
    assert valid_session is not None
    assert valid_session.session_id == session.session_id

    # Revoke session
    assert auth_db.revoke_session(session.session_id) is True
    assert auth_db.get_valid_session(token_hash) is None


def test_expired_session_is_rejected(auth_db):
    user = auth_db.create_user("expired@example.com", "Expired User")
    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    past_expiry = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    auth_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=past_expiry,
    )

    assert auth_db.get_valid_session(token_hash) is None


def test_oauth_state_atomicity_and_single_use(auth_db):
    state = generate_oauth_state()
    verifier, _ = generate_pkce_pair()
    future = get_session_expiry_iso(days=1)

    auth_db.save_oauth_state(
        state=state,
        provider="google",
        code_verifier=verifier,
        redirect_uri="http://localhost:8000/callback",
        expires_at=future,
    )

    # First fetch succeeds and deletes state
    consumed = auth_db.get_and_consume_oauth_state(state)
    assert consumed is not None
    assert consumed["provider"] == "google"
    assert consumed["code_verifier"] == verifier

    # Second fetch returns None (replay prevented)
    replay = auth_db.get_and_consume_oauth_state(state)
    assert replay is None


# =====================================================================
# Security & Account Linking Policy Tests
# =====================================================================

def test_pkce_pair_generation():
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    assert verifier != challenge
    # Base64url characters only
    assert all(c.isalnum() or c in "-._~" for c in verifier)


def test_resolve_or_create_new_user(auth_db):
    user, identity, is_new = resolve_or_create_user(
        auth_db=auth_db,
        provider="google",
        provider_user_id="google-sub-001",
        email="newuser@example.com",
        email_verified=True,
        full_name="New User",
        avatar_url="https://avatar.url",
    )

    assert is_new is True
    assert user.primary_email == "newuser@example.com"
    assert identity.provider == "google"
    assert identity.provider_user_id == "google-sub-001"


def test_resolve_existing_user_login(auth_db):
    # First login (signup)
    user1, identity1, is_new1 = resolve_or_create_user(
        auth_db=auth_db,
        provider="google",
        provider_user_id="google-sub-002",
        email="returning@example.com",
        email_verified=True,
        full_name="Returning User",
    )
    assert is_new1 is True

    # Subsequent login with same provider
    user2, identity2, is_new2 = resolve_or_create_user(
        auth_db=auth_db,
        provider="google",
        provider_user_id="google-sub-002",
        email="returning@example.com",
        email_verified=True,
        full_name="Returning User",
    )
    assert is_new2 is False
    assert user2.id == user1.id
    assert identity2.id == identity1.id


def test_unauthenticated_email_collision_prevents_hijacking(auth_db):
    # User signs up with Google
    auth_db.create_user("victim@example.com", "Victim")
    auth_db.create_identity(
        user_id=auth_db.get_user_by_email("victim@example.com").id,
        provider="google",
        provider_user_id="google-victim-123",
        email="victim@example.com",
        email_verified=True,
    )

    # An unauthenticated login arrives via PayPal with the same email
    with pytest.raises(AccountConflictError, match="already exists"):
        resolve_or_create_user(
            auth_db=auth_db,
            provider="paypal",
            provider_user_id="paypal-attacker-999",
            email="victim@example.com",
            email_verified=True,
            full_name="Attacker",
            current_user_id=None,
        )


def test_authenticated_linking_success(auth_db):
    # User is logged in
    user = auth_db.create_user("owner@example.com", "Owner")
    auth_db.create_identity(
        user_id=user.id,
        provider="google",
        provider_user_id="google-owner-1",
        email="owner@example.com",
        email_verified=True,
    )

    # User explicitly links PayPal while authenticated
    linked_user, new_identity, is_new = resolve_or_create_user(
        auth_db=auth_db,
        provider="paypal",
        provider_user_id="paypal-owner-1",
        email="owner@example.com",
        email_verified=True,
        full_name="Owner",
        current_user_id=user.id,
    )

    assert is_new is False
    assert linked_user.id == user.id
    assert new_identity.provider == "paypal"
    assert len(auth_db.get_identities_for_user(user.id)) == 2


def test_authenticated_linking_fails_on_unverified_email(auth_db):
    user = auth_db.create_user("user@example.com", "User")

    with pytest.raises(UnverifiedEmailError, match="email is not verified"):
        resolve_or_create_user(
            auth_db=auth_db,
            provider="paypal",
            provider_user_id="paypal-unverified-1",
            email="user@example.com",
            email_verified=False,
            full_name="User",
            current_user_id=user.id,
        )


# =====================================================================
# OIDC Client Tests (Google & PayPal)
# =====================================================================

def test_google_oidc_auth_url():
    client = GoogleOIDCClient(
        client_id="test-google-id",
        client_secret="test-google-secret",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )
    assert client.is_configured() is True
    url = client.get_authorization_url(state="state-123", code_challenge="challenge-123")
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert "client_id=test-google-id" in url
    assert "state=state-123" in url
    assert "code_challenge=challenge-123" in url


def test_google_oidc_exchange_success():
    client = GoogleOIDCClient(
        client_id="test-google-id",
        client_secret="test-google-secret",
    )

    mock_token_resp = Mock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "google-mock-access-token"}

    mock_user_resp = Mock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {
        "sub": "google-sub-12345",
        "email": "googleuser@example.com",
        "email_verified": True,
        "name": "Google User",
        "picture": "https://lh3.googleusercontent.com/photo.jpg",
    }

    with patch("backend.auth.oidc.requests.post", return_value=mock_token_resp), \
         patch("backend.auth.oidc.requests.get", return_value=mock_user_resp):
        claims = client.exchange_code_for_user(code="auth-code-123", code_verifier="verifier-123")

    assert claims.provider == "google"
    assert claims.provider_user_id == "google-sub-12345"
    assert claims.email == "googleuser@example.com"
    assert claims.email_verified is True
    assert claims.full_name == "Google User"


def test_paypal_identity_unconfigured_raises_error():
    client = PayPalIdentityClient(client_id="", client_secret="")
    assert client.is_configured() is False
    with pytest.raises(OIDCConfigurationError):
        client.get_authorization_url(state="state-123", code_challenge="challenge-123")


def test_paypal_identity_auth_url():
    client = PayPalIdentityClient(
        client_id="test-paypal-id",
        client_secret="test-paypal-secret",
        base_url="https://api-m.sandbox.paypal.com",
        redirect_uri="http://localhost:8000/auth/paypal/callback",
    )
    assert client.is_configured() is True
    url = client.get_authorization_url(state="state-123", code_challenge="challenge-123")
    assert "https://www.sandbox.paypal.com/signin/authorize" in url
    assert "client_id=test-paypal-id" in url
    assert "scope=openid+profile+email" in url


def test_paypal_identity_unavailable_raises_clear_error():
    client = PayPalIdentityClient(
        client_id="test-paypal-id",
        client_secret="test-paypal-secret",
        base_url="https://api-m.sandbox.paypal.com",
    )

    mock_token_resp = Mock()
    mock_token_resp.status_code = 401
    mock_token_resp.text = "Unauthorized"

    with patch("backend.auth.oidc.requests.post", return_value=mock_token_resp):
        with pytest.raises(PayPalIdentityUnavailableError, match="Log in with PayPal"):
            client.exchange_code_for_user(code="auth-code", code_verifier="verifier")

