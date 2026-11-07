from decimal import Decimal
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


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

    DATABASE_URL: str = "postgresql+psycopg://sukat:sukat@localhost:5432/sukat"
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    INVITE_EXPIRE_HOURS: int = 72

    # Failed login / invite-accept limits, counted over a sliding window.
    AUTH_FAILURE_WINDOW_MINUTES: int = 15
    AUTH_MAX_FAILURES_PER_EMAIL: int = 10
    AUTH_MAX_FAILURES_PER_IP: int = 30

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
    UPLOAD_URL_EXPIRE_SECONDS: int = 300

    # ----- AI (reading list photos) -----
    # Leave empty to use the SDK's normal credential lookup (ANTHROPIC_API_KEY env, etc.).
    ANTHROPIC_API_KEY: SecretStr = SecretStr("")
    # Which VisionReader implementation to use (see app/ai/provider.py).
    # "anthropic" (Claude) or "gemini" (Google). Used for reading scans.
    AI_PROVIDER: Literal["anthropic", "gemini"] = "anthropic"
    AI_MODEL: str = "claude-opus-5-5"
    AI_EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    AI_TIMEOUT_SECONDS: float = 90.0
    AI_MAX_RETRIES: int = 1
    # Server-side refusal fallback ("default" routing). Turn off for models without it (Haiku).
    AI_REFUSAL_FALLBACK: bool = True
    # Prices in USD per million tokens, for the ai_usage cost log. Defaults match AI_MODEL;
    # update them when you change the model.
    AI_PRICE_INPUT_PER_MTOK_USD: Decimal = Decimal("4.00")
    AI_PRICE_OUTPUT_PER_MTOK_USD: Decimal = Decimal("20.00")
    AI_PRICE_CACHE_WRITE_PER_MTOK_USD: Decimal = Decimal("5.00")
    AI_PRICE_CACHE_READ_PER_MTOK_USD: Decimal = Decimal("0.20")
    USD_TO_PHP: Decimal = Decimal("58.00")

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

    # ----- Gemini (when AI_PROVIDER=gemini) -----
    # Leave the key empty to use the SDK's normal lookup (GEMINI_API_KEY / GOOGLE_API_KEY env).
    GEMINI_API_KEY: SecretStr = SecretStr("")
    # Thinking is turned off (2.x models) or set to the lowest level (3.x and later).
    GEMINI_MODEL: str = "gemini-2.5-flash"
    # USD per million tokens for GEMINI_MODEL (thinking tokens bill as output). Check the
    # current rates on Google's pricing page and update them with the model.
    GEMINI_PRICE_INPUT_PER_MTOK_USD: Decimal = Decimal("0.30")
    GEMINI_PRICE_OUTPUT_PER_MTOK_USD: Decimal = Decimal("2.50")
    GEMINI_PRICE_CACHE_READ_PER_MTOK_USD: Decimal = Decimal("0.03")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        if self.APP_ENV != "development" and (
            self.JWT_SECRET.get_secret_value() == DEV_JWT_SECRET
            or len(self.JWT_SECRET.get_secret_value()) < 32
        ):
            raise ValueError(
                "Set JWT_SECRET to a random value of at least 32 characters "
                "(or APP_ENV=development on your own PC)."
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
