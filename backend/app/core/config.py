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

    release_version: str = "1.4.0"
    release_sha: str | None = None
    frontend_base_url: str = "http://localhost:8080"
    deployment_environment_code: str = "local"
    # The deployment's own classification. Deliberately no default: it decides
    # `prod_like` in the acceptance catalog, and every safety gate there
    # (DEV_TOKENS_DISABLED, TLS_ENABLED, CORS_RESTRICTED,
    # OBJECT_STORAGE_CONFIGURED, OIDC_MODE_ENABLED, MONITORING_ENABLED) is
    # waived when it is false. Any default at all would therefore be a
    # security verdict this service invented about itself.
    deployment_environment_type: str | None = None  # Integration|Pilot|Staging|Production
    deployment_environment_name: str | None = None
    monitoring_enabled: bool = False
    tls_enabled: bool = False
    backup_storage_root: str = "./var/backups"
    deployment_report_root: str = "./var/deployment-reports"
    baseline_release_root: str = "./var/baseline-releases"
    governance_export_root: str = "./var/governance-exports"

    @property
    def cors_origin_list(self) -> list[str]:
        """Resolved CORS origins, normalised.

        An Origin header is a bare scheme://host[:port] - never a path and
        never a trailing slash - and CORSMiddleware compares it literally. A
        configured value of "https://app.example.com/" therefore matches
        nothing and every browser request fails, so trailing slashes and
        surrounding whitespace are stripped rather than silently breaking CORS.
        Invalid entries are dropped here and reported by
        cors_origin_problems() so startup can surface them.
        """
        resolved: list[str] = []
        for raw in self.cors_origins.split(","):
            value = raw.strip()
            if not value:
                continue
            if value == "*":
                resolved.append(value)
                continue
            value = value.rstrip("/")
            if not value.startswith(("http://", "https://")):
                continue
            if value not in resolved:
                resolved.append(value)
        return resolved

    def cors_origin_problems(self) -> list[str]:
        """Configured entries that were rejected, for visible startup reporting."""
        problems: list[str] = []
        for raw in self.cors_origins.split(","):
            value = raw.strip()
            if not value or value == "*":
                continue
            if not value.rstrip("/").startswith(("http://", "https://")):
                problems.append(value)
        return problems

    @property
    def oidc_algorithm_list(self) -> list[str]:
        return [x.strip() for x in self.oidc_algorithms.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
