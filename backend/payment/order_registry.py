import os
import sqlite3
import json
from pathlib import Path


class OrderRegistry:
    """Persistent, atomic registry for PayPal order processing."""

    # Checkout order lifecycle states. AWAITING_BUYER_APPROVAL is the default
    # recorded when a PayPal order is created; the server transitions the order
    # through AUTHORIZED / CAPTURE_PENDING only after server-side verification
    # and a PayShield ALLOW decision, and to COMPLETED / BLOCKED / FAILED only
    # on a definitive capture outcome.
    STATUS_AWAITING_BUYER_APPROVAL = "AWAITING_BUYER_APPROVAL"
    STATUS_AUTHORIZED = "AUTHORIZED"
    STATUS_CAPTURE_PENDING = "CAPTURE_PENDING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_BLOCKED = "BLOCKED"
    STATUS_FAILED = "FAILED"

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

            connection.execute("""
                CREATE TABLE IF NOT EXISTS agent_budgets (
                    agent_id TEXT PRIMARY KEY,
                    spending_limit_cents INTEGER NOT NULL,
                    spent_cents INTEGER NOT NULL DEFAULT 0,
                    reserved_cents INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT
                        (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS agent_budget_reservations (
                    idempotency_key TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'RESERVED'
                        CHECK (status IN ('RESERVED', 'COMMITTED', 'RELEASED')),
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
                ("idempotency_key", "TEXT"),
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

    # ------------------------------------------------------------------
    # Per-agent spending budget (atomic, persistent)
    # ------------------------------------------------------------------

    @staticmethod
    def _to_cents(amount: float) -> int:
        """Convert a dollar amount to integer cents for exact budget arithmetic."""
        return int(round(float(amount) * 100))

    def reserve_agent_budget(
        self,
        agent_id: str,
        amount: float,
        idempotency_key: str,
        spending_limit: float,
    ) -> bool:
        """
        Atomically check and reserve budget for one agent in a single
        transaction.

        Returns True only when the reservation was recorded. A reservation is
        refused when the idempotency key already has a RESERVED/COMMITTED
        reservation (duplicate attempts never double-count) or when
        spent + reserved + amount would exceed the agent's spending limit.
        """
        if not agent_id or not idempotency_key:
            return False
        amount_cents = self._to_cents(amount)
        limit_cents = self._to_cents(spending_limit)
        if amount_cents <= 0 or limit_cents <= 0:
            return False

        with self._connect() as connection:
            # BEGIN IMMEDIATE obtains the write lock before reading, so
            # concurrent requests serialize and cannot jointly over-reserve.
            connection.execute("BEGIN IMMEDIATE")

            connection.execute(
                """
                INSERT INTO agent_budgets (agent_id, spending_limit_cents, spent_cents, reserved_cents)
                VALUES (?, ?, 0, 0)
                ON CONFLICT(agent_id)
                DO UPDATE SET spending_limit_cents = excluded.spending_limit_cents
                """,
                (agent_id, limit_cents),
            )

            existing = connection.execute(
                """
                SELECT status, amount_cents
                FROM agent_budget_reservations
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()

            # The same purchase attempt must never reserve twice. An existing
            # RESERVED or COMMITTED reservation for this key is counted once.
            if existing is not None and existing[0] in ("RESERVED", "COMMITTED"):
                return True

            row = connection.execute(
                """
                SELECT spent_cents, reserved_cents
                FROM agent_budgets
                WHERE agent_id = ?
                """,
                (agent_id,),
            ).fetchone()
            spent_cents, reserved_cents = int(row[0] or 0), int(row[1] or 0)

            if spent_cents + reserved_cents + amount_cents > limit_cents:
                return False  # Budget exhausted: this purchase would exceed the limit.

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO agent_budget_reservations
                        (idempotency_key, agent_id, amount_cents, status)
                    VALUES (?, ?, ?, 'RESERVED')
                    """,
                    (idempotency_key, agent_id, amount_cents),
                )
            else:
                # A RELEASED reservation for the same attempt may be re-reserved.
                connection.execute(
                    """
                    UPDATE agent_budget_reservations
                    SET status = 'RESERVED', amount_cents = ?
                    WHERE idempotency_key = ?
                    """,
                    (amount_cents, idempotency_key),
                )

            connection.execute(
                """
                UPDATE agent_budgets
                SET reserved_cents = reserved_cents + ?,
                    updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                WHERE agent_id = ?
                """,
                (amount_cents, agent_id),
            )

            return True

    def commit_agent_budget(self, idempotency_key: str, amount: float) -> bool:
        """Transition a RESERVED budget reservation to COMMITTED (spent).

        Called once a capture is confirmed. A non-reserved reservation is a
        no-op so direct capture calls (without a preceding purchase reservation)
        are unaffected.
        """
        if not idempotency_key:
            return False
        amount_cents = self._to_cents(amount)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            row = connection.execute(
                """
                SELECT agent_id, amount_cents, status
                FROM agent_budget_reservations
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()

            if row is None or row[2] != "RESERVED":
                return False

            agent_id, reserved_cents = row[0], int(row[1] or 0)

            connection.execute(
                """
                UPDATE agent_budget_reservations
                SET status = 'COMMITTED'
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            )
            connection.execute(
                """
                UPDATE agent_budgets
                SET reserved_cents = reserved_cents - ?,
                    spent_cents = spent_cents + ?,
                    updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                WHERE agent_id = ?
                """,
                (reserved_cents, reserved_cents, agent_id),
            )
            return True

    def release_agent_budget(self, idempotency_key: str) -> bool:
        """Release a RESERVED budget reservation for a failed/cancelled attempt.

        Only RESERVED reservations can be released: COMMITTED captures are
        final spending, and already-released reservations are a no-op.
        """
        if not idempotency_key:
            return False

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            row = connection.execute(
                """
                SELECT agent_id, amount_cents, status
                FROM agent_budget_reservations
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()

            if row is None or row[2] != "RESERVED":
                return False

            agent_id, amount_cents = row[0], int(row[1] or 0)

            connection.execute(
                """
                UPDATE agent_budget_reservations
                SET status = 'RELEASED'
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            )
            connection.execute(
                """
                UPDATE agent_budgets
                SET reserved_cents = reserved_cents - ?,
                    updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                WHERE agent_id = ?
                """,
                (amount_cents, agent_id),
            )
            return True

    def get_agent_budget(self, agent_id: str):
        """Return the current budget state for an agent (cents, for exact tests)."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT spending_limit_cents, spent_cents, reserved_cents
                FROM agent_budgets
                WHERE agent_id = ?
                """,
                (agent_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "agent_id": agent_id,
            "spending_limit_cents": int(row[0] or 0),
            "spent_cents": int(row[1] or 0),
            "reserved_cents": int(row[2] or 0),
        }

    def link_order_to_idempotency_key(self, order_id: str, idempotency_key: str) -> bool:
        """Bind a PayPal order to its purchase idempotency key.

        Capture uses this to commit or release the budget reserved for the
        corresponding purchase attempt.
        """
        order_id = self._validate_order_id(order_id)
        if not idempotency_key:
            return False
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE checkout_orders
                SET idempotency_key = ?
                WHERE order_id = ?
                """,
                (idempotency_key, order_id),
            )
            return cursor.rowcount == 1

    def get_idempotency_key_for_order(self, order_id: str):
        """Return the purchase idempotency key bound to a PayPal order, if any."""
        order_id = self._validate_order_id(order_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT idempotency_key
                FROM checkout_orders
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()
        return row[0] if row else None

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

    def set_checkout_order_status(self, order_id: str, status: str) -> bool:
        """Transition a registered checkout order to a new lifecycle state.

        Only the server may advance this state; it reflects the authoritative
        order lifecycle, not a browser return URL.
        """
        order_id = self._validate_order_id(order_id)
        if not isinstance(status, str) or not status.strip():
            raise ValueError("Status is required")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE checkout_orders
                SET status = ?
                WHERE order_id = ?
                """,
                (status.strip(), order_id),
            )
            return cursor.rowcount == 1

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