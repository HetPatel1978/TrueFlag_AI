"""Provider credential mapping stays server-side and does not activate dispatch."""

from pydantic import SecretStr

from app.core.config import Settings
from app.services.provider_budget import finance_dispatch_allowed


def test_llm_key_fallback_does_not_enable_provider(monkeypatch):
    monkeypatch.delenv("INVESTIGATION_PROVIDER_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "synthetic-fallback-key")
    settings = Settings(_env_file=None, jwt_secret=SecretStr("x" * 32))
    assert settings.investigation_provider_api_key.get_secret_value() == "synthetic-fallback-key"
    assert not settings.investigation_external_enabled
    assert not finance_dispatch_allowed(settings)
    assert "synthetic-fallback-key" not in repr(settings)


def test_existing_provider_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("INVESTIGATION_PROVIDER_API_KEY", "synthetic-canonical-key")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-fallback-key")
    settings = Settings(_env_file=None, jwt_secret=SecretStr("x" * 32))
    assert settings.investigation_provider_api_key.get_secret_value() == "synthetic-canonical-key"


def test_explicit_provider_key_remains_supported(monkeypatch):
    monkeypatch.delenv("INVESTIGATION_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("x" * 32),
        investigation_provider_api_key=SecretStr("synthetic-explicit-key"),
    )
    assert settings.investigation_provider_api_key.get_secret_value() == "synthetic-explicit-key"
