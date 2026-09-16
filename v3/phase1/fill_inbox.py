"""Persist normalized fill deliveries before ingestion so failures retain evidence."""

import json
from uuid import uuid4

from psycopg.pq import TransactionStatus

from .fill_ingestion import record_nautilus_fill
from .postgres import PostgresPhase1Ledger


class DurableFillInbox:
    def __init__(self, connection):
        self.connection = connection

    def _require_idle(self):
        if self.connection.info.transaction_status != TransactionStatus.IDLE:
            raise ValueError("fill inbox requires an idle dedicated connection")

    def receive(self, event) -> str:
        """Commit normalized execution fields. Not a raw transport packet archive."""
        from nautilus_trader.model.events import OrderFilled

        self._require_idle()
        if not isinstance(event, OrderFilled):
            raise ValueError("an OrderFilled event is required")
        payload = OrderFilled.to_dict(event)
        payload["info"] = {}  # Exclude arbitrary adapter metadata from this bounded schema.
        receipt = str(uuid4())
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO fill_event_inbox (id,payload,status) VALUES (%s,%s::jsonb,'PENDING')",
                (receipt, json.dumps(payload)),
            )
        return receipt

    def process(self, receipt: str) -> str:
        """Value conflicts are quarantined; database failures leave the receipt pending."""
        from nautilus_trader.model.events import OrderFilled

        self._require_idle()
        with self.connection.transaction():
            row = self.connection.execute(
                "SELECT payload,status FROM fill_event_inbox WHERE id=%s FOR UPDATE", (receipt,)
            ).fetchone()
            if not row:
                raise ValueError("unknown fill receipt")
            if row[1] != "PENDING":
                return row[1]
            try:
                with self.connection.transaction():  # Savepoint: retain inbox on ingestion error.
                    event = OrderFilled.from_dict(row[0])
                    record_nautilus_fill(PostgresPhase1Ledger(self.connection), event)
            except (ValueError, TypeError, KeyError) as exc:
                self.connection.execute(
                    "UPDATE fill_event_inbox SET status='BLOCKED',error_type=%s,processed_at=clock_timestamp() WHERE id=%s",
                    (type(exc).__name__, receipt),
                )
                self.connection.execute(
                    "INSERT INTO incidents (id,category,severity,status,detail,opened_at) "
                    "VALUES (%s,'fill_ingestion','critical','open',%s,clock_timestamp())",
                    (
                        str(uuid4()),
                        f"fill receipt {receipt} requires reconciliation ({type(exc).__name__})",
                    ),
                )
                return "BLOCKED"
            self.connection.execute(
                "UPDATE fill_event_inbox SET status='APPLIED',processed_at=clock_timestamp() WHERE id=%s",
                (receipt,),
            )
            return "APPLIED"
