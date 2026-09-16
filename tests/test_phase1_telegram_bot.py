import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from v3.phase1.telegram_bot import (
    COMMANDS,
    LedgerFacts,
    balance_text,
    daily_text,
    episode_pnl,
    handle_update,
    help_text,
    load_run_evidence,
    parse_command,
    profit_text,
    status_text,
)
from v3.phase1.telegram_text import compact_event

NOW = datetime(2026, 9, 15, 12, 30, tzinfo=UTC)


def _facts():
    t = datetime(2026, 9, 15, 11, 35, tzinfo=UTC)
    fills = [
        dict(
            intent_id="a",
            leg="spot",
            side="buy",
            quantity="0.00285",
            price="76939.29",
            fee_amount="0.00000285",
            fee_token="BTC",
            filled_at=t,
        ),
        dict(
            intent_id="a",
            leg="perp",
            side="sell",
            quantity="0.0028",
            price="76899.4",
            fee_amount="0.086",
            fee_token="USDT",
            filled_at=t,
        ),
        dict(
            intent_id="a",
            leg="perp",
            side="buy",
            quantity="0.0028",
            price="76907.1",
            fee_amount="0.086",
            fee_token="USDT",
            filled_at=t + timedelta(minutes=5),
        ),
        dict(
            intent_id="a",
            leg="spot",
            side="sell",
            quantity="0.00284",
            price="76914",
            fee_amount="0.218",
            fee_token="USDT",
            filled_at=t + timedelta(minutes=5),
        ),
    ]
    return LedgerFacts(
        [("a", "CLOSED", t), ("b", "HEDGED", t + timedelta(hours=1))],
        fills,
        {"a": Decimal("0.00000715")},
        0,
        0,
        0,
        0,
    )


def test_parse_command_accepts_bot_suffix_and_arguments():
    assert parse_command("/status") == "status"
    assert parse_command("/Profit@kai_bot now") == "profit"
    assert parse_command("hello") is None and parse_command(None) is None


def test_episode_pnl_is_usdt_cash_flow_net_of_usdt_fees_with_btc_kept_separate():
    pnl = episode_pnl(_facts().fills)["a"]
    gross = (
        Decimal("-0.00285") * Decimal("76939.29")
        + Decimal("0.0028") * Decimal("76899.4")
        - Decimal("0.0028") * Decimal("76907.1")
        + Decimal("0.00284") * Decimal("76914")
    )
    assert pnl["usdt"] == gross
    assert pnl["net_usdt"] == gross - Decimal("0.39")
    assert pnl["fees_btc"] == Decimal("0.00000285")


def test_texts_mark_demo_and_stay_short():
    facts = _facts()
    run = {
        "started_at": "2026-09-15T12:07:24+00:00",
        "bounds": {"maximum_episodes": 60, "episode_interval_seconds": 7200},
        "events": [{"at": "2026-09-15T12:07:37+00:00", "kind": "trade"}],
    }
    for text in (
        status_text(facts, run, NOW),
        profit_text(facts),
        daily_text(facts, run, NOW),
        help_text(),
    ):
        assert text.startswith("[DEMO]") and len(text.splitlines()) <= 8
    status = status_text(facts, run, NOW)
    assert "1 종료 / 최대 60" in status and "진행 중: HEDGED" in status and "원장: 정상" in status
    assert "#1" in profit_text(facts) and "잔량 0.00000715 BTC" in profit_text(facts)
    account = dict(
        spot_usdt=Decimal("781.1"),
        spot_total_btc=Decimal("0.00002144"),
        perp_usdt=Decimal("612.3"),
        perp_qty=Decimal("0"),
        leverage=2,
        margin_type="ISOLATED",
        open_orders=[],
    )
    assert "선물 포지션: 0 BTC (flat)" in balance_text(account)
    assert [name for name, _ in COMMANDS] == ["status", "profit", "balance", "daily", "help"]


def test_handle_update_ignores_other_chats_and_non_commands():
    loaders = dict(
        facts_loader=_facts, run_loader=lambda: {"events": []}, account_loader=lambda: {}
    )
    assert (
        handle_update(
            {"message": {"chat": {"id": 999}, "text": "/status"}}, chat_id="123", **loaders
        )
        is None
    )
    assert (
        handle_update({"message": {"chat": {"id": 123}, "text": "hi"}}, chat_id="123", **loaders)
        is None
    )
    chat, reply = handle_update(
        {"message": {"chat": {"id": 123}, "text": "/help"}}, chat_id="123", **loaders
    )
    assert chat == "123" and reply.startswith("[DEMO] 명령")

    # A loader failure becomes a short reply, never a crash.
    def boom():
        raise RuntimeError("db down")

    _, reply = handle_update(
        {"message": {"chat": {"id": 123}, "text": "/balance"}},
        chat_id="123",
        facts_loader=_facts,
        run_loader=dict,
        account_loader=boom,
    )
    assert reply == "[DEMO] 조회 실패: RuntimeError"


def test_load_run_evidence_prefers_latest_run_file(tmp_path):
    (tmp_path / "started-at.txt").write_text("2026-09-15T12:07:24+00:00\n")
    (tmp_path / "run.json").write_text(
        json.dumps(
            {"events": [{"at": "1", "kind": "start"}], "run_bounds": {"maximum_episodes": 2}}
        )
    )
    info = load_run_evidence(tmp_path)
    assert info["started_at"] == "2026-09-15T12:07:24+00:00"
    assert info["bounds"] == {"maximum_episodes": 2} and len(info["events"]) == 1


def test_compact_event_lines_are_short_korean_summaries():
    title, summary, details = compact_event(
        "trade",
        {
            "fill_confirmed": True,
            "instrument": "BTCUSDT-PERP.BINANCE_USDM_DEMO",
            "quantity": "0.0028",
            "price": "76911.40",
            "side": "SELL",
        },
    )
    assert title == "체결 선물 매도" and summary == "0.0028 BTC @ 76911.40" and details == {}
    title, summary, _ = compact_event(
        "trade", {"submitted": True, "action": "spot_buy_ioc", "episode_reason": "episode 1 of 60"}
    )
    assert title == "현물 매수 제출" and summary == "episode 1 of 60"
    title, summary, _ = compact_event(
        "stop", {"residual_settled": True, "residual_base": "0.00000714"}
    )
    assert "잔량 정산" in title and "0.00000714" in summary
    title, summary, _ = compact_event(
        "stop", {"status": "STOPPED", "reason": "run_window_exhausted", "episodes_closed": 2}
    )
    assert title == "실행 종료" and "run_window_exhausted" in summary
    title, _, _ = compact_event("start", {"status": "RESUMING", "intent_id": "abcdef12-3"})
    assert title.startswith("재시작")
