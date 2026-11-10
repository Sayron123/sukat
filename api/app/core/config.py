from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"
DEFAULT_DB_CREDENTIALS = "//sukat:sukat@"


class Settings(BaseSettings):
    """App settings. Values come from environment variables or the api/.env file."""

    # hide_input_in_errors: a settings error at startup must not print the values (they
    # include secrets) into the server log.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    # Defaults to "production" so a server with no APP_ENV is safe. Only the exact value
    # "development" allows the public dev JWT_SECRET (a typo like "prod" still gets checked).
    APP_ENV: str = "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    RELEASE: str = ""

    DATABASE_URL: str = "postgresql+psycopg://sukat:sukat@localhost:5432/sukat"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    # Stores' local time zone. Reports take dates in this zone ("today" = a Manila day)
    # and convert them to UTC for queries, because timestamps are stored in UTC.
    # The web app has its own copy (STORE_TZ in web/src/lib/dates.ts): change both together.
    STORE_TIMEZONE: str = "Asia/Manila"
    # Comma-separated list of allowed origins, e.g. "http://localhost:3000,http://127.0.0.1:3000"
    CORS_ORIGINS: str = "http://localhost:3000"

    # Secret used to sign JWT access tokens. Use a long random value outside development.
    # Secrets are SecretStr: they print as "**********". Read with .get_secret_value().
    JWT_SECRET: SecretStr = SecretStr(DEV_JWT_SECRET)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 3650
    INVITE_EXPIRE_HOURS: int = 72
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    EMAIL_VERIFY_EXPIRE_HOURS: int = 48
    WEB_APP_URL: str = "http://localhost:3000"

    # Failed login / invite-accept limits, counted over a sliding window.
    AUTH_FAILURE_WINDOW_MINUTES: int = 15
    AUTH_MAX_FAILURES_PER_EMAIL: int = 10
    AUTH_MAX_FAILURES_PER_IP: int = 30
    AUTH_EMAILS_MAX_PER_EMAIL: int = 3
    AUTH_EMAILS_MAX_PER_IP: int = 20

    EMAIL_BACKEND: Literal["console", "smtp"] = "console"
    EMAIL_WORKER_ENABLED: bool = True
    EMAIL_POLL_SECONDS: float = 5
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: SecretStr = SecretStr("")
    SMTP_FROM: str = ""
    SIGNUP_MAX_PER_IP: int = 5
    INTERNAL_API_SECRET: SecretStr = SecretStr("")

    # ----- Photo storage -----
    # "local" saves uploads under LOCAL_UPLOAD_DIR (development); "r2" uses Cloudflare R2.
    STORAGE_BACKEND: Literal["local", "r2"] = "local"
    LOCAL_UPLOAD_DIR: str = "./uploads"
    # Public base URL of this API; local upload URLs point here.
    PUBLIC_API_URL: str = "http://localhost:8000"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: SecretStr = SecretStr("")
    R2_BUCKET: str = ""
    UPLOAD_MAX_BYTES: int = 5 * 1024 * 1024
    MAX_REQUEST_BYTES: int = 1024 * 1024
    UPLOAD_URL_EXPIRE_SECONDS: int = 300

    # ----- AI (reading list photos) -----
    GEMINI_API_KEY: SecretStr = SecretStr("")
    ANTHROPIC_API_KEY: SecretStr = SecretStr("")
    AI_PROVIDER: Literal["gemini", "anthropic"] = "gemini"
    AI_FALLBACK_PROVIDER: Literal["none", "gemini", "anthropic"] = "none"
    AI_MODEL: str = "gemini-3.1-flash-lite"
    AI_FALLBACK_MODEL: str = "claude-opus-5-5"
    AI_GEMINI_THINKING_LEVEL: Literal["minimal", "low", "medium", "high"] = "minimal"
    AI_EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    AI_TIMEOUT_SECONDS: float = 90.0
    AI_MAX_RETRIES: int = 1
    # Server-side refusal fallback ("default" routing). Turn off for models without it (Haiku).
    AI_REFUSAL_FALLBACK: bool = True
    # Prices in USD per million tokens, for the ai_usage cost log. Defaults match AI_MODEL;
    # update them when you change the model.
    AI_PRICE_INPUT_PER_MTOK_USD: Decimal = Decimal("0.25")
    AI_PRICE_OUTPUT_PER_MTOK_USD: Decimal = Decimal("1.50")
    AI_PRICE_CACHE_WRITE_PER_MTOK_USD: Decimal = Decimal("0.25")
    AI_PRICE_CACHE_READ_PER_MTOK_USD: Decimal = Decimal("0.025")
    AI_FALLBACK_PRICE_INPUT_PER_MTOK_USD: Decimal = Decimal("4.00")
    AI_FALLBACK_PRICE_OUTPUT_PER_MTOK_USD: Decimal = Decimal("20.00")
    AI_FALLBACK_PRICE_CACHE_WRITE_PER_MTOK_USD: Decimal = Decimal("5.00")
    AI_FALLBACK_PRICE_CACHE_READ_PER_MTOK_USD: Decimal = Decimal("0.20")
    USD_TO_PHP: Decimal = Decimal("58.00")
    AI_MONTHLY_BUDGET_CENTAVOS: int = Field(default=50000, ge=0)

    # ----- AI chat (Phase 6) -----
    # Same model as the reader (AI_MODEL). Chat answers are short lookups: low effort.
    AI_CHAT_EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    AI_CHAT_MAX_TOKENS: int = 8000  # per model call, reasoning included
    AI_CHAT_TIMEOUT_SECONDS: float = 45.0  # for the whole question, all calls together
    CHAT_MAX_TOOL_CALLS: int = 5  # per question
    CHAT_QUESTIONS_PER_HOUR: int = 30  # per store
    CHAT_HISTORY_MESSAGES: int = 10  # only the last N messages are sent to the model

    # ----- Multi-step scan -----
    # Step 2 "match": a fuzzy match (rapidfuzz, 0-100) must score at least this, and
    # clearly beat any other product, or the line goes to the AI.
    SCAN_FUZZY_THRESHOLD: int = 90
    # Step 3 "check": qty x price may differ from a written line total by this much
    # (written totals are often rounded) before the line is marked "check".
    SCAN_TOTAL_TOLERANCE_CENTAVOS: int = 100

    @property
    def has_ai_fallback(self) -> bool:
        return self.AI_FALLBACK_PROVIDER != "none"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV != "development"

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.is_production and (
            self.JWT_SECRET.get_secret_value() == DEV_JWT_SECRET
            or len(self.JWT_SECRET.get_secret_value()) < 32
        ):
            raise ValueError(
                "Set JWT_SECRET to a random value of at least 32 characters "
                "(or APP_ENV=development on your own PC)."
            )
        if self.APP_ENV != "development" and self.EMAIL_BACKEND == "console":
            raise ValueError("Set EMAIL_BACKEND=smtp outside development.")
        if self.EMAIL_BACKEND == "smtp" and not (self.SMTP_HOST and self.SMTP_FROM):
            raise ValueError("EMAIL_BACKEND=smtp needs SMTP_HOST and SMTP_FROM.")
        if self.AI_FALLBACK_PROVIDER == self.AI_PROVIDER:
            raise ValueError("AI_FALLBACK_PROVIDER must be different from AI_PROVIDER.")
        if self.is_production:
            if self.DEBUG:
                raise ValueError("DEBUG must be off in production.")
            if len(self.INTERNAL_API_SECRET.get_secret_value()) < 32:
                raise ValueError("Set INTERNAL_API_SECRET to a random value of 32+ characters.")
            if DEFAULT_DB_CREDENTIALS in self.DATABASE_URL:
                raise ValueError("Set DATABASE_URL with your own database password.")
            origins = self.cors_origins_list
            if not origins or any(not o.startswith("https://") for o in origins):
                raise ValueError(
                    "Set CORS_ORIGINS to your web app's https:// address(es), comma-separated "
                    "(no * and no http://)."
                )
        if self.STORAGE_BACKEND == "r2" and not all(
            (
                self.R2_ACCOUNT_ID,
                self.R2_ACCESS_KEY_ID,
                self.R2_SECRET_ACCESS_KEY.get_secret_value(),
                self.R2_BUCKET,
            )
        ):
            raise ValueError("STORAGE_BACKEND=r2 needs R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, ...")
        return self


settings = Settings()
