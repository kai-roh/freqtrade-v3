# ruff: noqa: F811
import pytest
from test_phase1_dispatch_safety import ready  # noqa: F401
from test_phase1_fill_ingestion import fill

from v3.phase1.dispatch import DispatchJournal
from v3.phase1.fill_inbox import DurableFillInbox


def test_restart_processes_persisted_receipt_once_and_deduplicates_redelivery(ready):
    db, _, _, decision, command = ready
    inbox = DurableFillInbox(db)
    event = fill()
    receipt = inbox.receive(event)
    assert db.info.transaction_status.name == "IDLE"
    with pytest.raises(ValueError, match="unprocessed fill"):
        DispatchJournal(db).claim(command, decision, maximum_quote_age_ms=5000)
    restarted = DurableFillInbox(db)
    assert restarted.process(receipt) == "APPLIED"
    assert restarted.process(receipt) == "APPLIED"
    assert restarted.process(restarted.receive(event)) == "APPLIED"
    assert db.execute("SELECT count(*) FROM fills").fetchone()[0] == 1


def test_overfill_retains_evidence_opens_incident_and_blocks_new_dispatch(ready):
    db, _, _, decision, command = ready
    inbox = DurableFillInbox(db)
    assert inbox.process(inbox.receive(fill(quantity="0.003"))) == "APPLIED"
    receipt = inbox.receive(fill(trade="2"))
    assert inbox.process(receipt) == "BLOCKED"
    assert inbox.process(receipt) == "BLOCKED"
    assert db.execute("SELECT count(*) FROM incidents").fetchone()[0] == 1
    assert (
        db.execute(
            "SELECT payload->>'trade_id' FROM fill_event_inbox WHERE id=%s", (receipt,)
        ).fetchone()[0]
        == "2"
    )
    assert db.execute("SELECT count(*) FROM fills").fetchone()[0] == 1
    with pytest.raises(ValueError, match="unprocessed fill"):
        DispatchJournal(db).claim(command, decision, maximum_quote_age_ms=5000)


def test_inbox_cannot_defer_receipt_commit_in_outer_transaction(ready):
    db, _, _, _, _ = ready
    with db.transaction():
        with pytest.raises(ValueError, match="idle dedicated"):
            DurableFillInbox(db).receive(fill())
