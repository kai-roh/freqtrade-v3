from datetime import UTC, datetime

import pytest

from v3.phase1.ledger import (
    FillRow,
    InMemoryPhase1Ledger,
    IntentRow,
    InternalTransferRow,
    OrderCommandRow,
    command_idempotency_key,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _ledger():
    ledger = InMemoryPhase1Ledger()
    ledger.add_intent(
        IntentRow(
            intent_id="intent-1",
            run_manifest_id="manifest-1",
            cost_ledger_id="cost-1",
            target_notional="300",
            fields={"entry_reason": "fixture"},
            created_at=NOW,
        )
    )
    return ledger


def test_command_and_transfer_idempotency_are_enforced():
    ledger = _ledger()
    ledger.add_command(OrderCommandRow("cmd-1", "intent-1", "spot", "key-1", "0.1", "100"))
    with pytest.raises(ValueError, match="active command"):
        ledger.add_command(OrderCommandRow("cmd-2", "intent-1", "spot", "key-2", "0.1", "99"))
    ledger.deactivate_command("cmd-1")
    with pytest.raises(ValueError, match="idempotency"):
        ledger.add_command(OrderCommandRow("cmd-2", "intent-1", "spot", "key-1", "0.1", "99"))

    transfer = InternalTransferRow(
        "transfer-1",
        "intent-1",
        "USDT",
        "10",
        "spot",
        "usd_m",
        "transfer-key",
        "requested",
        NOW,
    )
    ledger.add_transfer(transfer)
    with pytest.raises(ValueError, match="idempotency"):
        ledger.add_transfer(
            InternalTransferRow(
                "transfer-2",
                "intent-1",
                "USDT",
                "10",
                "spot",
                "usd_m",
                "transfer-key",
                "requested",
                NOW,
            )
        )


def test_fill_must_reference_a_command_and_venue_fill_is_unique():
    ledger = _ledger()
    unknown = FillRow("fill-0", "binance", "venue-0", "missing", "0.1", "100", NOW)
    with pytest.raises(ValueError, match="unknown command"):
        ledger.add_fill(unknown)

    ledger.add_command(OrderCommandRow("cmd-1", "intent-1", "spot", "key-1", "0.1", "100"))
    ledger.add_fill(FillRow("fill-1", "binance", "venue-1", "cmd-1", "0.1", "100", NOW))
    with pytest.raises(ValueError, match="venue fill"):
        ledger.add_fill(FillRow("fill-2", "binance", "venue-1", "cmd-1", "0.1", "100", NOW))


def test_ledger_snapshot_can_be_restored_without_shared_mutation():
    ledger = _ledger()

    restored = InMemoryPhase1Ledger.restore(ledger.snapshot())
    restored.intents.clear()

    assert "intent-1" in ledger.intents
    assert not restored.intents


def test_command_idempotency_key_is_deterministic_and_attempt_sensitive():
    first = command_idempotency_key(
        intent_id="intent-1", leg="spot", attempt=0, quantity="0.100", price="100"
    )
    same = command_idempotency_key(
        intent_id="intent-1", leg="spot", attempt=0, quantity="0.100", price="100"
    )
    requote = command_idempotency_key(
        intent_id="intent-1", leg="spot", attempt=1, quantity="0.100", price="99"
    )

    assert len(first) == 32
    assert first == same
    assert first != requote
