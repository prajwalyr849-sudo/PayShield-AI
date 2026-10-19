"""Settings preference persistence and validation tests."""

import pytest
from fastapi import HTTPException

from backend.auth.db import AuthDatabase
from backend.settings.router import (
    DEFAULTS,
    get_preferences,
    update_preferences,
)


@pytest.fixture
def db(tmp_path):
    return AuthDatabase(str(tmp_path / "settings.sqlite3"))


@pytest.fixture
def user(db):
    return db.create_user("prefs@payshield.ai", "Prefs User")


def test_defaults_returned_when_unset(db, user):
    result = get_preferences(current_user=user, auth_db=db)
    assert result["preferences"] == DEFAULTS
    assert result["stored"] == {}


def test_security_controls_are_never_editable(db, user):
    result = get_preferences(current_user=user, auth_db=db)
    editable = set(result["editable_fields"])
    control_keys = {control["key"] for control in result["security_controls"]}
    assert control_keys.isdisjoint(editable)
    assert editable == set(DEFAULTS.keys())


def test_update_persists_and_reloads(db, user):
    update_preferences(
        {"notify_browser": True, "risk_alert_threshold": 85},
        current_user=user,
        auth_db=db,
    )
    reloaded = get_preferences(current_user=user, auth_db=db)
    assert reloaded["preferences"]["notify_browser"] is True
    assert reloaded["preferences"]["risk_alert_threshold"] == 85
    assert db.get_preferences(user.id)["risk_alert_threshold"] == 85


def test_partial_update_keeps_other_values(db, user):
    update_preferences({"display_currency": "EUR"}, current_user=user, auth_db=db)
    update_preferences({"notify_browser": True}, current_user=user, auth_db=db)
    reloaded = get_preferences(current_user=user, auth_db=db)
    assert reloaded["preferences"]["display_currency"] == "EUR"
    assert reloaded["preferences"]["notify_browser"] is True


def test_unknown_preference_rejected(db, user):
    with pytest.raises(HTTPException) as excinfo:
        update_preferences({"policy_enforcement": False}, current_user=user, auth_db=db)
    assert excinfo.value.status_code == 422


def test_out_of_range_threshold_rejected(db, user):
    with pytest.raises(HTTPException) as excinfo:
        update_preferences({"risk_alert_threshold": 500}, current_user=user, auth_db=db)
    assert excinfo.value.status_code == 422


def test_wrong_type_rejected(db, user):
    with pytest.raises(HTTPException) as excinfo:
        update_preferences({"notify_browser": "yes"}, current_user=user, auth_db=db)
    assert excinfo.value.status_code == 422


def test_unsupported_currency_rejected(db, user):
    with pytest.raises(HTTPException) as excinfo:
        update_preferences({"display_currency": "XYZ"}, current_user=user, auth_db=db)
    assert excinfo.value.status_code == 422
