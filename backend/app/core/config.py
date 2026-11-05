from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ReliAI"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://reli:reli_local_only@localhost:5432/reli"
    database_connect_timeout_seconds: int = Field(default=5, ge=1)
    log_level: str = "INFO"
    llm_provider: Literal["mock", "together", "groq"] = "mock"
    together_api_key: SecretStr | None = None
    together_model: str = "Qwen/Qwen3.5-9B"
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-20b"
    dataset_import_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    dataset_import_max_cases: int = Field(default=10_000, ge=1, le=100_000)
    dataset_import_batch_size: int = Field(default=500, ge=1, le=5000)
    project_allowed_hosts: str = ""
    project_allowed_endpoints: str = ""
    project_allowed_local_docker_endpoints: str = ""
    project_local_docker_network_cidr: str = ""
    project_auth_env_vars: str = ""
    project_auth_tokens_json: SecretStr | None = None
    project_http_timeout_seconds: int = Field(default=20, ge=1, le=120)
    project_max_concurrency: int = Field(default=8, ge=1, le=32)
    project_requests_per_second: int = Field(default=5, ge=1, le=100)
    project_max_retries: int = Field(default=1, ge=0, le=2)
    cors_allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173,"
        "http://localhost:8002,http://127.0.0.1:8002"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
