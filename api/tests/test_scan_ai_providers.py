"""The two ScanAI providers with fake SDK clients (no network, no API key): request
shape, structured output, thinking setting, token usage, errors; plus provider choice,
the JSON schemas and the cost per provider."""

import json
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import SecretStr

from app.ai import gemini_reader
from app.ai.anthropic_reader import AnthropicScanAI
from app.ai.errors import AIReadError
from app.ai.gemini_reader import GeminiScanAI, thinking_config
from app.ai.pricing import cost_centavos
from app.ai.scan_output import MATCH_PROMPT, READ_PROMPT, prompt
from app.ai.schemas import (
    MATCH_SCHEMA,
    READ_SCHEMA,
    AIUsageInfo,
    MatchAnswer,
    MatchItem,
    ReadLine,
)
from app.core.config import settings

ROW = {
    "raw_text": "10 bags sem @250 2,500",
    "qty_text": "10",
    "unit_text": "bags",
    "price_text": "@250",
    "total_text": "2,500",
    "confidence": 0.97,
}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20


# ---------- schemas ----------


@pytest.mark.parametrize(
    ("schema", "model"), [(READ_SCHEMA, ReadLine), (MATCH_SCHEMA, MatchAnswer)]
)
def test_json_schemas_list_exactly_the_model_fields(schema, model):
    item = next(iter(schema["properties"].values()))["items"]
    assert set(item["properties"]) == set(model.model_fields) == set(item["required"])
    assert item["additionalProperties"] is False


def test_prompts_exist_with_the_rules():
    read = prompt(READ_PROMPT)
    assert "Copy exactly what is written" in read and "Never invent" in read
    assert read.count("Row") >= 3  # three examples
    assert "Return only ids that appear in the product list" in prompt(MATCH_PROMPT)


# ---------- Gemini ----------


class FakeGemini:
    """Stands in for genai.Client: records generate_content calls."""

    def __init__(self, result):
        self.result = result
        self.calls = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def gemini_response(payload, finish=types.FinishReason.STOP, blocked=None):
    return SimpleNamespace(
        text=json.dumps(payload),
        model_version="gemini-2.5-flash-001",
        prompt_feedback=SimpleNamespace(block_reason=blocked) if blocked else None,
        candidates=[SimpleNamespace(finish_reason=finish)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=1500,
            cached_content_token_count=500,
            candidates_token_count=200,
            thoughts_token_count=30,
        ),
    )


def test_gemini_read_request_and_usage(monkeypatch):
    monkeypatch.setattr(settings, "AI_MODEL", "gemini-2.5-flash")
    fake = FakeGemini(gemini_response({"lines": [ROW]}))
    lines, usage = GeminiScanAI(fake).read_photo(JPEG, "image/jpeg")  # type: ignore[arg-type]
    call = fake.calls[0]
    config = call["config"]
    assert call["model"] == "gemini-2.5-flash"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == READ_SCHEMA
    assert config.thinking_config.thinking_budget == 0  # thinking off
    assert config.system_instruction == prompt(READ_PROMPT)
    image = call["contents"][0]
    assert image.inline_data.data == JPEG and image.inline_data.mime_type == "image/jpeg"
    assert lines == [ReadLine(**ROW)]
    assert usage == AIUsageInfo(
        model="gemini-2.5-flash-001",
        input_tokens=1000,  # prompt minus cached
        output_tokens=230,  # answer + thoughts
        cache_read_tokens=500,
        provider="gemini",
    )


def test_gemini_match_sends_the_product_list_and_items():
    fake = FakeGemini(gemini_response({"matches": [{"line": 1, "product_id": "P2"}]}))
    answers, _ = GeminiScanAI(fake).match_items(  # type: ignore[arg-type]
        [MatchItem(line=1, text="2 kl pakong 4")], 'P2 | Common Wire Nail 4" | unit: kg'
    )
    config = fake.calls[0]["config"]
    assert config.response_json_schema == MATCH_SCHEMA
    assert config.system_instruction.startswith(prompt(MATCH_PROMPT))
    assert 'P2 | Common Wire Nail 4"' in config.system_instruction
    assert '"text": "2 kl pakong 4"' in fake.calls[0]["contents"][0]
    assert answers == [MatchAnswer(line=1, product_id="P2")]


@pytest.mark.parametrize(
    ("model", "budget", "level"),
    [
        ("gemini-2.5-flash", 0, None),
        ("gemini-2.5-flash-lite", 0, None),
        ("gemini-2.5-pro", 128, None),  # Pro can't turn thinking off
        ("gemini-3.8-flash", None, types.ThinkingLevel.MINIMAL),
        ("gemini-3.1-pro", None, types.ThinkingLevel.LOW),
    ],
)
def test_gemini_uses_the_least_thinking_each_model_allows(model, budget, level):
    config = thinking_config(model)
    assert (config.thinking_budget, config.thinking_level) == (budget, level)


@pytest.mark.parametrize(
    ("response", "message", "retryable"),
    [
        (gemini_response({"lines": []}, types.FinishReason.SAFETY), "could not be read", False),
        (gemini_response({"lines": []}, blocked="SAFETY"), "could not be read", False),
        (gemini_response({"lines": []}, types.FinishReason.MAX_TOKENS), "too long", False),
        (SimpleNamespace(**{**vars(gemini_response({})), "text": "not json"}), "unexpected", True),
    ],
)
def test_gemini_unusable_answers(response, message, retryable):
    with pytest.raises(AIReadError) as e:
        GeminiScanAI(FakeGemini(response)).read_photo(JPEG, "image/jpeg")  # type: ignore[arg-type]
    assert message in str(e.value) and e.value.retryable is retryable
    assert e.value.usage is not None  # tokens were spent: still logged


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (httpx2.ReadTimeout("slow"), True),
        (genai_errors.APIError(429, {"error": {"code": 429, "message": "busy"}}), True),
        (genai_errors.ServerError(503, {"error": {"code": 503, "message": "down"}}), True),
        (genai_errors.ClientError(400, {"error": {"code": 400, "message": "bad key"}}), False),
    ],
)
def test_gemini_api_errors(error, retryable):
    with pytest.raises(AIReadError) as e:
        GeminiScanAI(FakeGemini(error)).read_photo(JPEG, "image/jpeg")  # type: ignore[arg-type]
    assert e.value.retryable is retryable


def test_gemini_without_a_key_says_not_set_up(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr(""))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(AIReadError) as e:
        GeminiScanAI().read_photo(JPEG, "image/jpeg")
    assert str(e.value) == "The reader is not set up yet." and not e.value.retryable


def test_gemini_client_gets_timeout_and_retries(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(gemini_reader.genai, "Client", Client)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr("test-key"))
    _ = GeminiScanAI().client
    assert seen["api_key"] == "test-key"
    assert seen["http_options"].timeout == int(settings.AI_TIMEOUT_SECONDS * 1000)  # ms
    assert seen["http_options"].retry_options.attempts == settings.AI_MAX_RETRIES + 1


# ---------- Claude ----------


class FakeAnthropic:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def claude_response(payload, stop_reason="end_turn"):
    return SimpleNamespace(
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=SimpleNamespace(
            input_tokens=900,
            output_tokens=80,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


def test_claude_read_and_match_requests():
    fake = FakeAnthropic(claude_response({"lines": [ROW]}))
    lines, usage = AnthropicScanAI(fake).read_photo(JPEG, "image/jpeg")  # type: ignore[arg-type]
    req = fake.calls[0]
    assert req["model"] == settings.AI_MODEL
    assert req["output_config"] == {
        "effort": settings.AI_EFFORT,
        "format": {"type": "json_schema", "schema": READ_SCHEMA},
    }
    assert req["system"] == [{"type": "text", "text": prompt(READ_PROMPT)}]
    assert req["messages"][0]["content"][0]["type"] == "image"
    assert req["fallbacks"] == "default"
    assert lines == [ReadLine(**ROW)] and usage.provider == "anthropic"

    fake.result = claude_response({"matches": [{"line": 0, "product_id": None}]})
    answers, _ = AnthropicScanAI(fake).match_items(  # type: ignore[arg-type]
        [MatchItem(line=0, text="1 gal paint")], "P1 | Paint"
    )
    req = fake.calls[1]
    assert req["output_config"]["format"]["schema"] == MATCH_SCHEMA
    assert req["system"][1] == {
        "type": "text",
        "text": "P1 | Paint",
        "cache_control": {"type": "ephemeral"},  # the product list is cached
    }
    assert answers == [MatchAnswer(line=0, product_id=None)]


@pytest.mark.parametrize(
    ("result", "retryable"),
    [
        (claude_response({}, "refusal"), False),
        (claude_response({}, "max_tokens"), False),
        (anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")), True),
        (TypeError('"Could not resolve authentication method."'), False),
    ],
)
def test_claude_errors(result, retryable):
    with pytest.raises(AIReadError) as e:
        AnthropicScanAI(FakeAnthropic(result)).read_photo(JPEG, "image/jpeg")  # type: ignore[arg-type]
    assert e.value.retryable is retryable


# ---------- provider choice and cost ----------


@pytest.mark.parametrize(
    ("provider", "cls"), [("gemini", GeminiScanAI), ("anthropic", AnthropicScanAI)]
)
def test_ai_provider_setting_picks_the_implementation(monkeypatch, provider, cls):
    from app.ai import provider as module
    from app.ai.scan_pipeline import MultiStepReader

    monkeypatch.setattr(settings, "AI_PROVIDER", provider)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", SecretStr("test"))
    module.get_scan_ai.cache_clear()
    module.get_vision_reader.cache_clear()
    try:
        reader = module.get_vision_reader()
        assert isinstance(reader, MultiStepReader) and isinstance(reader.ai, cls)
    finally:
        module.get_scan_ai.cache_clear()
        module.get_vision_reader.cache_clear()


def test_cost_uses_the_providers_prices(monkeypatch):
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "USD_TO_PHP", Decimal("58"))
    for name, price in {
        "AI_PRICE_INPUT_PER_MTOK_USD": "0.25",
        "AI_PRICE_OUTPUT_PER_MTOK_USD": "1.50",
        "AI_PRICE_CACHE_READ_PER_MTOK_USD": "0.025",
        "AI_FALLBACK_PRICE_INPUT_PER_MTOK_USD": "4",
        "AI_FALLBACK_PRICE_OUTPUT_PER_MTOK_USD": "20",
    }.items():
        monkeypatch.setattr(settings, name, Decimal(price))
    gemini = AIUsageInfo(
        model="g", input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=1_000_000,
        provider="gemini",
    )  # fmt: skip
    # (0.25 + 0.15 + 0.025) USD * 58 PHP * 100 = 2465 centavos
    assert cost_centavos(gemini) == Decimal("2465.0000")
    claude = AIUsageInfo(
        model="c", input_tokens=1_000_000, output_tokens=100_000, provider="anthropic"
    )
    # (4.00 + 2.00) USD * 58 * 100 = 34800 centavos
    assert cost_centavos(claude) == Decimal("34800.0000")


def test_gemini_key_is_hidden_in_repr():
    from app.core.config import Settings

    s = Settings(_env_file=None, APP_ENV="development", GEMINI_API_KEY="AIza-zz9leak")
    assert "zz9leak" not in repr(s) and s.GEMINI_API_KEY.get_secret_value() == "AIza-zz9leak"
