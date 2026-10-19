"""Health endpoint tests: component status without leaking secrets."""

from backend.main import health


def test_health_reports_components_and_providers(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYSHIELD_DB_PATH", str(tmp_path / "health.sqlite3"))
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    result = health()

    assert result["status"] in ("ok", "degraded")
    assert result["application"]["name"] == "PayShield AI"
    assert set(result["components"]) == {"api", "database", "audit_log"}
    assert set(result["providers"]) == {"channel3", "live_search_fallback", "paypal_sandbox"}


def test_health_never_exposes_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYSHIELD_DB_PATH", str(tmp_path / "health.sqlite3"))
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("CHANNEL3_API_KEY", "super-secret-key")
    monkeypatch.setenv("ENDLESS_SEARCH_KEY", "another-secret")

    result = health()

    assert "super-secret-key" not in str(result)
    assert "another-secret" not in str(result)
    assert result["providers"]["channel3"]["configured"] is True
    assert result["providers"]["live_search_fallback"]["configured"] is True
