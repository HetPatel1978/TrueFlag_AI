from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_env: str = "local"
    database_url: str = "postgresql+psycopg://trueflag@127.0.0.1:5432/trueflag"
    jwt_secret: SecretStr
    jwt_issuer: str = "trueflag-ai"
    jwt_audience: str = "trueflag-api"
    access_token_minutes: int = 15
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    @field_validator("jwt_secret")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError(
                "JWT_SECRET must contain at least 32 characters; run scripts/init_env.py"
            )
        return value

    @field_validator("access_token_minutes")
    @classmethod
    def bounded_expiry(cls, value: int) -> int:
        if not 1 <= value <= 60:
            raise ValueError("ACCESS_TOKEN_MINUTES must be between 1 and 60")
        return value
