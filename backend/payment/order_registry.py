import os
import sqlite3
import json
from pathlib import Path


class OrderRegistry:
    """Persistent, atomic registry for PayPal order processing."""

    def __init__(self, db_path=None):
        self.db_path = str(
            db_path
            or os.getenv(
                "PAYSHIELD_DB_PATH",
                "payshield_payments.sqlite3",
            )
        )

        Path(self.db_path).parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS processed_orders (
                    order_id TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL DEFAULT
                        (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS order_reservations (
                    order_id TEXT PRIMARY KEY,
                    reserved_at TEXT NOT NULL DEFAULT
                        (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    status TEXT NOT NULL DEFAULT 'RESERVED'
                        CHECK (status IN ('RESERVED', 'COMPLETED'))
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS checkout_orders (
                    order_id TEXT PRIMARY KEY,
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    merchant_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT
                        (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS integration_requests (
                    idempotency_key TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT
                        (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)
            existing_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(checkout_orders)"
                )
            }
            for name, definition in (
                ("transaction_id", "TEXT"),
                ("external_order_id", "TEXT"),
                ("items_json", "TEXT"),
                ("status", "TEXT NOT NULL DEFAULT 'AWAITING_BUYER_APPROVAL'"),
            ):
                if name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE checkout_orders ADD COLUMN {name} {definition}"
                    )

    def _connect(self):
        return sqlite3.connect(
            self.db_path,
            timeout=10,
        )

    @staticmethod
    def _validate_order_id(order_id: str) -> str:
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("Order ID is required")

        return order_id.strip()

    def is_processed(self, order_id: str) -> bool:
        """Return whether an order has already been processed."""
        order_id = self._validate_order_id(order_id)

        with self._connect() as connection:
            result = connection.execute(
                """
                SELECT 1
                FROM processed_orders
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()

        return result is not None

    def mark_processed(self, order_id: str) -> bool:
        """Atomically mark an order processed; reject duplicates."""
        order_id = self._validate_order_id(order_id)

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO processed_orders (order_id)
                VALUES (?)
                """,
                (order_id,),
            )

            inserted = cursor.rowcount == 1

            if inserted:
                connection.execute(
                    """
                    INSERT INTO order_reservations (order_id, status)
                    VALUES (?, 'COMPLETED')
                    ON CONFLICT(order_id)
                    DO UPDATE SET status = 'COMPLETED'
                    """,
                    (order_id,),
                )

            return inserted

    def reserve_order(self, order_id: str) -> bool:
        """
        Atomically claim an order before processing.

        Returns True only for the first reservation.
        A processed or already-reserved order returns False.
        """
        order_id = self._validate_order_id(order_id)

        with self._connect() as connection:
            # BEGIN IMMEDIATE obtains a write reservation before checking.
            connection.execute("BEGIN IMMEDIATE")

            processed = connection.execute(
                """
                SELECT 1
                FROM processed_orders
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()

            if processed is not None:
                return False

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO order_reservations (order_id)
                VALUES (?)
                """,
                (order_id,),
            )

            return cursor.rowcount == 1

    def complete_reservation(self, order_id: str) -> bool:
        """Mark a reserved order as processed after confirmed success."""
        order_id = self._validate_order_id(order_id)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            reservation = connection.execute(
                """
                SELECT status
                FROM order_reservations
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()

            if reservation is None or reservation[0] != "RESERVED":
                return False

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO processed_orders (order_id)
                VALUES (?)
                """,
                (order_id,),
            )

            if cursor.rowcount != 1:
                return False

            connection.execute(
                """
                UPDATE order_reservations
                SET status = 'COMPLETED'
                WHERE order_id = ?
                """,
                (order_id,),
            )

            return True

    def release_reservation(self, order_id: str) -> bool:
        """
        Release a reservation only when it is safe to retry.

        Do not call this if the payment capture outcome is uncertain.
        """
        order_id = self._validate_order_id(order_id)

        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM order_reservations
                WHERE order_id = ?
                  AND status = 'RESERVED'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM processed_orders
                      WHERE processed_orders.order_id =
                            order_reservations.order_id
                  )
                """,
                (order_id,),
            )

            return cursor.rowcount == 1

    def register_checkout_order(
        self,
        order_id: str,
        amount: str,
        currency: str,
        agent_id: str,
        category: str,
        merchant_name: str,
        user_id: str,
        transaction_id: str | None = None,
        external_order_id: str | None = None,
        items: list[dict] | None = None,
    ) -> bool:
        """Persist the server-owned intent behind a PayPal order."""
        order_id = self._validate_order_id(order_id)

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO checkout_orders (
                    order_id, amount, currency, agent_id, category,
                    merchant_name, user_id, transaction_id,
                    external_order_id, items_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    str(amount),
                    currency.upper(),
                    agent_id,
                    category,
                    merchant_name,
                    user_id,
                    transaction_id,
                    external_order_id,
                    json.dumps(items or [], separators=(",", ":")),
                ),
            )
            return cursor.rowcount == 1

    def get_checkout_order(self, order_id: str):
        """Return the server-owned checkout intent for an order."""
        order_id = self._validate_order_id(order_id)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT order_id, amount, currency, agent_id, category,
                       merchant_name, user_id, transaction_id,
                       external_order_id, items_json, status
                FROM checkout_orders
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()

        if row is None:
            return None

        result = {
            "order_id": row[0],
            "amount": row[1],
            "currency": row[2],
            "agent_id": row[3],
            "category": row[4],
            "merchant_name": row[5],
            "user_id": row[6],
        }
        if row[7] is not None:
            result["transaction_id"] = row[7]
        if row[8] is not None:
            result["external_order_id"] = row[8]
        items = json.loads(row[9] or "[]")
        if items:
            result["items"] = items
        if row[10] != "AWAITING_BUYER_APPROVAL":
            result["status"] = row[10]
        return result

    def get_idempotent_response(self, key: str):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM integration_requests WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_idempotent_response(self, key: str, response: dict) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO integration_requests
                    (idempotency_key, response_json)
                VALUES (?, ?)
                """,
                (key, json.dumps(response, separators=(",", ":"))),
            )
            return cursor.rowcount == 1