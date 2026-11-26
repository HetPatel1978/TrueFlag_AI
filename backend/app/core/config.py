from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )
    app_env: str = "local"
    casework_allowed_resolutions: list[
        Literal[
            "additional_review_required",
            "no_further_action_recommended",
            "escalated_for_compliance_review",
            "investigation_completed",
        ]
    ] = Field(
        default_factory=lambda: [
            "additional_review_required",
            "no_further_action_recommended",
            "escalated_for_compliance_review",
            "investigation_completed",
        ],
        min_length=1,
        max_length=4,
    )
    regulatory_context_id: UUID | None = None
    academic_research_enabled: bool = False
    academic_research_scope_file: Path | None = None
    academic_research_scope_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    academic_research_approval_file: Path | None = None
    # Owner-written spending-approver policy (named user IDs, cumulative cap). Absent means
    # research requests can only be approved through the owner's exact-approval file.
    academic_research_approver_file: Path | None = None
    academic_research_response_file: Path | None = None
    academic_research_credential_file: Path | None = None
    anthropic_research_dispatch_enabled: bool = False
    anthropic_research_approval_id: str = Field(default="", max_length=100)
    anthropic_research_input_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_research_request_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    investigation_simulation_enabled: bool = False
    investigation_external_enabled: bool = False
    investigation_probe_bootstrap_enabled: bool = False
    investigation_provider_approval_id: str = Field(
        default="", max_length=100, pattern=r"^[A-Za-z0-9_.-]*$"
    )
    investigation_provider_terms_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    investigation_provider_contract_verified: bool = False
    investigation_provider_financial_policy: Literal["bounded_probe_v3", "prepaid_floor_v2"] = (
        "bounded_probe_v3"
    )
    investigation_provider_financial_authorization_sha256: str = Field(
        default="325d4dc7770f35606023fbd4c3a0738ee700ee1ad79b6499f09393ec4afdbe18",
        pattern=r"^[a-f0-9]{64}$",
    )
    investigation_provider_minimum_balance_usd: float = Field(
        default=200, ge=200, le=1000000, allow_inf_nan=False
    )
    investigation_provider_balance_buffer_usd: float = Field(
        default=1, ge=0, le=1000000, allow_inf_nan=False
    )
    investigation_provider_balance_max_age_seconds: int = Field(default=15, ge=1, le=60)
    investigation_provider_balance_lookup_enabled: bool = False
    investigation_provider_call_limit: int = Field(default=0, ge=0, le=3)
    investigation_provider_spend_limit_usd: float = Field(
        default=797, ge=0, le=797, allow_inf_nan=False
    )
    investigation_provider_input_usd_per_million: float = Field(default=0, ge=0, le=1000)
    investigation_provider_output_usd_per_million: float = Field(default=0, ge=0, le=1000)
    investigation_provider_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("INVESTIGATION_PROVIDER_API_KEY", "LLM_API_KEY"),
    )
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="ANTHROPIC_API_KEY"
    )
    anthropic_synthetic_demo_enabled: bool = False
    anthropic_contract_verified: bool = False
    anthropic_bootstrap_enabled: bool = False
    anthropic_bootstrap_input_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_diagnostic_enabled: bool = False
    anthropic_diagnostic_input_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_fix_verification_enabled: bool = False
    anthropic_fix_input_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_verification_diagnostic_enabled: bool = False
    anthropic_verification_input_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_claim_fix_enabled: bool = False
    anthropic_live_validation_enabled: bool = False
    anthropic_development_validation_enabled: bool = False
    anthropic_development_input_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_development_approval_id: str = Field(default="", max_length=100)
    anthropic_live_validation_input_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_analyst_generation_enabled: bool = False
    regulatory_investigation_enabled: bool = False
    anthropic_claim_fix_input_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_terms_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    anthropic_demo_spend_limit_usd: float = Field(default=20, ge=0, le=20, allow_inf_nan=False)
    anthropic_demo_call_limit: int = Field(default=20, ge=0, le=100)
    database_url: str = "postgresql+psycopg://trueflag@127.0.0.1:5432/trueflag"
    jwt_secret: SecretStr
    jwt_issuer: str = "trueflag-ai"
    jwt_audience: str = "trueflag-api"
    access_token_minutes: int = 60
    local_persistent_login_username: str = Field(
        default="", max_length=100, pattern=r"^(?:[a-z0-9]{3,100})?$"
    )
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
    batch_assessment_dispatch_rate_limit: int = Field(default=120, ge=1, le=10000)
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
