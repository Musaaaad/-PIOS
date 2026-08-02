from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIOS_", env_file=".env", extra="ignore")

    env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://pios:pios@localhost:5432/pios"
    organization_code: str = "NBC"
    default_site_code: str = "TGH"
    log_level: str = "INFO"

    # Authentication: dev tokens are restricted to non-production environments.
    auth_mode: str = "dev"  # dev | oidc
    allow_dev_tokens: bool = True
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_jwks_json: str | None = None
    oidc_algorithms: str = "RS256"
    oidc_roles_claim: str = "roles"
    oidc_user_id_claim: str = "sub"
    oidc_email_claim: str = "email"
    oidc_name_claim: str = "name"
    oidc_site_claim: str = "sites"

    cors_origins: str = "http://localhost:8080,http://localhost:5173"

    object_storage_backend: str = "local"  # local | s3
    object_storage_root: str = "./var/evidence"
    object_storage_bucket: str = "pios-evidence"
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    max_upload_size_mb: int = 25
    antivirus_mode: str = "basic"  # basic | disabled

    export_storage_root: str = "./var/exports"
    export_retention_days: int = 30
    notification_default_limit: int = 100

    release_version: str = "1.3.0"
    release_sha: str | None = None
    frontend_base_url: str = "http://localhost:8080"
    deployment_environment_code: str = "local"
    monitoring_enabled: bool = False
    tls_enabled: bool = False
    backup_storage_root: str = "./var/backups"
    deployment_report_root: str = "./var/deployment-reports"
    baseline_release_root: str = "./var/baseline-releases"
    governance_export_root: str = "./var/governance-exports"

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def oidc_algorithm_list(self) -> list[str]:
        return [x.strip() for x in self.oidc_algorithms.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
