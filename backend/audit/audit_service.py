import json
from pathlib import Path


class AuditService:
    def __init__(self, log_path="data/audit_log.jsonl"):
        self.log_path = Path(log_path)

    def get_history(self, limit=50):
        if not 1 <= limit <= 500:
            raise ValueError("Limit must be between 1 and 500")

        if not self.log_path.exists():
            return []

        records = []

        with self.log_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                records.append(record)

        return list(reversed(records[-limit:]))