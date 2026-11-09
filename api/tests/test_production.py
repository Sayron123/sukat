"""Production settings: refuse unsafe config at startup, no API docs, CORS only from the
configured origins."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app

SECRET = "x" * 40
SAFE = {
    "APP_ENV": "production",
    "JWT_SECRET": SECRET,
    "DATABASE_URL": "postgresql+psycopg://sukat_app:a-real-password@db:5432/sukat",
    "CORS_ORIGINS": "https://sukat.example.com,https://www.sukat.example.com",
}


def prod(**overrides) -> Settings:
    return Settings(_env_file=None, **{**SAFE, **overrides})


def test_a_safe_production_config_starts():
    s = prod()
    assert s.is_production and not s.DEBUG


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"JWT_SECRET": "dev-only-insecure-secret-change-me"}, "JWT_SECRET"),
        ({"JWT_SECRET": "short"}, "JWT_SECRET"),
        ({"DEBUG": True}, "DEBUG"),
        ({"DATABASE_URL": "postgresql+psycopg://sukat:sukat@localhost:5432/sukat"}, "DATABASE_URL"),
        ({"CORS_ORIGINS": "*"}, "CORS_ORIGINS"),
        ({"CORS_ORIGINS": "http://localhost:3000"}, "CORS_ORIGINS"),
        ({"CORS_ORIGINS": "https://ok.example.com,http://bad.example.com"}, "CORS_ORIGINS"),
        ({"CORS_ORIGINS": ""}, "CORS_ORIGINS"),
    ],
)
def test_production_refuses_unsafe_settings(overrides, message):
    with pytest.raises(ValidationError) as e:
        prod(**overrides)
    assert message in str(e.value)


def test_a_typo_in_app_env_still_gets_the_production_checks():
    with pytest.raises(ValidationError):
        prod(APP_ENV="prod", DEBUG=True)


def test_development_allows_the_local_defaults():
    s = Settings(_env_file=None, APP_ENV="development", DEBUG=True)
    assert not s.is_production


def test_docs_are_off_in_production_and_on_in_development():
    with TestClient(create_app(prod())) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404, path
    dev = Settings(_env_file=None, APP_ENV="development")
    with TestClient(create_app(dev)) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_cors_allows_only_configured_origins():
    with TestClient(create_app(prod())) as client:

        def preflight(origin: str):
            return client.options(
                "/v1/auth/login",
                headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
            )

        ok = preflight("https://sukat.example.com")
        assert ok.headers.get("access-control-allow-origin") == "https://sukat.example.com"
        bad = preflight("https://evil.example.com")
        assert "access-control-allow-origin" not in bad.headers
