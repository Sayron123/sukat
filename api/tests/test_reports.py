"""Phase 5 reports: Manila day boundaries, voided sales, low stock, history, stock check,
roles and tenant isolation."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.ai.errors import AIReadError
from app.insights import reports
from app.insights.schemas import DateRange
from app.inventory.models import Scan, StockMovement, Transaction
from app.products.models import Product
from tests.conftest import auth_header, make_product, scan_line, upload_photo

DAY = date(2026, 3, 10)  # in the past, so "now" (fixture rows) never falls on it


def _rid() -> str:
    return uuid.uuid4().hex


def _txn(api, headers, txn_type, lines, **extra):
    body = {"client_request_id": _rid(), "type": txn_type, "lines": lines, **extra}
    res = api.post("/transactions", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _at(db, txn_id, when: datetime) -> None:
    """Move a transaction (and its movements) to another time, for date tests."""
    db.execute(update(Transaction).where(Transaction.id == txn_id).values(created_at=when))
    db.execute(
        update(StockMovement).where(StockMovement.transaction_id == txn_id).values(created_at=when)
    )
    db.commit()


def _manila(d: date, hour: int, minute: int = 0) -> datetime:
    """A Manila wall-clock time as an aware UTC datetime (Manila is UTC+8, no DST)."""
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=UTC) - timedelta(hours=8)


def _invite(api, manager, role, email):
    invite = api.post("/staff/invites", json={"email": email, "role": role}, headers=manager)
    token = api.post(
        "/staff/invites/accept",
        json={"token": invite.json()["token"], "password": "staff-pass-1", "full_name": role},
    ).json()["access_token"]
    return auth_header(token)


@pytest.fixture
def cement(api, manager):
    """Cement ₱250/bag with 100 bags in stock."""
    p = make_product(api, manager, price_centavos=25000)
    _txn(api, manager, "stock_in", [{"product_id": p["id"], "qty": "100", "unit": "bag"}])
    return p


def _sell(api, headers, product, qty="1", unit="bag", **extra):
    return _txn(
        api, headers, "sale", [{"product_id": product["id"], "qty": qty, "unit": unit}], **extra
    )


def _summary(api, headers, start: date, end: date | None = None):
    params = {"start": start.isoformat(), "end": (end or start).isoformat()}
    res = api.get("/reports/sales-summary", params=params, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# ---------- dates ----------


def test_manila_day_is_converted_to_utc():
    lo, hi = reports.utc_bounds(DateRange(start=DAY, end=DAY))
    assert lo == datetime(2026, 3, 9, 16, 0, tzinfo=UTC)
    assert hi == datetime(2026, 3, 10, 16, 0, tzinfo=UTC)
    assert DateRange(start=DAY, end=DAY + timedelta(days=6)).previous() == DateRange(
        start=DAY - timedelta(days=7), end=DAY - timedelta(days=1)
    )
    # 15:59 UTC is still the 10th in Manila (11:59 PM); 16:00 UTC is the 11th.
    assert reports.store_today(datetime(2026, 3, 10, 15, 59, tzinfo=UTC)) == DAY
    assert reports.store_today(datetime(2026, 3, 10, 16, 0, tzinfo=UTC)) == DAY + timedelta(days=1)


def test_sale_at_11_30_pm_counts_for_that_day_not_the_next(api, db, manager, cement):
    late = _sell(api, manager, cement, qty="2")  # ₱500
    early = _sell(api, manager, cement, qty="3")  # ₱750
    _at(db, late["id"], _manila(DAY, 23, 30))
    _at(db, early["id"], _manila(DAY + timedelta(days=1), 0, 30))

    today = _summary(api, manager, DAY)
    assert today["total_centavos"] == 50000 and today["sales_count"] == 1
    tomorrow = _summary(api, manager, DAY + timedelta(days=1))
    assert tomorrow["total_centavos"] == 75000 and tomorrow["sales_count"] == 1
    # Compared with the day before: 750 vs 500 = +50%.
    assert tomorrow["previous"]["total_centavos"] == 50000 and tomorrow["change_pct"] == 50.0
    assert today["previous"]["total_centavos"] == 0 and today["change_pct"] is None

    # The transaction list uses the same day boundaries.
    res = api.get(
        "/transactions", params={"start": DAY.isoformat(), "end": DAY.isoformat()}, headers=manager
    )
    assert [t["id"] for t in res.json()["items"]] == [late["id"]]


def test_today_is_compared_with_yesterday_up_to_the_same_time(api, db, manager, cement):
    """At 9:15 AM, today is compared with yesterday 00:00-09:15, not all of yesterday
    (which would show a drop every morning)."""
    yesterday = DAY - timedelta(days=1)
    for qty, when in [
        ("1", _manila(yesterday, 8)),  # ₱250, before 9:15: counts
        ("2", _manila(yesterday, 15)),  # ₱500, after 9:15: not yet comparable
        ("1", _manila(DAY, 9)),  # ₱250 today
    ]:
        _at(db, _sell(api, manager, cement, qty=qty)["id"], when)
    store_id = uuid.UUID(api.get("/auth/me", headers=manager).json()["store_id"])
    now = _manila(DAY, 9, 15)

    summary = reports.sales_summary(db, store_id, DateRange(start=DAY, end=DAY), now=now)
    assert summary.total_centavos == 25000
    assert summary.previous.total_centavos == 25000 and summary.previous.sales_count == 1
    assert summary.previous.until == _manila(yesterday, 9, 15)
    assert summary.change_pct == 0.0
    assert summary.compared_to == "same time yesterday"

    # A finished day (not today) is compared with the whole day before.
    later = now + timedelta(days=1)
    summary = reports.sales_summary(db, store_id, DateRange(start=DAY, end=DAY), now=later)
    assert summary.previous.total_centavos == 75000 and summary.previous.until is None
    assert summary.compared_to == "the day before"

    # The API returns the same words for Home to show.
    res = api.get("/reports/sales-summary", headers=manager)
    assert res.json()["compared_to"] == "same time yesterday"


def test_week_so_far_is_compared_with_last_week_up_to_the_same_weekday_and_time(
    api, db, manager, cement
):
    """Mon-Wed 9:15 AM is compared with last Mon-Wed 9:15 AM, not with the 3 days just
    before (last Fri-Sun)."""
    monday = date(2026, 3, 2)
    wednesday = monday + timedelta(days=2)
    last_monday = monday - timedelta(days=7)
    for qty, when in [
        ("1", _manila(last_monday, 10)),  # ₱250 last Monday: counts
        ("2", _manila(last_monday + timedelta(days=2), 8)),  # ₱500 last Wed 8 AM: counts
        ("4", _manila(last_monday + timedelta(days=2), 10)),  # ₱1000 last Wed 10 AM: too late
        ("8", _manila(monday - timedelta(days=1), 12)),  # ₱2000 last Sunday: not last Mon-Wed
        ("3", _manila(monday, 9)),  # ₱750 this week
    ]:
        _at(db, _sell(api, manager, cement, qty=qty)["id"], when)
    store_id = uuid.UUID(api.get("/auth/me", headers=manager).json()["store_id"])

    now = _manila(wednesday, 9, 15)
    summary = reports.sales_summary(db, store_id, DateRange(start=monday, end=wednesday), now=now)
    last_wednesday = last_monday + timedelta(days=2)
    assert summary.previous.range == DateRange(start=last_monday, end=last_wednesday)
    assert summary.previous.until == _manila(last_monday + timedelta(days=2), 9, 15)
    assert summary.previous.total_centavos == 75000 and summary.total_centavos == 75000
    assert summary.compared_to == "same time last week"

    # The whole week Mon-Sun, seen on Wednesday, lines up the same way.
    full_week = DateRange(start=monday, end=monday + timedelta(days=6))
    summary = reports.sales_summary(db, store_id, full_week, now=now)
    assert summary.previous.range.start == last_monday
    assert summary.previous.total_centavos == 75000

    # Once the week is over it is compared with the 7 days before, whole.
    summary = reports.sales_summary(db, store_id, full_week, now=now + timedelta(days=7))
    assert summary.previous.until is None and summary.compared_to == "the previous 7 days"


def test_month_so_far_is_compared_with_last_month_up_to_the_same_day_and_time(
    api, db, manager, cement
):
    """Mar 1-5 at 9:15 AM is compared with Feb 1-5 until 9:15 AM; a month-end day that
    last month doesn't have is capped at its last day."""
    for qty, when in [
        ("1", _manila(date(2026, 2, 5), 8)),  # ₱250 Feb 5, 8 AM: counts
        ("2", _manila(date(2026, 2, 5), 10)),  # ₱500 Feb 5, 10 AM: too late
        ("4", _manila(date(2026, 1, 31), 12)),  # ₱1000 Jan 31: not in February
    ]:
        _at(db, _sell(api, manager, cement, qty=qty)["id"], when)
    store_id = uuid.UUID(api.get("/auth/me", headers=manager).json()["store_id"])

    period = DateRange(start=date(2026, 3, 1), end=date(2026, 3, 5))
    summary = reports.sales_summary(db, store_id, period, now=_manila(date(2026, 3, 5), 9, 15))
    assert summary.previous.range == DateRange(start=date(2026, 2, 1), end=date(2026, 2, 5))
    assert summary.previous.total_centavos == 25000
    assert summary.compared_to == "same time last month"

    # March 1-31 seen on March 31: February ends on the 28th.
    period = DateRange(start=date(2026, 3, 1), end=date(2026, 3, 31))
    summary = reports.sales_summary(db, store_id, period, now=_manila(date(2026, 3, 31), 9))
    assert summary.previous.range == DateRange(start=date(2026, 2, 1), end=date(2026, 2, 28))


def test_unfinished_range_is_compared_up_to_the_same_point(api, db, manager, cement):
    """A range that ends after today (this week Mon-Sun, seen on a Wednesday) isn't over
    either, so it's also compared with the period before only up to the same point."""
    period = DateRange(start=DAY, end=DAY + timedelta(days=2))  # DAY is "today" below
    before = DAY - timedelta(days=3)  # first day of the previous period
    for qty, when in [
        ("1", _manila(before, 8)),  # ₱250, before the cut: counts
        ("2", _manila(before + timedelta(days=1), 10)),  # ₱500, past the cut
        ("1", _manila(DAY, 9)),
    ]:
        _at(db, _sell(api, manager, cement, qty=qty)["id"], when)
    store_id = uuid.UUID(api.get("/auth/me", headers=manager).json()["store_id"])

    summary = reports.sales_summary(db, store_id, period, now=_manila(DAY, 9, 15))
    assert summary.previous.until == _manila(before, 9, 15)
    assert summary.previous.total_centavos == 25000 and summary.change_pct == 0.0


def test_bad_ranges_are_refused(api, manager):
    later = {"start": "2026-11-06", "end": "2026-11-05"}
    assert api.get("/reports/sales-summary", params=later, headers=manager).status_code == 422
    too_long = {"start": "2025-01-01", "end": "2026-03-10"}
    res = api.get("/reports/sales-summary", params=too_long, headers=manager)
    assert res.status_code == 422 and "366" in res.json()["detail"]


def test_extreme_dates_are_422_not_500(api, manager):
    """Year 1 or 9999 used to overflow when turned into UTC or the previous period."""
    requests = [
        ("/reports/sales-summary", {"start": "0001-01-01"}),
        ("/reports/sales-summary", {"end": "9999-12-31"}),
        ("/transactions", {"end": "9999-12-31"}),
        ("/reports/stock-movements", {"end": "9999-12-31"}),
    ]
    for path, params in requests:
        res = api.get(path, params=params, headers=manager)
        assert res.status_code == 422, (path, params, res.text)
        assert "2000-01-01" in res.json()["detail"], res.text


def test_earliest_and_latest_allowed_ranges_work(api, manager):
    # The period before the earliest allowed range starts in 1999; that must not crash.
    first_year = {"start": "2000-01-01", "end": "2000-12-31"}
    assert api.get("/reports/sales-summary", params=first_year, headers=manager).status_code == 200
    last_day = {"start": "2100-12-31"}
    assert api.get("/reports/sales-summary", params=last_day, headers=manager).status_code == 200
    assert api.get("/transactions", params=last_day, headers=manager).status_code == 200


# ---------- voided sales ----------


def test_voided_sales_are_excluded(api, db, manager, cement):
    kept = _sell(api, manager, cement, qty="2")
    voided = _sell(api, manager, cement, qty="5")
    assert api.post(f"/transactions/{voided['id']}/void", headers=manager).status_code == 200
    for t in (kept, voided):
        _at(db, t["id"], _manila(DAY, 10))

    summary = _summary(api, manager, DAY)
    assert summary["total_centavos"] == 50000 and summary["sales_count"] == 1

    top = api.get(
        "/reports/top-products",
        params={"start": DAY.isoformat(), "end": DAY.isoformat()},
        headers=manager,
    ).json()
    assert [(i["name"], i["qty"], i["revenue_centavos"]) for i in top["items"]] == [
        ("Portland Cement 40kg", "2.000", 50000)
    ]


def test_top_products_by_qty_and_by_revenue(api, db, manager, cement):
    nails = make_product(
        api, manager, name="Common Nail", category="Nails & Screws", base_unit="kg",
        price_centavos=9000,
    )  # fmt: skip
    _txn(api, manager, "stock_in", [{"product_id": nails["id"], "qty": "50", "unit": "kg"}])
    sales = [
        _sell(api, manager, cement, qty="1"),  # 1 bag, ₱250
        _sell(api, manager, nails, qty="10", unit="kg"),  # 10 kg, ₱900
    ]
    for t in sales:
        _at(db, t["id"], _manila(DAY, 9))
    params = {"start": DAY.isoformat(), "end": DAY.isoformat()}
    by_qty = api.get("/reports/top-products", params=params, headers=manager).json()
    assert [i["name"] for i in by_qty["items"]] == ["Common Nail", "Portland Cement 40kg"]
    by_rev = api.get(
        "/reports/top-products", params={**params, "by": "revenue", "limit": 1}, headers=manager
    ).json()
    assert [(i["name"], i["revenue_centavos"]) for i in by_rev["items"]] == [("Common Nail", 90000)]


# ---------- low stock ----------


def test_low_stock_lowest_first_and_only_active_products_with_a_level(api, db, manager):
    def product(name, stock, level, archived=False):
        p = make_product(api, manager, name=name, low_stock_level=level)
        if stock:
            _txn(api, manager, "stock_in", [{"product_id": p["id"], "qty": stock, "unit": "bag"}])
        if archived:
            api.post(f"/products/{p['id']}/archive", headers=manager)
        return p

    product("At level", "5", "5")  # equal counts as low
    product("Empty", None, "3")
    product("Plenty", "50", "5")
    product("No level", "1", None)
    product("Archived", "1", "5", archived=True)

    rows = api.get("/reports/low-stock", headers=manager).json()
    assert [(r["name"], r["stock_qty"]) for r in rows] == [
        ("Empty", "0.000"),
        ("At level", "5.000"),
    ]


# ---------- history ----------


def test_stock_movements_pagination_newest_first(api, manager, cement):
    for _ in range(24):  # + the fixture's stock-in = 25 movements
        _sell(api, manager, cement)
    first = api.get("/reports/stock-movements", headers=manager).json()
    assert first["total"] == 25 and first["pages"] == 2 and len(first["items"]) == 20
    second = api.get("/reports/stock-movements", params={"page": 2}, headers=manager).json()
    assert len(second["items"]) == 5
    assert second["items"][-1]["kind"] == "stock_in"  # the oldest one, on the last page
    stamps = [r["created_at"] for r in first["items"] + second["items"]]
    assert stamps == sorted(stamps, reverse=True)
    # stock_after goes 99, 98, ... newest first
    assert first["items"][0]["stock_after"] == "76.000"


def test_movement_filters_and_product_history(api, db, manager, cement):
    sale = _sell(api, manager, cement, qty="4")
    api.post(f"/transactions/{sale['id']}/void", headers=manager)

    def kinds(**params):
        res = api.get("/reports/stock-movements", params=params, headers=manager).json()
        return [(r["kind"], r["qty_change"], r["stock_after"]) for r in res["items"]]

    assert kinds(kind="void") == [("void", "4.000", "100.000")]
    assert kinds(kind="sale") == [("sale", "-4.000", "96.000")]
    assert kinds(kind="adjustment") == []
    member = _invite(api, manager, "member", "m@example.com")
    assert kinds(created_by=str(uuid.uuid4())) == []

    history = api.get(f"/reports/products/{cement['id']}/history", headers=member).json()
    assert [r["kind"] for r in history["items"]] == ["void", "sale", "stock_in"]
    assert [r["stock_after"] for r in history["items"]] == ["100.000", "96.000", "100.000"]


# ---------- stock check ----------


def test_stock_check_is_empty_after_a_sale_and_a_void(api, db, manager, cement):
    sale = _sell(api, manager, cement, qty="7")
    assert api.post(f"/transactions/{sale['id']}/void", headers=manager).status_code == 200
    _sell(api, manager, cement, qty="2")
    make_product(api, manager, name="Never moved")  # 0 stock, no movements: fine
    assert api.get("/reports/stock-check", headers=manager).json() == []

    # A change that skipped the movement log is caught.
    db.execute(
        update(Product).where(Product.id == uuid.UUID(cement["id"])).values(stock_qty=Decimal(1))
    )
    db.commit()
    [row] = api.get("/reports/stock-check", headers=manager).json()
    assert row["name"] == "Portland Cement 40kg"
    assert (row["stock_qty"], row["movements_sum"], row["difference"]) == (
        "1.000",
        "98.000",
        "-97.000",
    )


# ---------- scans to review ----------


def test_scans_to_review_lists_read_unsaved_recent_scans(api, db, manager, storage, reader, cement):
    reader.lines = [scan_line(cement["id"], unit="bag"), scan_line(None, unit="pc")]
    keys = [upload_photo(api, manager, storage) for _ in range(3)]
    scans = [
        api.post("/scans", json={"photo_key": k, "type": "sale"}, headers=manager).json()
        for k in keys
    ]
    fresh, saved, old = scans
    _txn(
        api,
        manager,
        "sale",
        [{"product_id": cement["id"], "qty": "1", "unit": "bag", "scan_line": 0}],
        scan_id=saved["id"],
    )
    db.execute(
        update(Scan)
        .where(Scan.id == uuid.UUID(old["id"]))
        .values(created_at=datetime.now(UTC) - timedelta(days=8))
    )
    db.commit()
    rows = api.get("/reports/scans-to-review", headers=manager).json()["items"]
    assert [(r["scan_id"], r["type"], r["line_count"]) for r in rows] == [(fresh["id"], "sale", 2)]


def test_scans_to_review_includes_failed_reads(api, manager, storage, reader, cement):
    """A photo the AI couldn't read is also unfinished work: its list isn't recorded."""
    reader.lines = [scan_line(cement["id"], unit="bag")]
    read = api.post(
        "/scans", json={"photo_key": upload_photo(api, manager, storage), "type": "sale"},
        headers=manager,
    ).json()  # fmt: skip
    reader.error = AIReadError("Reading took too long. Please try again.", retryable=True)
    failed = api.post(
        "/scans", json={"photo_key": upload_photo(api, manager, storage)}, headers=manager
    ).json()
    assert failed["status"] == "failed"

    rows = api.get("/reports/scans-to-review", headers=manager).json()["items"]
    assert [(r["scan_id"], r["status"], r["line_count"]) for r in rows] == [
        (failed["id"], "failed", 0),
        (read["id"], "read", 1),
    ]


def test_scans_to_review_skips_failures_that_cant_be_retried(api, manager, storage, reader):
    """Nothing can be done with a photo that can never be read, so it isn't listed."""
    reader.error = AIReadError("This photo could not be read.", retryable=False)
    res = api.post(
        "/scans", json={"photo_key": upload_photo(api, manager, storage)}, headers=manager
    )
    assert res.json()["status"] == "failed" and res.json()["retryable"] is False

    assert api.get("/reports/scans-to-review", headers=manager).json()["items"] == []


def test_scans_to_review_includes_reads_stuck_in_pending(api, db, manager, storage):
    """A read cut off mid-way (e.g. a server restart) stays "pending" forever. The phone
    shows it as a failure to retry, so Needs review lists it as failed too."""
    me = api.get("/auth/me", headers=manager).json()
    stuck, reading = (
        Scan(
            store_id=uuid.UUID(me["store_id"]),
            type="stock_in",
            photo_key=upload_photo(api, manager, storage),
            status="pending",
            created_by=uuid.UUID(me["user_id"]),
        )
        for _ in range(2)
    )
    db.add_all([stuck, reading])
    db.commit()
    db.execute(
        update(Scan)
        .where(Scan.id == stuck.id)
        .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
    )
    db.commit()

    rows = api.get("/reports/scans-to-review", headers=manager).json()["items"]
    assert [(r["scan_id"], r["status"]) for r in rows] == [(str(stuck.id), "failed")]


def test_scans_to_review_says_when_there_are_more(api, db, manager):
    """At most 50 are listed. has_more tells whether the list was cut, so exactly 50
    isn't shown as "50+" (the web used to guess from the count)."""
    me = api.get("/auth/me", headers=manager).json()
    store_id, user_id = uuid.UUID(me["store_id"]), uuid.UUID(me["user_id"])
    start = datetime.now(UTC) - timedelta(hours=2)

    def add_scans(first: int, count: int) -> None:
        db.add_all(
            Scan(
                store_id=store_id,
                type="sale",
                photo_key=f"{store_id}/scans/{n}",
                status="read",
                created_by=user_id,
                created_at=start + timedelta(minutes=n),
            )
            for n in range(first, first + count)
        )
        db.commit()

    add_scans(0, 50)
    full = api.get("/reports/scans-to-review", headers=manager).json()
    assert len(full["items"]) == 50 and full["has_more"] is False

    add_scans(50, 1)
    more = api.get("/reports/scans-to-review", headers=manager).json()
    assert len(more["items"]) == 50 and more["has_more"] is True
    newest = db.scalar(select(Scan.id).order_by(Scan.created_at.desc()).limit(1))
    assert more["items"][0]["scan_id"] == str(newest)


# ---------- roles ----------


def test_who_can_read_what(api, manager, cement):
    member = _invite(api, manager, "member", "m@example.com")
    secretary = _invite(api, manager, "secretary", "s@example.com")
    member_ok = [
        "/reports/sales-summary",
        "/reports/low-stock",
        "/reports/stock-movements",
        f"/reports/products/{cement['id']}/history",
        "/reports/scans-to-review",
    ]
    for path in member_ok:
        assert api.get(path, headers=member).status_code == 200, path
    assert api.get("/reports/top-products", headers=member).status_code == 403
    assert api.get("/reports/top-products", headers=secretary).status_code == 200
    assert api.get("/reports/stock-check", headers=member).status_code == 403
    assert api.get("/reports/stock-check", headers=secretary).status_code == 403
    assert api.get("/reports/stock-check", headers=manager).status_code == 200


# ---------- tenant isolation ----------


def test_reports_only_show_your_own_store(api, db, signup, manager, cement):
    sale = _sell(api, manager, cement, qty="2")
    _at(db, sale["id"], _manila(DAY, 12))
    api.patch(f"/products/{cement['id']}", json={"low_stock_level": "500"}, headers=manager)

    other = auth_header(signup(email="b@example.com", store_name="Store B")["access_token"])
    assert _summary(api, other, DAY)["sales_count"] == 0
    assert api.get("/reports/low-stock", headers=other).json() == []
    assert api.get("/reports/stock-movements", headers=other).json()["total"] == 0
    res = api.get(f"/reports/products/{cement['id']}/history", headers=other)
    assert res.status_code == 404
    params = {"start": DAY.isoformat(), "end": DAY.isoformat()}
    assert api.get("/reports/top-products", params=params, headers=other).json()["items"] == []
    assert api.get("/transactions", params=params, headers=other).json()["total"] == 0
    assert api.get("/reports/scans-to-review", headers=other).json()["items"] == []
    # ...while store A sees its own.
    assert _summary(api, manager, DAY)["sales_count"] == 1
    assert len(api.get("/reports/low-stock", headers=manager).json()) == 1
