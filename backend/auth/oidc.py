"""OpenID Connect and OAuth 2.0 client implementations for Google and PayPal Identity."""

import os
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


class OIDCConfigurationError(ValueError):
    """Raised when an identity provider is called without required configuration."""
    pass


class OIDCAuthenticationError(RuntimeError):
    """Raised when identity exchange or token validation fails."""
    pass


class PayPalIdentityUnavailableError(RuntimeError):
    """Raised when PayPal account does not have Log in with PayPal enabled."""
    pass


@dataclass(frozen=True)
class OIDCUserClaims:
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool
    full_name: str
    avatar_url: str = ""


class GoogleOIDCClient:
    """Client for Google OpenID Connect flow."""

    AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        timeout: int = 15,
    ):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "") if client_id is None else client_id
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "") if client_secret is None else client_secret
        self.redirect_uri = redirect_uri or os.getenv(
            "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
        )
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.client_id.strip() and self.client_secret.strip())

    def get_authorization_url(
        self, state: str, code_challenge: str, redirect_uri: Optional[str] = None
    ) -> str:
        if not self.is_configured():
            raise OIDCConfigurationError(
                "Google Sign-In is not configured. Set GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET in your environment."
            )

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{self.AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_user(
        self, code: str, code_verifier: str, redirect_uri: Optional[str] = None
    ) -> OIDCUserClaims:
        if not self.is_configured():
            raise OIDCConfigurationError("Google credentials are not configured.")

        # Exchange authorization code for tokens
        token_payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri or self.redirect_uri,
        }

        try:
            token_resp = requests.post(
                self.TOKEN_ENDPOINT,
                data=token_payload,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OIDCAuthenticationError(f"Failed to reach Google token endpoint: {exc}") from exc

        if token_resp.status_code != 200:
            error_data = token_resp.json() if "application/json" in token_resp.headers.get("content-type", "") else {}
            err_msg = error_data.get("error_description", token_resp.text)
            raise OIDCAuthenticationError(f"Google token exchange failed ({token_resp.status_code}): {err_msg}")

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise OIDCAuthenticationError("Google did not return an access token.")

        # Fetch user profile
        try:
            user_resp = requests.get(
                self.USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OIDCAuthenticationError(f"Failed to reach Google userinfo endpoint: {exc}") from exc

        if user_resp.status_code != 200:
            raise OIDCAuthenticationError(f"Google userinfo request failed: {user_resp.status_code}")

        user_data = user_resp.json()
        sub = user_data.get("sub")
        email = user_data.get("email")
        if not sub or not email:
            raise OIDCAuthenticationError("Google user profile is missing required identity claims.")

        return OIDCUserClaims(
            provider="google",
            provider_user_id=str(sub),
            email=str(email).lower(),
            email_verified=bool(user_data.get("email_verified", False)),
            full_name=user_data.get("name", email.split("@")[0].title()),
            avatar_url=user_data.get("picture", ""),
        )


class PayPalIdentityClient:
    """Client for Log in with PayPal (OpenID Connect Identity)."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        timeout: int = 15,
    ):
        if client_id is not None:
            self.client_id = client_id
        else:
            self.client_id = os.getenv("PAYPAL_IDENTITY_CLIENT_ID", "")

        if client_secret is not None:
            self.client_secret = client_secret
        else:
            self.client_secret = os.getenv("PAYPAL_IDENTITY_CLIENT_SECRET", "")

        self.base_url = (
            base_url or os.getenv("PAYPAL_IDENTITY_BASE_URL") or os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
        ).rstrip("/")
        self.redirect_uri = redirect_uri or os.getenv(
            "PAYPAL_IDENTITY_REDIRECT_URI", "http://localhost:8000/auth/paypal/callback"
        )
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.client_id.strip() and self.client_secret.strip())

    def get_authorization_url(
        self, state: str, code_challenge: str, redirect_uri: Optional[str] = None
    ) -> str:
        if not self.is_configured():
            raise OIDCConfigurationError(
                "PayPal Identity is not configured. Set PAYPAL_IDENTITY_CLIENT_ID and "
                "PAYPAL_IDENTITY_CLIENT_SECRET in your environment."
            )

        auth_domain = (
            "https://www.sandbox.paypal.com/signin/authorize"
            if "sandbox" in self.base_url.lower()
            else "https://www.paypal.com/signin/authorize"
        )

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri or self.redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{auth_domain}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_user(
        self, code: str, code_verifier: str, redirect_uri: Optional[str] = None
    ) -> OIDCUserClaims:
        if not self.is_configured():
            raise OIDCConfigurationError("PayPal Identity credentials are not configured.")

        token_url = f"{self.base_url}/v1/oauth2/token"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri or self.redirect_uri,
        }

        try:
            token_resp = requests.post(
                token_url,
                auth=(self.client_id, self.client_secret),
                data=data,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OIDCAuthenticationError(f"Failed to reach PayPal Identity token endpoint: {exc}") from exc

        if token_resp.status_code == 401 or token_resp.status_code == 403:
            raise PayPalIdentityUnavailableError(
                "PayPal application rejected identity token exchange. Ensure 'Log in with PayPal' "
                "is enabled with 'openid profile email' scopes in your PayPal Developer Dashboard app settings."
            )

        if token_resp.status_code != 200:
            raise OIDCAuthenticationError(
                f"PayPal Identity token exchange failed ({token_resp.status_code}): {token_resp.text}"
            )

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise OIDCAuthenticationError("PayPal Identity did not return an access token.")

        userinfo_url = f"{self.base_url}/v1/identity/openidconnect/userinfo?schema=openid"
        try:
            user_resp = requests.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OIDCAuthenticationError(f"Failed to reach PayPal userinfo endpoint: {exc}") from exc

        if user_resp.status_code != 200:
            raise OIDCAuthenticationError(
                f"PayPal Identity userinfo request failed ({user_resp.status_code}): {user_resp.text}"
            )

        user_data = user_resp.json()
        sub = user_data.get("user_id") or user_data.get("payer_id") or user_data.get("sub")
        email = user_data.get("email")
        if not sub or not email:
            raise OIDCAuthenticationError("PayPal user profile did not return required identity claims.")

        verified = bool(user_data.get("verified_account", False) or user_data.get("email_verified", False))

        return OIDCUserClaims(
            provider="paypal",
            provider_user_id=str(sub),
            email=str(email).lower(),
            email_verified=verified,
            full_name=user_data.get("name", email.split("@")[0].title()),
            avatar_url="",
        )
