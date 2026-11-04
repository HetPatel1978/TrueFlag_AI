from pathlib import Path
from uuid import UUID

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_env: str = "local"
    regulatory_context_id: UUID | None = None
    database_url: str = "postgresql+psycopg://trueflag@127.0.0.1:5432/trueflag"
    jwt_secret: SecretStr
    jwt_issuer: str = "trueflag-ai"
    jwt_audience: str = "trueflag-api"
    access_token_minutes: int = 15
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    max_request_bytes: int = Field(default=65536, ge=1024, le=1048576)
    login_attempt_limit: int = Field(default=10, ge=1, le=100)
    login_window_seconds: int = Field(default=60, ge=1, le=3600)
    assessment_api_rate_limit: int = Field(default=120, ge=1, le=10000)
    assessment_api_window_seconds: int = Field(default=60, ge=1, le=3600)
    assessment_queue_capacity: int = Field(default=1000, ge=1, le=100000)
    csv_staging_root: Path = PROJECT_ROOT / "runtime" / "csv-staging"
    csv_max_bytes: int = Field(default=1048576, ge=1024, le=8388608)
    csv_max_rows: int = Field(default=2000, ge=1, le=10000)
    csv_max_columns: int = Field(default=64, ge=30, le=128)
    csv_max_field_bytes: int = Field(default=16384, ge=128, le=65536)
    csv_retention_seconds: int = Field(default=86400, ge=300, le=604800)
    csv_max_active_uploads: int = Field(default=10, ge=1, le=100)
    csv_max_concurrent_uploads: int = Field(default=4, ge=1, le=16)
    csv_cleanup_interval_seconds: int = Field(default=300, ge=30, le=3600)
    csv_max_validation_versions: int = Field(default=5, ge=1, le=20)
    csv_max_concurrent_validations: int = Field(default=2, ge=1, le=8)
    csv_validation_timeout_seconds: int = Field(default=10, ge=1, le=30)
    csv_import_chunk_size: int = Field(default=50, ge=1, le=200)
    csv_import_queue_capacity: int = Field(default=100, ge=1, le=1000)
    csv_import_actor_capacity: int = Field(default=3, ge=1, le=20)
    csv_import_lease_seconds: int = Field(default=60, ge=30, le=120)
    csv_import_chunk_timeout_seconds: int = Field(default=10, ge=1, le=15)
    batch_assessment_group_size: int = Field(default=10, ge=1, le=25)
    batch_assessment_capacity: int = Field(default=20, ge=1, le=100)
    batch_assessment_actor_capacity: int = Field(default=3, ge=1, le=20)
    batch_assessment_interval_seconds: int = Field(default=2, ge=1, le=30)
    batch_assessment_groups_per_tick: int = Field(default=3, ge=1, le=10)
    batch_assessment_dispatch_enabled: bool = False
    batch_export_max_rows: int = Field(default=500, ge=1, le=1000)
    batch_export_max_bytes: int = Field(default=1048576, ge=1024, le=4194304)

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
