from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    """App settings. Values come from environment variables or the api/.env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "development" or "production". Production refuses to start with unsafe defaults.
    APP_ENV: str = "development"

    DATABASE_URL: str = "postgresql+psycopg://sukat:sukat@localhost:5432/sukat"
    # Comma-separated list of allowed origins, e.g. "http://localhost:3000,http://127.0.0.1:3000"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Secret used to sign JWT access tokens. Use a long random value outside development.
    JWT_SECRET: str = DEV_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    INVITE_EXPIRE_HOURS: int = 72

    # Failed login / invite-accept limits, counted over a sliding window.
    AUTH_FAILURE_WINDOW_MINUTES: int = 15
    AUTH_MAX_FAILURES_PER_EMAIL: int = 10
    AUTH_MAX_FAILURES_PER_IP: int = 30

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.APP_ENV == "production" and (
            self.JWT_SECRET == DEV_JWT_SECRET or len(self.JWT_SECRET) < 32
        ):
            raise ValueError("Set JWT_SECRET to a random value of at least 32 characters.")
        return self


settings = Settings()
