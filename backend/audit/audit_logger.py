import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    def __init__(self, log_path="data/audit_log.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_decision(self, decision_data):
        """Append a payment decision with a tamper-evident hash."""

        if not isinstance(decision_data, dict):
            raise ValueError("Decision data must be a dictionary")

        record = dict(decision_data)
        record["timestamp"] = datetime.now(
            timezone.utc
        ).isoformat()

        canonical_record = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
        )

        previous_hash = self._get_last_hash()

        record["previous_hash"] = previous_hash
        hash_payload = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
        )

        record["record_hash"] = hashlib.sha256(
            hash_payload.encode("utf-8")
        ).hexdigest()

        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(record, sort_keys=True) + "\n"
            )

        return record

    def _get_last_hash(self):
        if not self.log_path.exists():
            return "GENESIS"

        with self.log_path.open("rb") as file:
            for line in reversed(file.readlines()):
                if line.strip():
                    return json.loads(line)["record_hash"]

        return "GENESIS"

    def verify_integrity(self):
        """Verify the audit log hash chain."""
        if not self.log_path.exists():
            return True

        expected_previous_hash = "GENESIS"

        with self.log_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return False

                stored_hash = record.pop("record_hash", None)

                if record.get("previous_hash") != expected_previous_hash:
                    return False

                payload = json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                )

                calculated_hash = hashlib.sha256(
                    payload.encode("utf-8")
                ).hexdigest()

                if stored_hash != calculated_hash:
                    return False

                expected_previous_hash = stored_hash

        return True