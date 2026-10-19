"""Persistent transaction receipts for PayShield-governed payments.

A receipt is the immutable, human-readable record of a single payment attempt
and its final outcome. It captures the authoritative server-side knowledge at
the moment a decision was made (a snapshot of the product, AI advisory, risk,
policy, and payment intent) and then records the outcome lifecycle as the
payment progresses.

Design rules:
  * Snapshots are written once at creation and never mutated afterwards, so a
    later search, assessment, or re-evaluation can never rewrite history.
  * Statuses come from a single canonical vocabulary (:class:`ReceiptStatus`).
  * Only verified, authoritative outcomes may be recorded. Missing data is left
    absent so the UI can honestly render "Not available" rather than guessing.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReceiptStatus:
    """Canonical payment outcome vocabulary shared by every surface."""

    COMPLETED = "COMPLETED"
    PENDING = "PENDING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    AWAITING_BUYER_APPROVAL = "AWAITING_BUYER_APPROVAL"
    AUTHORIZED = "AUTHORIZED"
    CAPTURE_PENDING = "CAPTURE_PENDING"

    ALL = frozenset({
        COMPLETED,
        PENDING,
        FAILED,
        CANCELLED,
        BLOCKED,
        REVIEW_REQUIRED,
        EXPIRED,
        REFUNDED,
        PARTIALLY_REFUNDED,
        AWAITING_BUYER_APPROVAL,
        AUTHORIZED,
        CAPTURE_PENDING,
    })

    # A payment that has reached a settled, non-progressing outcome.
    FINAL = frozenset({
        COMPLETED,
        FAILED,
        CANCELLED,
        BLOCKED,
        EXPIRED,
        REFUNDED,
        PARTIALLY_REFUNDED,
    })

    # A payment that still expects further processing or a human decision.
    OPEN = frozenset({
        PENDING,
        REVIEW_REQUIRED,
        AWAITING_BUYER_APPROVAL,
        AUTHORIZED,
        CAPTURE_PENDING,
    })

    LABELS = {
        COMPLETED: "Completed",
        PENDING: "Pending",
        FAILED: "Failed",
        CANCELLED: "Cancelled",
        BLOCKED: "Blocked",
        REVIEW_REQUIRED: "Review required",
        EXPIRED: "Expired",
        REFUNDED: "Refunded",
        PARTIALLY_REFUNDED: "Partially refunded",
        AWAITING_BUYER_APPROVAL: "Awaiting buyer approval",
        AUTHORIZED: "Authorized",
        CAPTURE_PENDING: "Capture pending",
    }

    @classmethod
    def validate(cls, status: str) -> str:
        if status not in cls.ALL:
            raise ValueError(f"Unknown receipt status: {status!r}")
        return status


def build_snapshots(
    *,
    product: Optional[dict] = None,
    ai_assessment: Optional[dict] = None,
    risk: Optional[dict] = None,
    policy: Optional[dict] = None,
    decision: Optional[dict] = None,
    payment: Optional[dict] = None,
) -> dict:
    """Assemble an immutable receipt snapshot from authoritative inputs.

    Only values actually known to the server are stored. ``None`` sections are
    omitted entirely so the UI can render an honest "Not available" state.
    """
    snapshots: dict[str, Any] = {}
    if product is not None:
        snapshots["product"] = product
    if ai_assessment is not None:
        snapshots["ai_assessment"] = ai_assessment
    if risk is not None:
        snapshots["risk"] = risk
    if policy is not None:
        snapshots["policy"] = policy
    if decision is not None:
        snapshots["decision"] = decision
    if payment is not None:
        snapshots["payment"] = payment
    return snapshots


class ReceiptStore:
    """SQLite-backed, append-only receipt registry."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(
            db_path
            or os.getenv("PAYSHIELD_RECEIPT_DB_PATH")
            or os.getenv("PAYSHIELD_DB_PATH")
            or "payshield_payments.sqlite3"
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS transaction_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    transaction_id TEXT,
                    order_id TEXT,
                    capture_id TEXT,
                    decision_reference TEXT,
                    external_order_id TEXT,
                    idempotency_key TEXT,
                    user_id TEXT NOT NULL DEFAULT '',
                    agent_id TEXT NOT NULL DEFAULT '',
                    merchant_name TEXT NOT NULL DEFAULT '',
                    merchant_category TEXT NOT NULL DEFAULT '',
                    amount TEXT,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    quantity INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    decision TEXT NOT NULL DEFAULT '',
                    payment_status_raw TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    risk_score INTEGER,
                    risk_level TEXT NOT NULL DEFAULT '',
                    snapshots_json TEXT NOT NULL DEFAULT '{}',
                    events_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_order
                ON transaction_receipts (order_id)
                WHERE order_id IS NOT NULL
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_idempotency
                ON transaction_receipts (idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_receipts_user
                ON transaction_receipts (user_id, created_at)
                """
            )

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10)

    @staticmethod
    def _validate_receipt_id(receipt_id: str) -> str:
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            raise ValueError("Receipt ID is required")
        return receipt_id.strip()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    def create_receipt(
        self,
        *,
        status: str,
        transaction_id: Optional[str] = None,
        order_id: Optional[str] = None,
        capture_id: Optional[str] = None,
        decision_reference: Optional[str] = None,
        external_order_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        user_id: str = "",
        agent_id: str = "",
        merchant_name: str = "",
        merchant_category: str = "",
        amount: Any = None,
        currency: str = "USD",
        quantity: int = 1,
        decision: str = "",
        payment_status_raw: str = "",
        reason: str = "",
        risk_score: Optional[int] = None,
        risk_level: str = "",
        snapshots: Optional[dict] = None,
        event: Optional[dict] = None,
    ) -> str:
        """Create a receipt, returning its ID. Idempotent by order/key."""
        ReceiptStatus.validate(status)

        if order_id:
            existing = self.get_receipt_by_order_id(order_id)
            if existing is not None:
                return existing["receipt_id"]
        if idempotency_key:
            existing = self.get_receipt_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing["receipt_id"]

        receipt_id = f"RCPT-{uuid.uuid4().hex[:12].upper()}"
        now = _utc_now()
        events = [{"status": status, "at": now, "source": "created"}]
        if event:
            events.append({**event, "at": now})

        amount_text = None if amount is None else self._format_amount(amount)
        try:
            quantity_value = max(1, int(quantity))
        except (TypeError, ValueError):
            quantity_value = 1

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO transaction_receipts (
                    receipt_id, transaction_id, order_id, capture_id,
                    decision_reference, external_order_id, idempotency_key,
                    user_id, agent_id, merchant_name, merchant_category,
                    amount, currency, quantity, status, decision,
                    payment_status_raw, reason, risk_score, risk_level,
                    snapshots_json, events_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    transaction_id,
                    order_id,
                    capture_id,
                    decision_reference,
                    external_order_id,
                    idempotency_key,
                    user_id or "",
                    agent_id or "",
                    merchant_name or "",
                    merchant_category or "",
                    amount_text,
                    (currency or "USD").upper(),
                    quantity_value,
                    status,
                    decision or "",
                    payment_status_raw or "",
                    reason or "",
                    risk_score,
                    risk_level or "",
                    json.dumps(snapshots or {}, separators=(",", ":")),
                    json.dumps(events, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        return receipt_id

    @staticmethod
    def _format_amount(amount: Any) -> str:
        try:
            return f"{float(amount):.2f}"
        except (TypeError, ValueError):
            return str(amount)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    _COLUMNS = (
        "receipt_id, transaction_id, order_id, capture_id, decision_reference, "
        "external_order_id, idempotency_key, user_id, agent_id, merchant_name, "
        "merchant_category, amount, currency, quantity, status, decision, "
        "payment_status_raw, reason, risk_score, risk_level, snapshots_json, "
        "events_json, created_at, updated_at"
    )

    def _row_to_dict(self, row) -> dict:
        return {
            "receipt_id": row[0],
            "transaction_id": row[1],
            "order_id": row[2],
            "capture_id": row[3],
            "decision_reference": row[4],
            "external_order_id": row[5],
            "idempotency_key": row[6],
            "user_id": row[7],
            "agent_id": row[8],
            "merchant_name": row[9],
            "merchant_category": row[10],
            "amount": row[11],
            "currency": row[12],
            "quantity": row[13],
            "status": row[14],
            "decision": row[15],
            "payment_status_raw": row[16],
            "reason": row[17],
            "risk_score": row[18],
            "risk_level": row[19],
            "snapshots": self._safe_json(row[20], {}),
            "events": self._safe_json(row[21], []),
            "created_at": row[22],
            "updated_at": row[23],
        }

    @staticmethod
    def _safe_json(raw, fallback):
        try:
            return json.loads(raw) if raw else fallback
        except (TypeError, ValueError):
            return fallback

    def get_receipt(self, receipt_id: str) -> Optional[dict]:
        if not receipt_id or not str(receipt_id).strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {self._COLUMNS} FROM transaction_receipts WHERE receipt_id = ?",
                (str(receipt_id).strip(),),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_receipt_by_order_id(self, order_id: str) -> Optional[dict]:
        if not order_id or not str(order_id).strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {self._COLUMNS} FROM transaction_receipts WHERE order_id = ?",
                (str(order_id).strip(),),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_receipt_by_decision_reference(self, reference: str) -> Optional[dict]:
        if not reference or not str(reference).strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {self._COLUMNS} FROM transaction_receipts "
                "WHERE decision_reference = ? ORDER BY created_at DESC LIMIT 1",
                (str(reference).strip(),),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_receipt_by_idempotency_key(self, key: str) -> Optional[dict]:
        if not key or not str(key).strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {self._COLUMNS} FROM transaction_receipts WHERE idempotency_key = ?",
                (str(key).strip(),),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_receipts(
        self,
        *,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        if not 1 <= int(limit) <= 500:
            limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            if user_id is None:
                rows = connection.execute(
                    f"SELECT {self._COLUMNS} FROM transaction_receipts "
                    "ORDER BY created_at DESC, receipt_id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"SELECT {self._COLUMNS} FROM transaction_receipts "
                    "WHERE user_id = ? ORDER BY created_at DESC, receipt_id DESC LIMIT ?",
                    (str(user_id), limit),
                ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Updates (status/events only; snapshots are immutable)
    # ------------------------------------------------------------------
    def update_receipt(
        self,
        receipt_id: str,
        *,
        status: Optional[str] = None,
        decision: Optional[str] = None,
        capture_id: Optional[str] = None,
        order_id: Optional[str] = None,
        decision_reference: Optional[str] = None,
        payment_status_raw: Optional[str] = None,
        reason: Optional[str] = None,
        amount: Any = None,
        currency: Optional[str] = None,
        risk_score: Optional[int] = None,
        risk_level: Optional[str] = None,
        snapshots: Optional[dict] = None,
        event: Optional[dict] = None,
    ) -> bool:
        """Update status/events for an existing receipt.

        Snapshots are immutable by design: they are written once at creation.
        The only controlled exception is a capture-time refresh, where the
        caller explicitly passes ``snapshots`` to record the verified outcome
        of the same attempt (PayPal capture data, final risk/policy decision,
        assessment timestamp). This never rewrites history from a different
        attempt.
        """
        receipt_id = self._validate_receipt_id(receipt_id)
        if status is not None:
            ReceiptStatus.validate(status)

        with self._connect() as connection:
            row = connection.execute(
                "SELECT events_json, snapshots_json FROM transaction_receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if row is None:
                return False

            events = self._safe_json(row[0], [])
            now = _utc_now()

            assignments = ["updated_at = ?"]
            params: list[Any] = [now]
            columns = (
                ("status", status),
                ("decision", decision),
                ("capture_id", capture_id),
                ("order_id", order_id),
                ("decision_reference", decision_reference),
                ("payment_status_raw", payment_status_raw),
                ("reason", reason),
                ("amount", self._format_amount(amount) if amount is not None else None),
                ("currency", currency.upper() if currency else None),
                ("risk_score", risk_score),
                ("risk_level", risk_level),
            )
            for column, value in columns:
                if value is not None:
                    assignments.append(f"{column} = ?")
                    params.append(value)

            if snapshots is not None:
                assignments.append("snapshots_json = ?")
                params.append(json.dumps(snapshots, separators=(",", ":")))

            if status is not None:
                events.append({"status": status, "at": now, "source": "update"})
            if event:
                merged = {**event}
                if "at" not in merged:
                    merged["at"] = now
                if "source" not in merged:
                    merged["source"] = "update"
                events.append(merged)

            assignments.append("events_json = ?")
            params.append(json.dumps(events, separators=(",", ":")))
            params.append(receipt_id)

            cursor = connection.execute(
                f"UPDATE transaction_receipts SET {', '.join(assignments)} "
                "WHERE receipt_id = ?",
                params,
            )
            return cursor.rowcount == 1

    def set_status_by_order_id(
        self,
        order_id: str,
        *,
        status: str,
        capture_id: Optional[str] = None,
        payment_status_raw: Optional[str] = None,
        reason: Optional[str] = None,
        event: Optional[dict] = None,
    ) -> Optional[str]:
        """Update the receipt bound to a PayPal order; returns its ID or None."""
        existing = self.get_receipt_by_order_id(order_id)
        if existing is None:
            return None
        self.update_receipt(
            existing["receipt_id"],
            status=status,
            capture_id=capture_id,
            payment_status_raw=payment_status_raw,
            reason=reason,
            event=event,
        )
        return existing["receipt_id"]


def count_receipts(db_path: Optional[str] = None) -> int:
    """Utility used by tests and diagnostics."""
    store = ReceiptStore(db_path)
    with store._connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM transaction_receipts"
        ).fetchone()
    return int(row[0]) if row else 0
