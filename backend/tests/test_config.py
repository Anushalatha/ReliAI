from app.core.config import Settings


def test_settings_read_environment_variables(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/testdb")
    monkeypatch.setenv("APP_NAME", "ReliAI test")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/testdb"
    assert settings.app_name == "ReliAI test"


def test_settings_have_safe_local_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "localhost" in settings.database_url


def test_together_settings_are_optional_and_mock_is_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    monkeypatch.delenv("TOGETHER_MODEL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "mock"
    assert settings.together_api_key is None
    assert settings.together_model == "Qwen/Qwen3.5-9B"
    assert settings.groq_api_key is None
    assert settings.groq_model == "openai/gpt-oss-20b"


def test_together_settings_read_environment_variables(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "together")
    monkeypatch.setenv("TOGETHER_API_KEY", "test-key")
    monkeypatch.setenv("TOGETHER_MODEL", "custom/model")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "together"
    assert settings.together_api_key.get_secret_value() == "test-key"
    assert settings.together_model == "custom/model"


def test_groq_settings_read_environment_variables(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("GROQ_MODEL", "custom/groq-model")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "groq"
    assert settings.groq_api_key.get_secret_value() == "groq-test-key"
    assert settings.groq_model == "custom/groq-model"
