from app.foundation.llm.runtime_config import RuntimeModelConfig


def test_available_models_filters_by_configured_keys(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "sk-openai")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "llm_model", "claude-sonnet-4-6")
    monkeypatch.setattr(settings, "llm_fallback", "gpt-4o-mini")

    cfg = RuntimeModelConfig(settings.redis_url)
    models = cfg.available_models()

    assert "gpt-4o-mini" in models
    # Defaults are exposed even without provider key so the API can reset to defaults.
    assert "claude-sonnet-4-6" in models


def test_available_models_includes_anthropic_when_key_present(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant")

    cfg = RuntimeModelConfig(settings.redis_url)
    models = cfg.available_models()

    assert "claude-haiku-4-5-20251001" in models
    assert "claude-sonnet-4-6" in models
