import base64
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import httpx2
import pytest
from google import genai
from google.genai import types
from pydantic import ValidationError
from sqlalchemy import select, text

from app.ai.base import AssistantText, ToolResult, ToolResults, UserText
from app.ai.budget import month_bounds
from app.ai.errors import AIChatError, AIReadError
from app.ai.gemini_chat import GeminiChatModel
from app.ai.gemini_reader import GeminiScanAI
from app.ai.models import AIUsage
from app.ai.pricing import cost_centavos
from app.ai.provider import (
    get_backup_chat_model,
    get_backup_vision_reader,
    get_chat_model,
    get_scan_ai,
    get_vision_reader,
)
from app.ai.scan_output import READ_REQUEST
from app.ai.scan_pipeline import MultiStepReader
from app.ai.schemas import READ_SCHEMA, AIUsageInfo, CatalogEntry
from app.core.config import Settings, settings
from app.insights import chat_service
from app.insights.chat_service import TOO_SLOW
from app.insights.chat_tools import tool_specs
from app.inventory.scan_service import stale_after_seconds
from app.main import app
from tests.chat_helpers import ScriptedModel, ask, calls, say
from tests.conftest import FakeReader, auth_header, upload_photo

SPENT_TOKENS = AIUsageInfo(model="gemini-x", provider="gemini", input_tokens=500, output_tokens=10)


def _invite(api, manager, role, email):
    invite = api.post("/staff/invites", json={"email": email, "role": role}, headers=manager).json()
    token = api.post(
        "/staff/invites/accept",
        json={
            "accept_terms": True,
            "token": invite["token"],
            "password": "Staff-pass-1",
            "full_name": role.title(),
        },
    ).json()["access_token"]
    return auth_header(token)


def _store_id(api, headers):
    return api.get("/auth/me", headers=headers).json()["store_id"]


def _spend(db, store_id, centavos, created_at=None, feature="scan_read"):
    db.add(
        AIUsage(
            store_id=store_id,
            feature=feature,
            provider="gemini",
            model="m",
            tokens_in=1,
            tokens_out=1,
            cost_centavos=Decimal(centavos),
            created_at=created_at or datetime.now(UTC),
        )
    )
    db.commit()


def _rows(db, feature=None):
    db.rollback()
    query = select(AIUsage).order_by(AIUsage.created_at)
    if feature:
        query = query.where(AIUsage.feature == feature)
    return list(db.scalars(query))


@pytest.fixture
def backup_reader(api):
    fake = FakeReader(provider="anthropic", model="fake-anthropic")
    app.dependency_overrides[get_backup_vision_reader] = lambda: fake
    return fake


@pytest.fixture
def backup_chat(api):
    def install(*steps):
        model = ScriptedModel(*steps)
        app.dependency_overrides[get_backup_chat_model] = lambda: model
        return model

    return install


def _backup_say(answer):
    usage = AIUsageInfo(model="claude-x", provider="anthropic", input_tokens=70, output_tokens=7)
    return replace(say(answer), usage=usage)


def _scan(api, headers, storage):
    key = upload_photo(api, headers, storage)
    return api.post("/scans", json={"photo_key": key}, headers=headers)


@pytest.mark.parametrize(
    "message",
    [
        "Reading took too long. Please try again.",
        "The reader is busy. Please try again.",
        "The reader had a problem. Please try again.",
    ],
)
def test_scan_uses_backup_when_main_fails_and_logs_who_answered(
    api, db, manager, storage, reader, backup_reader, message
):
    reader.error = AIReadError(message, retryable=True)
    res = _scan(api, manager, storage).json()
    assert res["status"] == "read" and res["model"] == "fake-anthropic"
    assert len(reader.calls) == len(backup_reader.calls) == 1
    assert [row.provider for row in _rows(db)] == ["anthropic"]


def test_scan_invalid_answer_uses_backup_and_logs_both_costs(
    api, db, manager, storage, reader, backup_reader
):
    reader.error = AIReadError(
        "The reader gave an unexpected answer.", retryable=True, usage=SPENT_TOKENS
    )
    assert _scan(api, manager, storage).json()["status"] == "read"
    assert sorted(row.provider for row in _rows(db)) == ["anthropic", "gemini"]


@pytest.mark.parametrize("message", ["This photo could not be read.", "The list is too long."])
def test_scan_does_not_use_backup_for_permanent_failures(
    api, manager, storage, reader, backup_reader, message
):
    reader.error = AIReadError(message, retryable=False)
    assert _scan(api, manager, storage).json()["status"] == "failed"
    assert backup_reader.calls == []


def test_scan_tries_backup_once_and_reports_failure_when_both_fail(
    api, db, manager, storage, reader, backup_reader
):
    reader.error = AIReadError("main down", retryable=True, usage=SPENT_TOKENS)
    backup_reader.error = AIReadError(
        "backup down",
        retryable=True,
        usage=AIUsageInfo(model="claude-x", provider="anthropic", input_tokens=9),
    )
    res = _scan(api, manager, storage).json()
    assert res["status"] == "failed" and res["error_message"] == "backup down"
    assert len(reader.calls) == len(backup_reader.calls) == 1
    assert sorted(row.provider for row in _rows(db)) == ["anthropic", "gemini"]


def test_retry_also_uses_backup(api, manager, storage, reader):
    reader.error = AIReadError("down", retryable=True)
    failed = _scan(api, manager, storage).json()
    backup = FakeReader(provider="anthropic", model="fake-anthropic")
    app.dependency_overrides[get_backup_vision_reader] = lambda: backup
    res = api.post(f"/scans/{failed['id']}/retry", headers=manager).json()
    assert res["status"] == "read" and len(backup.calls) == 1


def test_chat_uses_backup_and_logs_who_answered(api, db, manager, chat_model, backup_chat):
    def fail(kwargs):
        raise AIChatError("busy", retryable=True, usage=SPENT_TOKENS)

    main = chat_model(calls(("low_stock", {})), fail)
    backup = backup_chat(_backup_say("From backup"))
    assert ask(api, manager, "low?").json()["answer"] == "From backup"
    assert len(backup.calls) == 1 and len(backup.calls[0]["items"]) == 1
    assert len(main.calls) == 2
    [answered] = _rows(db, "chat")
    assert (answered.provider, answered.model, answered.tokens_in) == ("anthropic", "claude-x", 70)
    [failed] = _rows(db, chat_service.FAILED_ATTEMPT_FEATURE)
    assert failed.provider == "gemini" and failed.tokens_in == 1000 + 500


def test_chat_fallback_counts_as_one_question(api, manager, chat_model, backup_chat, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_QUESTIONS_PER_HOUR", 1)

    def fail(kwargs):
        raise AIChatError("busy", retryable=True, usage=SPENT_TOKENS)

    chat_model(fail)
    backup_chat(_backup_say("ok"))
    assert ask(api, manager, "one").status_code == 200
    assert ask(api, manager, "two").json()["code"] == "chat_rate_limited"


def test_chat_uses_backup_when_main_runs_out_of_time(
    api, db, manager, chat_model, backup_chat, monkeypatch
):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(chat_service, "time", SimpleNamespace(monotonic=lambda: clock.now))

    def slow(kwargs):
        clock.now += settings.AI_CHAT_TIMEOUT_SECONDS
        return calls(("low_stock", {}))

    chat_model(slow)
    backup_chat(_backup_say("Made it"))
    assert ask(api, manager, "low?").json()["answer"] == "Made it"
    assert _rows(db, "chat")[0].provider == "anthropic"


def test_chat_without_backup_still_says_too_slow(api, manager, chat_model, monkeypatch):
    monkeypatch.setattr(settings, "AI_CHAT_TIMEOUT_SECONDS", 1.0)
    assert ask(api, manager, "hi").json()["answer"] == TOO_SLOW


def test_chat_does_not_use_backup_for_permanent_errors(api, manager, chat_model, backup_chat):
    def fail(kwargs):
        raise AIChatError("not set up", retryable=False)

    chat_model(fail)
    backup = backup_chat(_backup_say("never"))
    res = ask(api, manager, "hi")
    assert res.status_code == 503 and backup.calls == []


def test_chat_reports_failure_when_both_fail(api, db, manager, chat_model, backup_chat):
    def main_fail(kwargs):
        raise AIChatError("main", retryable=True)

    def backup_fail(kwargs):
        raise AIChatError(
            "backup",
            retryable=True,
            usage=AIUsageInfo(model="claude-x", provider="anthropic", input_tokens=33),
        )

    chat_model(main_fail)
    backup_chat(backup_fail)
    res = ask(api, manager, "hi")
    assert res.status_code == 503 and res.json()["detail"] == "backup"
    assert _rows(db, "chat")[0].provider == "anthropic"


def test_backup_is_priced_with_backup_prices(monkeypatch):
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "AI_PRICE_INPUT_PER_MTOK_USD", Decimal("1"))
    monkeypatch.setattr(settings, "AI_FALLBACK_PRICE_INPUT_PER_MTOK_USD", Decimal("10"))
    monkeypatch.setattr(settings, "USD_TO_PHP", Decimal("50"))
    main = AIUsageInfo(model="m", provider="gemini", input_tokens=1_000_000)
    backup = AIUsageInfo(model="b", provider="anthropic", input_tokens=1_000_000, backup=True)
    assert cost_centavos(main) == Decimal("5000.0000")
    assert cost_centavos(backup) == Decimal("50000.0000")


def test_budget_blocks_scan_before_calling_ai(api, db, manager, storage, reader, monkeypatch):
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 100)
    _spend(db, _store_id(api, manager), 100)
    res = _scan(api, manager, storage)
    body = res.json()
    assert res.status_code == 429 and body["code"] == "ai_budget_reached"
    assert "₱1.00" in body["detail"] and "will work again" in body["detail"]
    assert int(res.headers["retry-after"]) > 0
    assert reader.calls == []
    assert db.scalar(text("SELECT count(*) FROM scans")) == 0


def test_budget_blocks_scan_retry(api, db, manager, storage, reader, monkeypatch):
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 100)
    reader.error = AIReadError("down", retryable=True)
    failed = _scan(api, manager, storage).json()
    _spend(db, _store_id(api, manager), 100)
    res = api.post(f"/scans/{failed['id']}/retry", headers=manager)
    assert res.status_code == 429 and len(reader.calls) == 1


def test_repeated_photo_is_free_after_budget_is_reached(
    api, db, manager, storage, reader, monkeypatch
):
    key = upload_photo(api, manager, storage)
    first = api.post("/scans", json={"photo_key": key}, headers=manager).json()
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 1)
    _spend(db, _store_id(api, manager), 1)
    again = api.post("/scans", json={"photo_key": key}, headers=manager)
    assert again.status_code == 200 and again.json()["id"] == first["id"]


def test_budget_blocks_chat_before_calling_ai(api, db, manager, chat_model, monkeypatch):
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 100)
    store_id = _store_id(api, manager)
    _spend(db, store_id, 99, feature="chat")
    _spend(db, store_id, 1, feature=chat_service.FAILED_ATTEMPT_FEATURE)
    model = chat_model(say("never"))
    res = ask(api, manager, "hi")
    assert res.status_code == 429 and res.json()["code"] == "ai_budget_reached"
    assert model.calls == []


def test_budget_under_the_limit_is_allowed(api, db, manager, chat_model, monkeypatch):
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 100)
    _spend(db, _store_id(api, manager), "99.9999")
    chat_model(say("yes"))
    assert ask(api, manager, "hi").status_code == 200


def test_store_limit_overrides_the_default_including_zero(
    api, db, manager, signup, chat_model, monkeypatch
):
    store_id = _store_id(api, manager)
    db.execute(
        text("UPDATE stores SET ai_monthly_budget_centavos = 0 WHERE id = :s"), {"s": store_id}
    )
    db.commit()
    model = chat_model(say("never"))
    assert ask(api, manager, "hi").status_code == 429 and model.calls == []
    other = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    chat_model(say("ok"))
    assert ask(api, other, "hi").status_code == 200


def test_one_stores_spending_does_not_block_another(
    api, db, manager, signup, chat_model, monkeypatch
):
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 100)
    _spend(db, _store_id(api, manager), 500)
    other = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    chat_model(say("ok"))
    assert ask(api, other, "hi").status_code == 200


def test_last_month_does_not_count(api, db, manager, chat_model, monkeypatch):
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 100)
    start, _ = month_bounds()
    _spend(db, _store_id(api, manager), 500, created_at=start - timedelta(seconds=1))
    chat_model(say("ok"))
    assert ask(api, manager, "hi").status_code == 200


def test_month_uses_store_time():
    just_before = datetime(2026, 11, 30, 15, 59, tzinfo=UTC)
    just_after = datetime(2026, 11, 30, 16, 0, tzinfo=UTC)
    assert month_bounds(just_before)[0].month == 11
    start, end = month_bounds(just_after)
    assert (start.month, start.day, start.hour) == (12, 1, 0)
    assert (end.year, end.month, end.day) == (2027, 1, 1)


def test_manager_sees_this_months_usage(api, db, manager, monkeypatch):
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 1000)
    store_id = _store_id(api, manager)
    _spend(db, store_id, "100.1")
    _spend(db, store_id, "20", feature="scan_match")
    _spend(db, store_id, "50.5", feature="chat")
    out = api.get("/insights/ai-usage", headers=manager).json()
    assert out["budget_centavos"] == 1000 and out["spent_centavos"] == 171
    assert out["remaining_centavos"] == 829
    assert (out["scans_centavos"], out["chat_centavos"]) == (121, 50)
    assert out["scans_centavos"] + out["chat_centavos"] == out["spent_centavos"]
    assert out["reached"] is False


def test_usage_shows_when_limit_is_reached(api, db, manager, monkeypatch):
    monkeypatch.setattr(settings, "AI_MONTHLY_BUDGET_CENTAVOS", 100)
    _spend(db, _store_id(api, manager), 150)
    out = api.get("/insights/ai-usage", headers=manager).json()
    assert out["reached"] is True and out["remaining_centavos"] == 0


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_only_managers_see_usage(api, manager, role):
    staff = _invite(api, manager, role, f"{role}@example.com")
    assert api.get("/insights/ai-usage", headers=staff).status_code == 403


def test_provider_setting_picks_gemini_or_claude(monkeypatch):
    from app.ai.anthropic_chat import AnthropicChatModel
    from app.ai.anthropic_reader import AnthropicScanAI

    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "AI_MODEL", "main-model")
    monkeypatch.setattr(settings, "AI_FALLBACK_MODEL", "backup-model")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY)
    get_scan_ai.cache_clear()
    reader = get_vision_reader.__wrapped__()
    get_scan_ai.cache_clear()
    chat = get_chat_model.__wrapped__()
    backup_reader = get_backup_vision_reader.__wrapped__()
    backup_chat = get_backup_chat_model.__wrapped__()
    assert isinstance(reader, MultiStepReader) and isinstance(reader.ai, GeminiScanAI)
    assert reader.ai.model == "main-model" and reader.ai.max_retries == 0
    assert isinstance(chat, GeminiChatModel) and chat.model == "main-model"
    assert isinstance(backup_reader, MultiStepReader)
    assert isinstance(backup_reader.ai, AnthropicScanAI)
    assert backup_reader.ai.model == "backup-model" and backup_reader.ai.client.max_retries == 0
    assert isinstance(backup_chat, AnthropicChatModel) and backup_chat.model == "backup-model"


def test_no_backup_when_turned_off():
    assert get_vision_reader.__wrapped__().backup is None
    assert get_backup_vision_reader.__wrapped__() is None
    assert get_backup_chat_model.__wrapped__() is None


def test_backup_must_be_a_different_provider_or_model():
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="development",
            EMAIL_BACKEND="console",
            AI_PROVIDER="gemini",
            AI_MODEL="gemini-3.1-flash-lite",
            AI_FALLBACK_PROVIDER="gemini",
            AI_FALLBACK_MODEL="gemini-3.1-flash-lite",
        )
    same_provider = Settings(
        APP_ENV="development",
        EMAIL_BACKEND="console",
        AI_PROVIDER="gemini",
        AI_MODEL="gemini-3.1-flash-lite",
        AI_FALLBACK_PROVIDER="gemini",
        AI_FALLBACK_MODEL="gemini-3.5-flash-lite",
    )
    assert same_provider.has_ai_fallback


def test_a_gemini_backup_reader_and_chat_use_the_backup_model_and_prices(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "AI_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setattr(settings, "AI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
    get_scan_ai.cache_clear()
    main = get_vision_reader.__wrapped__()
    get_scan_ai.cache_clear()
    backup = get_backup_vision_reader.__wrapped__()
    backup_chat = get_backup_chat_model.__wrapped__()
    assert isinstance(main.ai, GeminiScanAI) and main.ai.backup is False
    assert main.ai.model == "gemini-3.1-flash-lite" and main.ai.max_retries == 0
    assert isinstance(backup.ai, GeminiScanAI) and backup.ai.backup is True
    assert backup.ai.model == "gemini-3.5-flash-lite"
    assert main.backup is backup.ai
    assert isinstance(backup_chat, GeminiChatModel) and backup_chat.backup is True
    assert backup_chat.model == "gemini-3.5-flash-lite"


def test_stale_time_covers_both_providers(monkeypatch):
    monkeypatch.setattr(settings, "AI_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 1)
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "none")
    assert stale_after_seconds() == 100
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 3)
    monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "anthropic")
    assert stale_after_seconds() == 90


def test_default_model_and_prices_match_googles_price_list():
    fields = Settings.model_fields
    assert fields["AI_PROVIDER"].default == "gemini"
    assert fields["AI_MODEL"].default == "gemini-3.1-flash-lite"
    assert fields["AI_PRICE_INPUT_PER_MTOK_USD"].default == Decimal("0.25")
    assert fields["AI_PRICE_OUTPUT_PER_MTOK_USD"].default == Decimal("1.50")
    assert fields["AI_PRICE_CACHE_READ_PER_MTOK_USD"].default == Decimal("0.025")
    assert fields["AI_GEMINI_THINKING_LEVEL"].default == "minimal"


LINE = {
    "raw_text": "2 bags Cement",
    "qty_text": "2",
    "unit_text": "bag",
    "price_text": "250.50",
    "total_text": None,
    "confidence": 0.9,
}
USAGE_JSON = {
    "promptTokenCount": 1000,
    "cachedContentTokenCount": 400,
    "candidatesTokenCount": 50,
    "thoughtsTokenCount": 25,
}


def _api_reply(parts, finish="STOP", extra=None):
    return {
        "candidates": [
            {"content": {"role": "model", "parts": parts}, "finishReason": finish, "index": 0}
        ],
        "usageMetadata": USAGE_JSON,
        "modelVersion": "gemini-3.1-flash-lite",
        **(extra or {}),
    }


class FakeGoogle:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        transport = httpx2.MockTransport(self._handle)
        self.client = genai.Client(
            api_key="test-key",
            http_options=types.HttpOptions(httpx_client=httpx2.Client(transport=transport)),
        )

    def _handle(self, request):
        self.requests.append(json.loads(request.content))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx2.Response(reply, json={"error": {"code": reply, "message": "x"}})
        return httpx2.Response(200, json=reply)


def _chat(fake, items=None, tools=None, allow_tools=True, timeout=12.5):
    return GeminiChatModel(fake.client, model="gemini-test").respond(
        system="SYSTEM",
        context="Today is X",
        items=items or [UserText("low?")],
        tools=tool_specs() if tools is None else tools,
        allow_tools=allow_tools,
        timeout=timeout,
    )


def _read(fake, scan_type="stock_in"):
    product = CatalogEntry(
        product_id=UUID("00000000-0000-0000-0000-0000000000c1"),
        name="Cement",
        base_unit="bag",
    )
    reader = MultiStepReader(GeminiScanAI(fake.client, model="gemini-test", max_retries=0))
    return reader.read_list(b"\xff\xd8img", "image/jpeg", [product], scan_type)


def test_gemini_chat_request_and_tool_reply():
    signature = base64.b64encode(b"opaque-signature").decode()
    call_part = {
        "functionCall": {"id": "fc_1", "name": "low_stock", "args": {}},
        "thoughtSignature": signature,
    }
    fake = FakeGoogle(_api_reply([call_part]), _api_reply([{"text": "Nails."}]))
    turn = _chat(fake)
    request = fake.requests[0]
    assert request["systemInstruction"]["parts"][0]["text"] == "SYSTEM\n\nToday is X"
    assert "MINIMAL" in request["generationConfig"]["thinkingConfig"].values()
    assert request["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"
    declared = request["tools"][0]["functionDeclarations"]
    assert [d["name"] for d in declared] == [t["name"] for t in tool_specs()]
    assert tool_specs()[0]["input_schema"] in declared[0].values()
    assert turn.stop == "tool_use" and turn.tool_calls[0].name == "low_stock"
    assert turn.usage.provider == "gemini"
    assert (turn.usage.input_tokens, turn.usage.cache_read_tokens) == (600, 400)
    assert turn.usage.output_tokens == 75

    items = [
        AssistantText("Hello"),
        UserText("low?"),
        turn,
        ToolResults([ToolResult("fc_1", '{"count": 2}')]),
    ]
    final = _chat(fake, items=items, allow_tools=False)
    second = fake.requests[1]
    assert second["toolConfig"]["functionCallingConfig"]["mode"] == "NONE"
    assert [c["role"] for c in second["contents"]] == ["model", "user", "model", "user"]
    assert second["contents"][2]["parts"][0]["thoughtSignature"] == signature
    assert second["contents"][3]["parts"][0]["functionResponse"] == {
        "id": "fc_1",
        "name": "low_stock",
        "response": {"output": {"count": 2}},
    }
    assert final.text == "Nails." and final.stop == "end"


def test_gemini_tool_error_is_sent_as_error():
    call = {"functionCall": {"name": "low_stock", "args": {}}}
    fake = FakeGoogle(_api_reply([call]), _api_reply([{"text": "ok"}]))
    turn = _chat(fake)
    assert turn.tool_calls[0].id.startswith("local-call-")
    result = ToolResult(turn.tool_calls[0].id, '{"error": "no"}', is_error=True)
    _chat(fake, items=[UserText("q"), turn, ToolResults([result])])
    response = fake.requests[1]["contents"][2]["parts"][0]["functionResponse"]
    assert "id" not in response
    assert response["response"] == {"error": {"error": "no"}}


def test_gemini_chat_hides_reasoning_text():
    fake = FakeGoogle(_api_reply([{"text": "private", "thought": True}, {"text": "Answer"}]))
    assert _chat(fake).text == "Answer"


@pytest.mark.parametrize(
    ("finish", "stop"),
    [("SAFETY", "refusal"), ("PROHIBITED_CONTENT", "refusal"), ("MAX_TOKENS", "max_tokens")],
)
def test_gemini_chat_stop_reasons(finish, stop):
    assert _chat(FakeGoogle(_api_reply([{"text": "x"}], finish))).stop == stop


def test_gemini_chat_blocked_prompt_is_a_refusal():
    reply = {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": USAGE_JSON}
    assert _chat(FakeGoogle(reply)).stop == "refusal"


@pytest.mark.parametrize("finish", ["MALFORMED_FUNCTION_CALL", "OTHER"])
def test_gemini_chat_broken_output_can_use_backup(finish):
    with pytest.raises(AIChatError) as e:
        _chat(FakeGoogle(_api_reply([], finish)))
    assert e.value.retryable is True and e.value.usage.output_tokens == 75


@pytest.mark.parametrize(
    ("reply", "retryable"),
    [
        (httpx2.ReadTimeout("slow"), True),
        (httpx2.ConnectError("down"), True),
        (429, True),
        (500, True),
        (503, True),
        (400, False),
        (401, False),
    ],
)
def test_gemini_errors(reply, retryable):
    with pytest.raises(AIChatError) as chat_error:
        _chat(FakeGoogle(reply))
    assert chat_error.value.retryable is retryable
    with pytest.raises(AIReadError) as read_error:
        _read(FakeGoogle(reply))
    assert read_error.value.retryable is retryable


def test_gemini_without_key_says_not_set_up(monkeypatch):
    monkeypatch.setattr("app.ai.gemini_chat.make_client", lambda: None)
    with pytest.raises(AIChatError) as e:
        GeminiChatModel().respond(
            system="S", context="C", items=[UserText("q")], tools=[], allow_tools=True, timeout=5
        )
    assert e.value.retryable is False


def test_gemini_reader_request_and_result():
    fake = FakeGoogle(_api_reply([{"text": json.dumps({"lines": [LINE]})}]))
    result = _read(fake, "sale")
    request = fake.requests[0]
    assert request["generationConfig"]["responseMimeType"] == "application/json"
    assert request["generationConfig"]["responseJsonSchema"] == READ_SCHEMA
    assert "MINIMAL" in request["generationConfig"]["thinkingConfig"].values()
    image, prompt = request["contents"][0]["parts"]
    assert base64.urlsafe_b64decode(image["inlineData"]["data"]) == b"\xff\xd8img"
    assert prompt["text"] == READ_REQUEST
    assert result.lines[0].unit_price_centavos == 25050
    assert result.usage.provider == "gemini"
    assert result.lines[0].unit == "bag"


@pytest.mark.parametrize(
    "text_reply", ["not json", json.dumps({"lines": [{"raw_text": "missing fields"}]}), "[]"]
)
def test_gemini_invalid_output_can_use_backup_and_keeps_cost(text_reply):
    with pytest.raises(AIReadError) as e:
        _read(FakeGoogle(_api_reply([{"text": text_reply}])))
    assert e.value.retryable is True and e.value.usage.provider == "gemini"


def test_gemini_reader_blocked_and_too_long_are_permanent():
    for finish, message in (("SAFETY", "could not be read"), ("MAX_TOKENS", "too long")):
        with pytest.raises(AIReadError) as e:
            _read(FakeGoogle(_api_reply([{"text": ""}], finish)))
        assert message in str(e.value) and e.value.retryable is False


def test_claude_reader_without_key_says_not_set_up():
    from app.ai.anthropic_reader import AnthropicScanAI

    def no_key(**_):
        raise TypeError('"Could not resolve authentication method."')

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=no_key)))
    with pytest.raises(AIReadError) as e:
        AnthropicScanAI(client).read_photo(b"x", "image/jpeg")  # type: ignore[arg-type]
    assert e.value.retryable is False
