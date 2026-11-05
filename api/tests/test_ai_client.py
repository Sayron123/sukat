"""AI client tests with a fake Anthropic client: no network, no API key."""

import base64
import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.ai.anthropic_reader import AnthropicVisionReader, _system_prompt
from app.ai.convert import catalog_refs, catalog_text
from app.ai.errors import AIReadError
from app.ai.pricing import cost_centavos
from app.ai.schemas import RAW_RESULT_SCHEMA, AIUsageInfo, CatalogConversion, CatalogEntry, RawLine
from app.core.config import settings

CEMENT = CatalogEntry(
    uuid.UUID("00000000-0000-0000-0000-0000000000c1"),
    "Portland Cement 40kg",
    "bag",
    ("sem", "semento"),
    (CatalogConversion("kg", Decimal("0.025")),),
)
NAILS = CatalogEntry(
    uuid.UUID("00000000-0000-0000-0000-0000000000a1"),
    'Common Wire Nail 4"',
    "kg",
    ("pako 4",),
    (CatalogConversion("box", Decimal("25")),),
)
CATALOG = [NAILS, CEMENT]  # P1 = nails, P2 = cement (sorted by name)


def _line(**kw):
    base = {
        "raw_text": "10 sem",
        "product_ref": "P2",
        "suggested_new_name": None,
        "qty": 10,
        "unit": "bag",
        "unit_price": 250.5,
        "line_total": None,
        "confidence": 0.97,
    }
    base.update(kw)
    return base


def _response(lines=None, *, text=None, stop_reason="end_turn"):
    body = text if text is not None else json.dumps({"lines": lines or []})
    return SimpleNamespace(
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=body),
        ],
        usage=SimpleNamespace(
            input_tokens=1200,
            output_tokens=300,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=5000,
        ),
    )


class FakeClient:
    def __init__(self, result):
        self.calls = []
        self._result = result
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _read(result, catalog=CATALOG):
    client = FakeClient(result)
    out = AnthropicVisionReader(client).read_list(b"\xff\xd8img", "image/jpeg", catalog, "stock_in")
    return out, client.calls[0]


def test_request_shape():
    _, req = _read(_response([_line()]))
    assert req["model"] == settings.AI_MODEL
    assert req["output_config"]["format"] == {"type": "json_schema", "schema": RAW_RESULT_SCHEMA}
    assert req["output_config"]["effort"] == settings.AI_EFFORT
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    prompt, products = req["system"]
    assert prompt["text"] == _system_prompt() and "cache_control" not in prompt
    assert products["cache_control"] == {"type": "ephemeral"}  # product list is cached
    assert (
        "P2 | Portland Cement 40kg | unit: bag | also: sem, semento | 1 kg = 0.025 bag"
        in (products["text"])
    )
    image = req["messages"][0]["content"][0]
    assert image["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(image["source"]["data"]) == b"\xff\xd8img"
    assert "stock in" in req["messages"][0]["content"][1]["text"]


def test_fallback_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "AI_REFUSAL_FALLBACK", False)
    _, req = _read(_response([_line()]))
    assert "fallbacks" not in req and "betas" not in req


def test_lines_are_mapped_to_product_ids_and_centavos():
    result, _ = _read(
        _response(
            [
                _line(),
                _line(
                    raw_text="2 bx pako 4",
                    product_ref="p1",
                    qty=2,
                    unit="BX.",
                    unit_price=None,
                    line_total=1700,
                ),
                _line(
                    raw_text="5 bakal 16mm",
                    product_ref=None,
                    suggested_new_name="Deformed Bar 16mm x 6m",
                    unit="pcs",
                    unit_price=None,
                    confidence=1.4,
                ),
                _line(raw_text="?? kawad", product_ref="P99", qty=0, confidence=-1),
            ]
        )
    )
    cement, nails, new, bad = result.lines
    assert cement.product_id == CEMENT.product_id and cement.unit_price_centavos == 25050
    assert cement.qty == Decimal("10")
    assert nails.product_id == NAILS.product_id
    assert nails.unit == "box"  # "BX." normalized
    assert nails.unit_price_centavos == 85000  # 1700 / 2, from the line total
    assert new.product_id is None and new.suggested_new_name == "Deformed Bar 16mm x 6m"
    assert new.unit == "pc" and new.confidence == 1.0  # clamped
    assert bad.product_id is None  # P99 isn't a real ref
    assert bad.qty is None and bad.confidence == 0.0
    assert result.usage.tokens_in == 6200 and result.usage.output_tokens == 300


def test_suggested_name_is_dropped_when_matched():
    result, _ = _read(_response([_line(suggested_new_name="Cement")]))
    assert result.lines[0].suggested_new_name is None


def test_refusal_is_not_retryable_and_keeps_usage():
    with pytest.raises(AIReadError) as e:
        _read(_response(stop_reason="refusal"))
    assert e.value.retryable is False and e.value.usage.output_tokens == 300


def test_invalid_json_is_retryable_and_keeps_usage():
    with pytest.raises(AIReadError) as e:
        _read(_response(text="not json"))
    assert e.value.retryable is True and e.value.usage is not None
    with pytest.raises(AIReadError):
        _read(_response(text=json.dumps({"lines": [{"raw_text": "x"}]})))


def test_max_tokens_is_reported():
    with pytest.raises(AIReadError) as e:
        _read(_response([_line()], stop_reason="max_tokens"))
    assert "too long" in str(e.value)


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (anthropic.APITimeoutError(httpx2.Request("POST", "https://x")), True),
        (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")), True),
        (
            anthropic.InternalServerError(
                "boom",
                response=httpx2.Response(500, request=httpx2.Request("POST", "https://x")),
                body=None,
            ),
            True,
        ),
        (
            anthropic.BadRequestError(
                "bad",
                response=httpx2.Response(400, request=httpx2.Request("POST", "https://x")),
                body=None,
            ),
            False,
        ),
    ],
)
def test_api_errors(error, retryable):
    with pytest.raises(AIReadError) as e:
        _read(error)
    assert e.value.retryable is retryable


def test_real_client_has_timeout_and_one_retry():
    reader = AnthropicVisionReader()
    assert reader.client.max_retries == settings.AI_MAX_RETRIES == 1
    assert reader.client.timeout == settings.AI_TIMEOUT_SECONDS


def test_schema_matches_pydantic_model():
    item = RAW_RESULT_SCHEMA["properties"]["lines"]["items"]
    assert set(item["properties"]) == set(RawLine.model_fields) == set(item["required"])


def test_catalog_text_is_stable_for_caching():
    a = catalog_text(catalog_refs([CEMENT, NAILS]))
    b = catalog_text(catalog_refs([NAILS, CEMENT]))
    assert a == b
    assert "no products" in catalog_text([])


def test_cost_centavos():
    usage = AIUsageInfo(
        model="m", input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=1_000_000
    )
    # (4.00 + 2.00 + 0.20) USD * 58 PHP * 100 = 35960 centavos
    assert cost_centavos(usage) == Decimal("35960.0000")


def test_missing_unit_is_not_guessed_from_the_product():
    # Audit H1: an empty unit stays empty (the review then asks staff for it).
    result, _ = _read(_response([_line(unit="")]))
    line = result.lines[0]
    assert line.product_id == CEMENT.product_id and line.unit == ""
    assert "If no unit is written, return an empty string" in _system_prompt()
