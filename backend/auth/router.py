"""FastAPI router for PayShield AI authentication, OAuth callbacks, and identity sessions."""

import os
import urllib.parse
import uuid
import smtplib
from email.message import EmailMessage
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from backend.audit.audit_logger import AuditLogger
from backend.auth.db import AuthDatabase
from backend.auth.dependencies import (
    get_audit_logger,
    get_auth_db,
    get_current_user,
    get_optional_current_user,
)
from backend.auth.models import (
    IdentityPublic,
    OAuthInitResponse,
    User,
    UserPublicProfile,
    EmailAuthRequest,
    RegisterRequest,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
)
from backend.auth.oidc import (
    GoogleOIDCClient,
    OIDCAuthenticationError,
    OIDCConfigurationError,
    PayPalIdentityClient,
    PayPalIdentityUnavailableError,
)
from backend.auth.security import (
    SESSION_COOKIE_NAME,
    AccountConflictError,
    UnverifiedEmailError,
    generate_oauth_state,
    generate_pkce_pair,
    generate_secure_token,
    get_cookie_settings,
    get_session_expiry_iso,
    hash_token,
    hash_password,
    normalize_email,
    validate_password,
    verify_password,
    resolve_or_create_user,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
_login_attempts = defaultdict(list)
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300
_DUMMY_PASSWORD_HASH = hash_password("DummyPassword123!")


def _get_frontend_url() -> str:
    return os.getenv("PAYSHIELD_FRONTEND_URL", "http://localhost:5173").rstrip("/")


def _get_oidc_client(provider: str):
    p = provider.lower().strip()
    if p == "google":
        return GoogleOIDCClient()
    if p == "paypal":
        return PayPalIdentityClient()
    raise HTTPException(status_code=400, detail=f"Unsupported identity provider: {provider}")


def _check_login_rate_limit(request: Request, email: str) -> None:
    now = datetime.now(timezone.utc).timestamp()
    key = f"{request.client.host if request.client else 'unknown'}:{email}"
    recent = [stamp for stamp in _login_attempts[key] if now - stamp < _LOGIN_WINDOW_SECONDS]
    if len(recent) >= _MAX_LOGIN_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")
    recent.append(now)
    _login_attempts[key] = recent


def _issue_session(request: Request, response: Response, user: User, auth_db: AuthDatabase) -> None:
    raw_token = generate_secure_token()
    auth_db.create_session(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=get_session_expiry_iso(),
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    response.set_cookie(key=SESSION_COOKIE_NAME, value=raw_token, **get_cookie_settings())


@router.post("/register", response_model=UserPublicProfile)
def register_email(
    request: Request,
    payload: RegisterRequest,
    response: Response,
    auth_db: AuthDatabase = Depends(get_auth_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")
    try:
        email = normalize_email(payload.email)
        validate_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if auth_db.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Unable to create account with these details.")
    try:
        user = auth_db.create_user(email, payload.name.strip())
        auth_db.set_password_hash(user.id, hash_password(payload.password))
        auth_db.create_password_identity(user.id, email)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Unable to create account with these details.") from exc
    _issue_session(request, response, user, auth_db)
    audit_logger.log_decision({"event_type": "AUTH_REGISTER_SUCCESS", "user_id": user.id})
    return get_current_user_profile(user=user, auth_db=auth_db)


@router.post("/login", response_model=UserPublicProfile)
def login_email(
    request: Request,
    payload: EmailAuthRequest,
    response: Response,
    auth_db: AuthDatabase = Depends(get_auth_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
):
    try:
        email = normalize_email(payload.email)
    except ValueError:
        email = payload.email.strip().lower()
    _check_login_rate_limit(request, email)
    user = auth_db.get_user_by_email(email)
    password_hash = auth_db.get_password_hash(user.id) if user else None
    valid = verify_password(password_hash, payload.password) if password_hash else verify_password(_DUMMY_PASSWORD_HASH, payload.password)
    if not user or not password_hash or not valid:
        audit_logger.log_decision({"event_type": "AUTH_LOGIN_FAILED", "reason": "Email authentication failed"})
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    _issue_session(request, response, user, auth_db)
    audit_logger.log_decision({"event_type": "AUTH_LOGIN_SUCCESS", "user_id": user.id})
    return get_current_user_profile(user=user, auth_db=auth_db)


@router.post("/password-reset/request")
def request_password_reset(
    payload: PasswordResetRequest,
    auth_db: AuthDatabase = Depends(get_auth_db),
):
    """Request reset without revealing whether an account exists."""
    try:
        email = normalize_email(payload.email)
    except ValueError:
        email = ""
    user = auth_db.get_user_by_email(email) if email else None
    smtp_host = os.getenv("PAYSHIELD_SMTP_HOST", "").strip()
    generic = "If an eligible account exists, a password reset message will be sent."
    if not user or not smtp_host:
        return {"status": "setup_required" if not smtp_host else "accepted", "message": generic}
    raw_token = generate_secure_token(32)
    auth_db.save_password_reset_token(
        hash_token(raw_token),
        user.id,
        (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    )
    message = EmailMessage()
    message["Subject"] = "PayShield AI password reset"
    message["From"] = os.getenv("PAYSHIELD_SMTP_FROM", "")
    message["To"] = email
    message.set_content(
        f"Use this password reset token in PayShield AI. It expires in 30 minutes:\n\n{raw_token}"
    )
    try:
        with smtplib.SMTP(smtp_host, int(os.getenv("PAYSHIELD_SMTP_PORT", "587")), timeout=10) as smtp:
            smtp.starttls()
            smtp.login(os.getenv("PAYSHIELD_SMTP_USER", ""), os.getenv("PAYSHIELD_SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except Exception:
        raise HTTPException(status_code=503, detail="Password reset email service is unavailable.")
    return {"status": "accepted", "message": generic}


@router.post("/password-reset/confirm")
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    response: Response,
    auth_db: AuthDatabase = Depends(get_auth_db),
):
    try:
        validate_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user_id = auth_db.consume_password_reset_token(hash_token(payload.token))
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token.")
    auth_db.set_password_hash(user_id, hash_password(payload.password))
    auth_db.revoke_all_user_sessions(user_id)
    return {"status": "password_updated"}


@router.post("/demo/login", response_model=UserPublicProfile)
def demo_login(
    response: Response,
    auth_db: AuthDatabase = Depends(get_auth_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
):
    """Sign in as a local demonstration administrator for test and evaluation environments."""
    if os.getenv("PAYSHIELD_ALLOW_DEMO_LOGIN", "true").lower() not in ("true", "1", "yes"):
        raise HTTPException(
            status_code=403,
            detail="Demo sign-in is disabled in this environment.",
        )

    user, _identity, _is_new = resolve_or_create_user(
        auth_db=auth_db,
        provider="google",
        provider_user_id="demo-admin-google-id",
        email="alex@payshield.ai",
        email_verified=True,
        full_name="Alex Smith",
        avatar_url="",
    )

    try:
        auth_db.create_identity(
            user_id=user.id,
            provider="paypal",
            provider_user_id="demo-admin-paypal-id",
            email="alex@payshield.ai",
            email_verified=True,
        )
    except Exception:
        pass

    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    expiry = get_session_expiry_iso(days=7)
    session = auth_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expiry,
        user_agent="PayShield-DemoClient",
        ip_address="127.0.0.1",
    )

    audit_logger.log_decision({
        "event_type": "AUTH_DEMO_LOGIN",
        "user_id": user.id,
        "session_id": session.session_id,
    })

    cookie_kwargs = get_cookie_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        **cookie_kwargs,
    )
    return get_current_user_profile(user=user, auth_db=auth_db)


@router.get("/{provider}/login", response_model=OAuthInitResponse)
def oauth_login(
    provider: str,
    link: bool = Query(default=False, description="Whether this login is intended to link to an active session"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    auth_db: AuthDatabase = Depends(get_auth_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
):
    """Initiate PKCE-secured OAuth 2.0 / OIDC flow for Google or PayPal."""
    provider_name = provider.lower().strip()
    client = _get_oidc_client(provider_name)

    if link and not current_user:
        raise HTTPException(
            status_code=401,
            detail="You must be logged in to connect a secondary identity.",
        )

    try:
        verifier, challenge = generate_pkce_pair()
        state = generate_oauth_state()

        # State token expires in 10 minutes
        expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        auth_db.save_oauth_state(
            state=state,
            provider=provider_name,
            code_verifier=verifier,
            redirect_uri=client.redirect_uri,
            expires_at=expiry,
        )

        auth_url = client.get_authorization_url(state=state, code_challenge=challenge)
        return OAuthInitResponse(
            authorization_url=auth_url,
            state=state,
            provider=provider_name,
        )
    except OIDCConfigurationError as exc:
        audit_logger.log_decision({
            "event_type": "AUTH_CONFIG_ERROR",
            "provider": provider_name,
            "reason": str(exc),
        })
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/providers/status")
def provider_status():
    """Expose provider readiness without returning credentials or secrets."""
    google = GoogleOIDCClient()
    paypal = PayPalIdentityClient()
    return {
        "google": {
            "configured": google.is_configured(),
            "redirect_uri": google.redirect_uri,
            "setup": (
                "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, then register "
                "the exact redirect URI in Google Cloud Console."
                if not google.is_configured()
                else "Configured"
            ),
        },
        "paypal": {
            "configured": paypal.is_configured(),
            "redirect_uri": paypal.redirect_uri,
            "setup": (
                "Create a separate PayPal app with Log in with PayPal enabled, "
                "openid/profile/email scopes, and set PAYPAL_IDENTITY_CLIENT_ID "
                "and PAYPAL_IDENTITY_CLIENT_SECRET."
                if not paypal.is_configured()
                else "Configured; provider-side Log in with PayPal must also be enabled."
            ),
        },
    }


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
    auth_db: AuthDatabase = Depends(get_auth_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Handle the OAuth 2.0 / OIDC callback, exchange code, and issue session."""
    frontend_url = _get_frontend_url()
    provider_name = provider.lower().strip()

    # Normalize parameters if invoked directly in tests
    code_str = code if isinstance(code, str) else None
    state_str = state if isinstance(state, str) else None
    error_str = error if isinstance(error, str) else None
    error_desc_str = error_description if isinstance(error_description, str) else None

    # Handle provider-reported errors
    if error_str:
        detail = error_desc_str or error_str
        audit_logger.log_decision({
            "event_type": "AUTH_LOGIN_FAILED",
            "provider": provider_name,
            "reason": f"Provider reported error: {detail}",
        })
        safe_param = urllib.parse.quote(f"{provider_name.title()} authentication failed: {detail}")
        return RedirectResponse(f"{frontend_url}/login?error={safe_param}")

    if not code_str or not state_str:
        audit_logger.log_decision({
            "event_type": "AUTH_LOGIN_FAILED",
            "provider": provider_name,
            "reason": "Missing code or state parameter",
        })
        safe_param = urllib.parse.quote("Missing required authentication callback parameters.")
        return RedirectResponse(f"{frontend_url}/login?error={safe_param}")

    # Validate and atomically consume state (single-use anti-CSRF)
    state_data = auth_db.get_and_consume_oauth_state(state_str)
    if not state_data or state_data["provider"] != provider_name:
        audit_logger.log_decision({
            "event_type": "AUTH_LOGIN_FAILED",
            "provider": provider_name,
            "reason": "Invalid or expired state token (CSRF defense triggered)",
        })
        safe_param = urllib.parse.quote("Authentication session expired or invalid. Please try again.")
        return RedirectResponse(f"{frontend_url}/login?error={safe_param}")

    client = _get_oidc_client(provider_name)

    # Exchange code for user identity claims
    try:
        claims = client.exchange_code_for_user(
            code=code_str,
            code_verifier=state_data["code_verifier"],
            redirect_uri=state_data["redirect_uri"],
        )
    except PayPalIdentityUnavailableError as exc:
        audit_logger.log_decision({
            "event_type": "AUTH_LOGIN_FAILED",
            "provider": "paypal",
            "reason": str(exc),
        })
        safe_param = urllib.parse.quote(str(exc))
        return RedirectResponse(f"{frontend_url}/login?error={safe_param}")
    except (OIDCAuthenticationError, OIDCConfigurationError) as exc:
        audit_logger.log_decision({
            "event_type": "AUTH_LOGIN_FAILED",
            "provider": provider_name,
            "reason": str(exc),
        })
        safe_param = urllib.parse.quote(f"Authentication failed: {exc}")
        return RedirectResponse(f"{frontend_url}/login?error={safe_param}")

    # Resolve or link account safely
    try:
        user, identity, is_new = resolve_or_create_user(
            auth_db=auth_db,
            provider=claims.provider,
            provider_user_id=claims.provider_user_id,
            email=claims.email,
            email_verified=claims.email_verified,
            full_name=claims.full_name,
            avatar_url=claims.avatar_url,
            current_user_id=current_user.id if current_user else None,
        )
    except (AccountConflictError, UnverifiedEmailError, ValueError) as exc:
        audit_logger.log_decision({
            "event_type": "AUTH_LINK_BLOCKED",
            "provider": provider_name,
            "email": claims.email,
            "reason": str(exc),
        })
        safe_param = urllib.parse.quote(str(exc))
        redirect_target = f"{frontend_url}/settings?error={safe_param}" if current_user else f"{frontend_url}/login?error={safe_param}"
        return RedirectResponse(redirect_target)

    # Log successful authentication in the audit trail
    event_type = "AUTH_ACCOUNT_LINKED" if current_user else ("AUTH_REGISTER_SUCCESS" if is_new else "AUTH_LOGIN_SUCCESS")
    audit_logger.log_decision({
        "event_type": event_type,
        "user_id": user.id,
        "email": user.primary_email,
        "provider": claims.provider,
        "provider_user_id": claims.provider_user_id,
    })

    # If this was an authenticated linking request, redirect back to Settings
    if current_user:
        return RedirectResponse(f"{frontend_url}/settings?linked={provider_name}")

    # Create new session
    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    expiry = get_session_expiry_iso()
    user_agent = request.headers.get("user-agent", "")
    ip_addr = request.client.host if request.client else ""

    auth_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expiry,
        user_agent=user_agent,
        ip_address=ip_addr,
    )

    # Set secure HttpOnly cookie and redirect
    response = RedirectResponse(f"{frontend_url}/?login_success=1", status_code=303)
    cookie_kwargs = get_cookie_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        **cookie_kwargs,
    )
    return response


@router.get("/me", response_model=UserPublicProfile)
def get_current_user_profile(
    user: User = Depends(get_current_user),
    auth_db: AuthDatabase = Depends(get_auth_db),
):
    """Return the authenticated user's profile and connected identity providers."""
    identities = auth_db.get_identities_for_user(user.id)
    public_identities = [
        IdentityPublic(
            provider=i.provider,
            provider_user_id=i.provider_user_id,
            email=i.email,
            email_verified=i.email_verified,
            linked_at=i.linked_at,
            last_login_at=i.last_login_at,
        )
        for i in identities
    ]
    return UserPublicProfile(
        id=user.id,
        primary_email=user.primary_email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        identities=public_identities,
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    auth_db: AuthDatabase = Depends(get_auth_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Invalidate current session and clear session cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        token_hash = hash_token(token)
        session = auth_db.get_valid_session(token_hash)
        if session:
            auth_db.revoke_session(session.session_id)
            audit_logger.log_decision({
                "event_type": "AUTH_LOGOUT",
                "user_id": session.user_id,
                "session_id": session.session_id,
            })

    # Clear cookie
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return {"status": "logged_out"}


@router.post("/identities/{provider}/unlink", response_model=UserPublicProfile)
def unlink_provider_identity(
    provider: str,
    user: User = Depends(get_current_user),
    auth_db: AuthDatabase = Depends(get_auth_db),
    audit_logger: AuditLogger = Depends(get_audit_logger),
):
    """Unlink a connected secondary identity provider."""
    provider_name = provider.lower().strip()
    try:
        auth_db.unlink_identity(user.id, provider_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_logger.log_decision({
        "event_type": "AUTH_IDENTITY_UNLINKED",
        "user_id": user.id,
        "provider": provider_name,
    })

    return get_current_user_profile(user=user, auth_db=auth_db)
