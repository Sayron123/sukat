"""AI chat with a scripted model: tool plumbing, roles, rate limit, exact numbers in the
table/chart, ai_usage logging, the tool-call and time limits, and the Claude adapter's
request shape. (Whether the real model picks the right tool is measured by
api/evals/chat, not here.)"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import anthropic
import httpx2
import pytest
from sqlalchemy import select, text

from app.ai.models import AIUsage
from app.ai.pricing import cost_centavos
from app.ai.schemas import AIUsageInfo
from app.core.config import settings
from app.insights import reports
from app.insights.chat_service import TOO_SLOW
from app.insights.chat_tools import NOT_ALLOWED
from app.insights.schemas import DateRange, MovementFilters
from tests.chat_helpers import ask, calls, last_results, say
from tests.conftest import auth_header, make_product


def _rid() -> str:
    return uuid.uuid4().hex


def _txn(api, headers, kind, product, qty, unit=None):
    body = {
        "client_request_id": _rid(),
        "type": kind,
        "lines": [{"product_id": product["id"], "qty": qty, "unit": unit or product["base_unit"]}],
    }
    res = api.post("/transactions", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _invite(api, manager, role, email):
    inv = api.post("/staff/invites", json={"email": email, "role": role}, headers=manager).json()
    token = api.post(
        "/staff/invites/accept",
        json={
            "accept_terms": True,
            "token": inv["token"],
            "password": "Staff-pass-1",
            "full_name": role.title(),
        },
    ).json()["access_token"]
    return auth_header(token)


@pytest.fixture
def shop(api, manager):
    """Cement (₱250/bag) and nails (₱92/kg, low), stocked and with a few sales today."""
    cement = make_product(api, manager, price_centavos=25000, low_stock_level="5")
    nails = make_product(
        api,
        manager,
        name='Common Wire Nail 4"',
        category="Nails & Screws",
        base_unit="kg",
        price_centavos=9200,
        low_stock_level="20",
        aliases=["pako 4"],
    )
    _txn(api, manager, "stock_in", cement, "40")
    _txn(api, manager, "stock_in", nails, "25")
    _txn(api, manager, "sale", cement, "3")
    _txn(api, manager, "sale", nails, "7.5")
    _txn(api, manager, "sale", cement, "1")
    store_id = UUID(api.get("/auth/me", headers=manager).json()["store_id"])
    return SimpleNamespace(cement=cement, nails=nails, store_id=store_id)


TODAY = {}  # tools default to today when no dates are given


# ---------- the right tool runs, with this store's data ----------


@pytest.mark.parametrize(
    ("question", "tool", "args", "data_tool"),
    [
        ("How much did we sell today?", "sales_summary", TODAY, "sales_summary"),
        ("Ano best seller ngayon?", "top_products", {"by": "qty"}, "top_products"),
        ("What's low on stock?", "low_stock", {}, "low_stock"),
        ("Ilan pa ang pako 4?", "find_product", {"query": "pako 4"}, "find_product"),
        ("Show today's stock changes", "stock_movements", {}, "stock_movements"),
    ],
)
def test_common_questions_run_their_tool(
    api, manager, shop, chat_model, question, tool, args, data_tool
):
    seen = {}

    def answer(kwargs):
        seen["result"] = last_results(kwargs)[0]
        return say("Here you go.")

    model = chat_model(calls((tool, args)), answer)
    res = ask(api, manager, question)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["answer"] == "Here you go." and out["tools_used"] == [tool]
    assert out["data"]["tool"] == data_tool
    assert "error" not in seen["result"]
    # The model got the question and every tool.
    assert model.calls[0]["items"][-1].text == question
    assert {t["name"] for t in model.calls[0]["tools"]} == {
        "sales_summary",
        "top_products",
        "low_stock",
        "stock_movements",
        "product_history",
        "find_product",
    }


def test_product_question_uses_find_then_history(api, manager, shop, chat_model):
    def history(kwargs):
        [found] = last_results(kwargs)
        return calls(("product_history", {"product_id": found["items"][0]["product_id"]}))

    chat_model(calls(("find_product", {"query": "cement"})), history, say("Sold 4 bags."))
    out = ask(api, manager, "Galaw ng semento?").json()
    assert out["tools_used"] == ["find_product", "product_history"]
    assert out["data"]["tool"] == "product_history"  # not the lookup step
    assert [r[2] for r in out["data"]["rows"]] == ["-1 bag", "-3 bag", "+40 bag"]


# ---------- roles ----------


def test_member_gets_not_allowed_for_top_products(api, manager, shop, chat_model):
    member = _invite(api, manager, "member", "m@example.com")
    seen = {}

    def answer(kwargs):
        seen["result"] = last_results(kwargs)[0]
        return say("That report is for managers and secretaries.")

    chat_model(calls(("top_products", {})), answer)
    out = ask(api, member, "best seller?").json()
    assert seen["result"] == {"error": NOT_ALLOWED}
    assert out["data"] is None
    # The member still sees the rest: sales, low stock.
    chat_model(calls(("sales_summary", {}), ("low_stock", {})), say("ok"))
    assert ask(api, member, "sales and low stock?").json()["tools_used"] == [
        "sales_summary",
        "low_stock",
    ]


def test_secretary_and_manager_get_top_products(api, manager, shop, chat_model):
    secretary = _invite(api, manager, "secretary", "s@example.com")
    for headers in (manager, secretary):
        chat_model(calls(("top_products", {})), say("Cement."))
        assert ask(api, headers, "best seller?").json()["data"]["tool"] == "top_products"


def test_role_comes_from_the_token_and_is_in_the_context(api, manager, shop, chat_model):
    member = _invite(api, manager, "member", "m2@example.com")
    model = chat_model(say("Hi"))
    ask(api, member, "hello")
    assert "The user's role is member." in model.calls[0]["context"]


# ---------- the numbers on screen are the report's numbers ----------


def _today() -> DateRange:
    day = reports.store_today()
    return DateRange(start=day, end=day)


def test_structured_numbers_match_the_report_functions(api, db, manager, shop, chat_model):
    sid = shop.store_id

    chat_model(calls(("sales_summary", {})), say("."))
    sales = ask(api, manager, "sales today").json()["data"]
    summary = reports.sales_summary(db, sid, _today())
    assert [Decimal(b["value"]) for b in sales["bars"]] == [
        Decimal(summary.previous.total_centavos),
        Decimal(summary.total_centavos),
    ]
    assert summary.total_centavos == 4 * 25000 + 69000  # 4 bags of cement + 7.5 kg of nails
    assert sales["range"] == {"start": str(_today().start), "end": str(_today().end)}
    assert sales["basis"] == "sales"

    for by in ("qty", "revenue"):
        chat_model(calls(("top_products", {"by": by})), say("."))
        bars = ask(api, manager, f"top by {by}").json()["data"]["bars"]
        top = reports.top_products(db, sid, _today(), 5, by)
        expected = [p.qty if by == "qty" else Decimal(p.revenue_centavos) for p in top.items]
        assert [Decimal(b["value"]) for b in bars] == expected
        assert [b["label"] for b in bars] == [p.name for p in top.items]

    chat_model(calls(("low_stock", {})), say("."))
    low = ask(api, manager, "low").json()["data"]
    report = reports.low_stock(db, sid)
    assert [r[0] for r in low["rows"]] == [i.name for i in report]
    assert low["rows"][0][1] == "17.5 kg"  # nails: 25 - 7.5

    chat_model(calls(("stock_movements", {})), say("."))
    table = ask(api, manager, "movements").json()["data"]
    page = reports.stock_movements(db, sid, MovementFilters())
    assert [r[3] for r in table["rows"]] == [
        f"{reports_qty(m.stock_after)} {m.base_unit}" for m in page.items[:10]
    ]
    assert table["range"] is None and table["basis"] is None  # all time


def reports_qty(q: Decimal) -> str:
    text = f"{q:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


# ---------- ai_usage ----------


def test_tokens_and_cost_are_logged_once_per_question(api, db, manager, shop, chat_model):
    chat_model(calls(("sales_summary", {})), say("₱..."))
    assert ask(api, manager, "sales?").status_code == 200
    [row] = db.scalars(select(AIUsage).where(AIUsage.feature == "chat")).all()
    both = AIUsageInfo(model="fake-chat", provider="gemini", input_tokens=2000, output_tokens=200)
    assert (row.store_id, row.model, row.tokens_in, row.tokens_out) == (
        shop.store_id,
        "fake-chat",
        2000,
        200,
    )
    assert row.cost_centavos == cost_centavos(both)


def test_no_open_transaction_while_the_model_thinks(api, db, manager, shop, chat_model):
    """After a tool round the connection is back in the pool before the next model call."""
    open_transactions = []

    def count_open(kwargs):
        db.rollback()  # a new transaction, so pg_stat_activity is read fresh
        open_transactions.append(
            db.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND state = 'idle in transaction' AND pid <> pg_backend_pid()"
                )
            )
        )
        db.rollback()
        return say("₱...")

    chat_model(calls(("sales_summary", {})), count_open)
    assert ask(api, manager, "sales?").status_code == 200
    assert open_transactions == [0]


def test_failed_question_still_logs_spent_tokens(api, db, manager, shop, chat_model):
    from app.ai.errors import AIChatError

    def fail(kwargs):
        raise AIChatError(
            "That took too long. Please try again.",
            retryable=True,
            usage=AIUsageInfo(model="fake-chat", provider="gemini", input_tokens=300),
        )

    chat_model(calls(("low_stock", {})), fail)
    res = ask(api, manager, "low?")
    assert res.status_code == 503
    assert res.json() == {
        "detail": "That took too long. Please try again.",
        "code": "chat_unavailable",
        "retryable": True,
    }
    [row] = db.scalars(select(AIUsage).where(AIUsage.feature == "chat")).all()
    assert row.tokens_in == 1000 + 300  # first call + the failed one


# ---------- rate limit ----------


def test_rate_limit_per_store(api, db, manager, signup, shop, chat_model, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_QUESTIONS_PER_HOUR", 3)
    # An old question (over an hour ago) doesn't count.
    db.add(
        AIUsage(
            store_id=shop.store_id,
            feature="chat",
            provider="gemini",
            model="m",
            tokens_in=0,
            tokens_out=0,
            cost_centavos=Decimal(0),
            created_at=datetime.now(UTC) - timedelta(minutes=61),
        )
    )
    db.commit()
    for _ in range(3):
        chat_model(say("ok"))
        assert ask(api, manager, "hi").status_code == 200
    model = chat_model(say("never"))
    res = ask(api, manager, "hi")
    assert res.status_code == 429
    body = res.json()
    assert body["code"] == "chat_rate_limited"
    assert "3 questions in the last hour" in body["detail"] and "ask again at" in body["detail"]
    assert 3500 < int(res.headers["retry-after"]) <= 3600
    assert model.calls == []  # refused before calling the AI
    # Scan reading isn't counted, and other stores have their own limit.
    other = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    chat_model(say("ok"))
    assert ask(api, other, "hi").status_code == 200


# ---------- limits and history ----------


def test_at_most_five_tool_calls_then_a_text_answer(api, manager, shop, chat_model, monkeypatch):
    burst = calls(("low_stock", {}), ("low_stock", {}), ("low_stock", {}))
    model = chat_model(burst, burst, say("Done."))
    out = ask(api, manager, "loop").json()
    assert out["answer"] == "Done." and len(out["tools_used"]) == 5
    # The 6th call got an error result, and the last call had to answer in text.
    second = model.calls[2]["items"][-1].results
    assert second[-1].is_error and "limit" in second[-1].content
    assert [c["allow_tools"] for c in model.calls] == [True, True, False]


def test_out_of_time_answers_without_calling_the_model(api, manager, chat_model, monkeypatch):
    monkeypatch.setattr(settings, "AI_CHAT_TIMEOUT_SECONDS", 1.0)
    model = chat_model(say("never"))
    assert ask(api, manager, "hi").json()["answer"] == TOO_SLOW
    assert model.calls == []


def test_only_the_last_ten_messages_are_sent(api, manager, chat_model):
    history = []
    for i in range(7):
        history += [
            {"role": "user", "content": f"q{i}"},
            {"role": "assistant", "content": f"a{i}"},
        ]
    model = chat_model(say("ok"))
    assert ask(api, manager, "latest", history).status_code == 200
    items = model.calls[0]["items"]
    assert len(items) <= 10 and type(items[0]).__name__ == "UserText"
    assert items[-1].text == "latest" and items[0].text == "q3"


def test_bad_conversations_are_refused(api, manager, chat_model):
    chat_model(say("never"))
    last_is_answer = {"messages": [{"role": "assistant", "content": "x"}]}
    too_long = {"messages": [{"role": "user", "content": "x" * 2001}]}
    for body in (last_is_answer, too_long, {"messages": []}):
        assert api.post("/insights/chat", json=body, headers=manager).status_code == 422


# ---------- the Claude adapter ----------


class FakeClient:
    """Stands in for anthropic.Anthropic: records the request, returns a canned reply."""

    def __init__(self, result):
        self.result = result
        self.requests = []
        self.options = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def with_options(self, **options):
        self.options.append(options)
        return self

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _reply(content, stop_reason="end_turn"):
    return SimpleNamespace(
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        content=content,
        usage=SimpleNamespace(
            input_tokens=900,
            output_tokens=40,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=2000,
        ),
    )


def test_claude_adapter_request_and_reply(monkeypatch):
    from app.ai.anthropic_chat import AnthropicChatModel
    from app.ai.base import UserText
    from app.insights.chat_tools import tool_specs

    tool_use = SimpleNamespace(type="tool_use", id="tu_1", name="low_stock", input={})
    thinking = SimpleNamespace(type="thinking", thinking="", signature="sig")
    client = FakeClient(_reply([thinking, tool_use], "tool_use"))
    turn = AnthropicChatModel(client).respond(  # type: ignore[arg-type]
        system="SYSTEM",
        context="Today is ...",
        items=[UserText("low?")],
        tools=tool_specs(),
        allow_tools=True,
        timeout=12.5,
    )
    req = client.requests[0]
    assert client.options == [{"timeout": 12.5}]
    assert req["model"] == settings.AI_MODEL
    assert req["output_config"] == {"effort": settings.AI_CHAT_EFFORT}
    assert req["tool_choice"] == {"type": "auto"}
    assert req["system"][0] == {
        "type": "text",
        "text": "SYSTEM",
        "cache_control": {"type": "ephemeral"},
    }
    assert req["system"][1] == {"type": "text", "text": "Today is ..."}
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert [t["name"] for t in req["tools"]] == [t["name"] for t in tool_specs()]
    assert turn.stop == "tool_use" and turn.tool_calls[0].name == "low_stock"
    assert turn.raw == [thinking, tool_use]  # sent back unchanged next time
    assert turn.usage.cache_read_tokens == 2000

    # Next call: the reasoning block goes back as it was; no tools allowed -> "none".
    from app.ai.base import ToolResult, ToolResults

    client.result = _reply([SimpleNamespace(type="text", text="Nails.")])
    turn2 = AnthropicChatModel(client).respond(  # type: ignore[arg-type]
        system="SYSTEM",
        context="Today is ...",
        items=[UserText("low?"), turn, ToolResults([ToolResult("tu_1", "{}")])],
        tools=tool_specs(),
        allow_tools=False,
        timeout=10,
    )
    req2 = client.requests[1]
    assert req2["tool_choice"] == {"type": "none"}
    assert req2["messages"][1] == {"role": "assistant", "content": [thinking, tool_use]}
    assert req2["messages"][2]["content"][0]["type"] == "tool_result"
    assert turn2.text == "Nails." and turn2.stop == "end"


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")), True),
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
def test_claude_adapter_errors(error, retryable):
    from app.ai.anthropic_chat import AnthropicChatModel
    from app.ai.base import UserText
    from app.ai.errors import AIChatError

    with pytest.raises(AIChatError) as e:
        AnthropicChatModel(FakeClient(error)).respond(  # type: ignore[arg-type]
            system="S", context="C", items=[UserText("q")], tools=[], allow_tools=True, timeout=5
        )
    assert e.value.retryable is retryable


def test_claude_adapter_without_api_key_says_not_set_up():
    from app.ai.anthropic_chat import AnthropicChatModel
    from app.ai.base import UserText
    from app.ai.errors import AIChatError

    no_key = TypeError('"Could not resolve authentication method. Expected one of api_key"')
    with pytest.raises(AIChatError) as e:
        AnthropicChatModel(FakeClient(no_key)).respond(  # type: ignore[arg-type]
            system="S", context="C", items=[UserText("q")], tools=[], allow_tools=True, timeout=5
        )
    assert str(e.value) == "The assistant is not set up yet." and e.value.retryable is False
