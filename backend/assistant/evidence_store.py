"""Server-side store for live product evidence and Guard Buy decision records.

The browser never supplies the authoritative product identity or amount for a
Guarded checkout. Search results are persisted here keyed by a stable product
reference, and Guard Buy re-reads that stored evidence before running the
deterministic PayShield risk/policy decision engines.
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


def _load_json_list(raw: str) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


class ProductEvidenceStore:
    """Persistent evidence and decision store backed by SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(
            db_path
            or os.getenv("PAYSHIELD_EVIDENCE_DB_PATH")
            or os.getenv("PAYSHIELD_DB_PATH")
            or "payshield_payments.sqlite3"
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS product_evidence (
                    reference TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_domain TEXT NOT NULL DEFAULT '',
                    retailer TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    snippet TEXT NOT NULL DEFAULT '',
                    price TEXT,
                    price_verified INTEGER NOT NULL DEFAULT 0,
                    availability TEXT NOT NULL DEFAULT 'Unknown',
                    currency TEXT NOT NULL DEFAULT 'USD',
                    result_type TEXT NOT NULL DEFAULT 'product',
                    category TEXT NOT NULL DEFAULT '',
                    search_timestamp TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guard_buy_decisions (
                    decision_reference TEXT PRIMARY KEY,
                    product_reference TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    agent_id TEXT NOT NULL DEFAULT '',
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    category TEXT NOT NULL DEFAULT '',
                    merchant_name TEXT NOT NULL DEFAULT '',
                    decision TEXT NOT NULL,
                    payment_status TEXT NOT NULL DEFAULT '',
                    risk_score INTEGER,
                    risk_level TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    evaluation_json TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    idempotency_key TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_guard_buy_idempotency
                ON guard_buy_decisions (idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )
            # Migration: record which authenticated identity approved a review.
            self._ensure_column(
                connection, "guard_buy_decisions", "reviewed_by", "reviewed_by TEXT"
            )
            self._ensure_column(
                connection, "guard_buy_decisions", "reviewed_at", "reviewed_at TEXT"
            )
            # Migration: price provenance extracted server-side from the source page.
            for column in (
                "price_currency",
                "price_type",
                "price_method",
                "price_confidence",
                "price_source_url",
                "price_retrieved_at",
                "price_unverified_reason",
                "retrieval_status",
                "retrieval_reason",
                "identity_match",
                "identity_reasons",
            ):
                self._ensure_column(
                    connection,
                    "product_evidence",
                    column,
                    f"{column} TEXT NOT NULL DEFAULT ''",
                )
            # Migration: live product rating evidence.
            for column in (
                "rating",
                "rating_status",
                "rating_reason",
                "rating_retrieved_at",
                "rating_provider",
            ):
                self._ensure_column(
                    connection,
                    "product_evidence",
                    column,
                    f"{column} TEXT NOT NULL DEFAULT ''",
                )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_product_evidence_rating
                ON product_evidence (rating_status)
                """
            )

    @staticmethod
    def _ensure_column(connection, table: str, column: str, ddl: str) -> None:
        existing = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10)

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------
    def save_search_results(
        self, results: Iterable[Any], category: str = ""
    ) -> list[str]:
        """Persist search evidence and return the stored stable references."""
        saved: list[str] = []
        with self._connect() as connection:
            for result in results:
                reference = getattr(result, "product_reference", "") or getattr(
                    result, "id", ""
                )
                if not reference:
                    continue
                price = getattr(result, "price", None)
                price_verified = bool(getattr(result, "price_verified", False))
                connection.execute(
                    """
                    INSERT INTO product_evidence (
                        reference, title, source_url, source_domain, retailer,
                        image_url, snippet, price, price_verified, availability,
                        currency, result_type, category, search_timestamp,
                        evidence_json, price_currency, price_type, price_method,
                        price_confidence, price_source_url, price_retrieved_at,
                        price_unverified_reason, retrieval_status, retrieval_reason,
                        identity_match, identity_reasons,
                        rating, rating_status, rating_reason, rating_retrieved_at, rating_provider
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(reference) DO UPDATE SET
                        title = excluded.title,
                        source_url = excluded.source_url,
                        source_domain = excluded.source_domain,
                        retailer = excluded.retailer,
                        image_url = excluded.image_url,
                        snippet = excluded.snippet,
                        price = excluded.price,
                        price_verified = excluded.price_verified,
                        availability = excluded.availability,
                        currency = excluded.currency,
                        result_type = excluded.result_type,
                        category = excluded.category,
                        search_timestamp = excluded.search_timestamp,
                        evidence_json = excluded.evidence_json,
                        price_currency = excluded.price_currency,
                        price_type = excluded.price_type,
                        price_method = excluded.price_method,
                        price_confidence = excluded.price_confidence,
                        price_source_url = excluded.price_source_url,
                        price_retrieved_at = excluded.price_retrieved_at,
                        price_unverified_reason = excluded.price_unverified_reason,
                        retrieval_status = excluded.retrieval_status,
                        retrieval_reason = excluded.retrieval_reason,
                        identity_match = excluded.identity_match,
                        identity_reasons = excluded.identity_reasons,
                        rating = excluded.rating,
                        rating_status = excluded.rating_status,
                        rating_reason = excluded.rating_reason,
                        rating_retrieved_at = excluded.rating_retrieved_at,
                        rating_provider = excluded.rating_provider
                    """,
                    (
                        reference,
                        str(getattr(result, "title", "")),
                        str(getattr(result, "source_url", "")),
                        str(getattr(result, "source_domain", "")),
                        str(getattr(result, "retailer", "")),
                        str(getattr(result, "image_url", "")),
                        str(getattr(result, "snippet", ""))[:2000],
                        None if price is None else str(price),
                        1 if price_verified else 0,
                        str(getattr(result, "availability", "Unknown")),
                        str(getattr(result, "currency", "USD")),
                        str(getattr(result, "result_type", "product")),
                        category or "",
                        str(getattr(result, "search_timestamp", _utc_now())),
                        json.dumps(
                            self._result_to_dict(result), separators=(",", ":")
                        ),
                        str(getattr(result, "price_currency", "")),
                        str(getattr(result, "price_type", "")),
                        str(getattr(result, "price_method", "")),
                        str(getattr(result, "price_confidence", "")),
                        str(getattr(result, "price_source_url", "")),
                        str(getattr(result, "price_retrieved_at", "")),
                        str(getattr(result, "price_unverified_reason", "")),
                        str(getattr(result, "retrieval_status", "")),
                        str(getattr(result, "retrieval_reason", "")),
                        str(getattr(result, "identity_match", "UNKNOWN") or "UNKNOWN"),
                        json.dumps(
                            list(getattr(result, "identity_reasons", []) or []),
                            separators=(",", ":"),
                        ),
                        str(getattr(result, "rating", "")) if getattr(result, "rating", None) is not None else "",
                        str(getattr(result, "rating_status", "")),
                        str(getattr(result, "rating_reason", "")),
                        str(getattr(result, "rating_retrieved_at", "")),
                        str(getattr(result, "rating_provider", "")),
                    ),
                )
                saved.append(reference)
        return saved

    @staticmethod
    def _result_to_dict(result: Any) -> dict:
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        if isinstance(result, dict):
            return result
        return {}

    def get_product(self, reference: str) -> Optional[dict]:
        if not reference or not str(reference).strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT reference, title, source_url, source_domain, retailer,
                       image_url, snippet, price, price_verified, availability,
                       currency, result_type, category, search_timestamp,
                       evidence_json, price_currency, price_type, price_method,
                       price_confidence, price_source_url, price_retrieved_at,
                       price_unverified_reason, retrieval_status, retrieval_reason,
                       identity_match, identity_reasons,
                       rating, rating_status, rating_reason, rating_retrieved_at, rating_provider
                FROM product_evidence
                WHERE reference = ?
                """,
                (str(reference).strip(),),
            ).fetchone()
        if row is None:
            return None
        try:
            price = float(row[7]) if row[7] is not None else None
        except (TypeError, ValueError):
            price = None
        return {
            "reference": row[0],
            "title": row[1],
            "source_url": row[2],
            "source_domain": row[3],
            "retailer": row[4] or row[3],
            "image_url": row[5],
            "snippet": row[6],
            "price": price,
            "price_verified": bool(row[8]),
            "availability": row[9],
            "currency": row[10] or "USD",
            "result_type": row[11],
            "category": row[12],
            "search_timestamp": row[13],
            "evidence": json.loads(row[14] or "{}"),
            "price_currency": row[15] or "",
            "price_type": row[16] or "",
            "price_method": row[17] or "",
            "price_confidence": row[18] or "",
            "price_source_url": row[19] or "",
            "price_retrieved_at": row[20] or "",
            "price_unverified_reason": row[21] or "",
            "retrieval_status": row[22] or "",
            "retrieval_reason": row[23] or "",
            "identity_match": row[24] or "UNKNOWN",
            "identity_reasons": _load_json_list(row[25]),
            "rating": float(row[26]) if row[26] not in (None, "") else None,
            "rating_status": row[27] or "",
            "rating_reason": row[28] or "",
            "rating_retrieved_at": row[29] or "",
            "rating_provider": row[30] or "",
            "review_count": (
                json.loads(row[14] or "{}").get("review_count")
                if row[14]
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Guard Buy decisions
    # ------------------------------------------------------------------
    def create_decision(
        self,
        *,
        product_reference: str,
        user_id: str,
        agent_id: str,
        amount: str,
        currency: str,
        quantity: int,
        category: str,
        merchant_name: str,
        decision: str,
        payment_status: str,
        risk_score: Optional[int],
        risk_level: str,
        reason: str,
        evaluation: Optional[dict],
        status: str,
        idempotency_key: Optional[str] = None,
    ) -> str:
        reference = f"gb_{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guard_buy_decisions (
                    decision_reference, product_reference, user_id, agent_id,
                    amount, currency, quantity, category, merchant_name,
                    decision, payment_status, risk_score, risk_level, reason,
                    evaluation_json, created_at, status, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference,
                    product_reference,
                    user_id,
                    agent_id,
                    str(amount),
                    currency.upper(),
                    int(quantity),
                    category,
                    merchant_name,
                    decision,
                    payment_status,
                    risk_score,
                    risk_level,
                    reason,
                    None if evaluation is None else json.dumps(evaluation, separators=(",", ":")),
                    _utc_now(),
                    status,
                    idempotency_key,
                ),
            )
        return reference

    def get_decision(self, decision_reference: str) -> Optional[dict]:
        if not decision_reference or not str(decision_reference).strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                 SELECT decision_reference, product_reference, user_id, agent_id,
                       amount, currency, quantity, category, merchant_name,
                       decision, payment_status, risk_score, risk_level, reason,
                       evaluation_json, created_at, status, idempotency_key,
                       reviewed_by, reviewed_at
                FROM guard_buy_decisions
                WHERE decision_reference = ?
                """,
                (str(decision_reference).strip(),),
            ).fetchone()
        if row is None:
            return None
        return {
            "decision_reference": row[0],
            "product_reference": row[1],
            "user_id": row[2],
            "agent_id": row[3],
            "amount": row[4],
            "currency": row[5],
            "quantity": row[6],
            "category": row[7],
            "merchant_name": row[8],
            "decision": row[9],
            "payment_status": row[10],
            "risk_score": row[11],
            "risk_level": row[12],
            "reason": row[13],
            "evaluation": json.loads(row[14]) if row[14] else None,
            "created_at": row[15],
            "status": row[16],
            "idempotency_key": row[17],
            "reviewed_by": row[18],
            "reviewed_at": row[19],
        }

    def get_decision_by_idempotency_key(self, key: str) -> Optional[dict]:
        if not key or not str(key).strip():
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT decision_reference FROM guard_buy_decisions WHERE idempotency_key = ?",
                (str(key).strip(),),
            ).fetchone()
        if row is None:
            return None
        return self.get_decision(row[0])

    def update_decision_after_review(
        self,
        decision_reference: str,
        *,
        decision: str,
        payment_status: str,
        risk_score: Optional[int],
        risk_level: str,
        reason: str,
        evaluation: Optional[dict],
        reviewed_by: Optional[str] = None,
    ) -> bool:
        reviewed_at = _utc_now() if reviewed_by else None
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE guard_buy_decisions
                SET decision = ?, payment_status = ?, risk_score = ?,
                    risk_level = ?, reason = ?, evaluation_json = ?,
                    status = ?,
                    reviewed_by = COALESCE(?, reviewed_by),
                    reviewed_at = COALESCE(?, reviewed_at)
                WHERE decision_reference = ?
                """,
                (
                    decision,
                    payment_status,
                    risk_score,
                    risk_level,
                    reason,
                    None if evaluation is None else json.dumps(evaluation, separators=(",", ":")),
                    "ACTIVE" if decision == "ALLOW" else "PENDING",
                    reviewed_by,
                    reviewed_at,
                    str(decision_reference).strip(),
                ),
            )
            return cursor.rowcount == 1

    def consume_decision(self, decision_reference: str) -> bool:
        """Atomically move an ACTIVE ALLOW decision to CONSUMED."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE guard_buy_decisions
                SET status = 'CONSUMED'
                WHERE decision_reference = ?
                  AND decision = 'ALLOW'
                  AND status = 'ACTIVE'
                """,
                (str(decision_reference).strip(),),
            )
            return cursor.rowcount == 1
