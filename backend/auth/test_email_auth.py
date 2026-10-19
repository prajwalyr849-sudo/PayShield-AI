from fastapi import HTTPException, Response
import pytest

from backend.audit.audit_logger import AuditLogger
from backend.auth.db import AuthDatabase
from backend.auth.models import (
    EmailAuthRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
)
from backend.auth.router import (
    confirm_password_reset,
    login_email,
    register_email,
)
from backend.auth.security import generate_secure_token, hash_token
from starlette.requests import Request


def make_request():
    return Request({
        "type": "http",
        "method": "POST",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
    })


@pytest.fixture
def auth_setup(tmp_path):
    db = AuthDatabase(str(tmp_path / "auth.sqlite3"))
    audit = AuditLogger(str(tmp_path / "audit.jsonl"))
    return db, audit


def test_register_and_login_with_correct_password(auth_setup):
    db, audit = auth_setup
    response = Response()
    profile = register_email(
        make_request(),
        RegisterRequest(
            name="Secure User",
            email=" User@Example.com ",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
        ),
        response,
        db,
        audit,
    )
    assert profile.primary_email == "user@example.com"
    assert db.get_password_hash(profile.id)
    assert "payshield_session" in response.headers["set-cookie"]

    login_response = Response()
    logged_in = login_email(
        make_request(),
        EmailAuthRequest(email="USER@example.com", password="StrongPassword123!"),
        login_response,
        db,
        audit,
    )
    assert logged_in.id == profile.id


def test_duplicate_and_wrong_password_are_rejected(auth_setup):
    db, audit = auth_setup
    register_email(
        make_request(),
        RegisterRequest(
            name="Secure User",
            email="duplicate@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
        ),
        Response(),
        db,
        audit,
    )
    with pytest.raises(HTTPException) as duplicate:
        register_email(
            make_request(),
            RegisterRequest(
                name="Other User",
                email="duplicate@example.com",
                password="StrongPassword123!",
                confirm_password="StrongPassword123!",
            ),
            Response(),
            db,
            audit,
        )
    assert duplicate.value.status_code == 409
    with pytest.raises(HTTPException) as wrong:
        login_email(
            make_request(),
            EmailAuthRequest(email="duplicate@example.com", password="WrongPassword123!"),
            Response(),
            db,
            audit,
        )
    assert wrong.value.status_code == 401
    assert wrong.value.detail == "Invalid email or password."


def test_reset_token_is_single_use_and_revokes_sessions(auth_setup):
    db, audit = auth_setup
    profile = register_email(
        make_request(),
        RegisterRequest(
            name="Reset User",
            email="reset@example.com",
            password="StrongPassword123!",
            confirm_password="StrongPassword123!",
        ),
        Response(),
        db,
        audit,
    )
    raw_token = generate_secure_token()
    db.save_password_reset_token(hash_token(raw_token), profile.id, "2999-01-01T00:00:00+00:00")
    result = confirm_password_reset(
        PasswordResetConfirmRequest(token=raw_token, password="NewStrongPassword123!"),
        Response(),
        db,
    )
    assert result["status"] == "password_updated"
    with pytest.raises(HTTPException):
        confirm_password_reset(
            PasswordResetConfirmRequest(token=raw_token, password="AnotherStrongPassword123!"),
            Response(),
            db,
        )


def test_rate_limit_blocks_repeated_attempts(auth_setup):
    db, audit = auth_setup
    for _ in range(5):
        with pytest.raises(HTTPException) as failure:
            login_email(
                make_request(),
                EmailAuthRequest(email="missing@example.com", password="WrongPassword123!"),
                Response(),
                db,
                audit,
            )
        assert failure.value.status_code == 401
    with pytest.raises(HTTPException) as limited:
        login_email(
            make_request(),
            EmailAuthRequest(email="missing@example.com", password="WrongPassword123!"),
            Response(),
            db,
            audit,
        )
    assert limited.value.status_code == 429
