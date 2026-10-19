import json

from backend.audit.audit_logger import AuditLogger


def test_audit_record_is_saved(tmp_path):
    logger = AuditLogger(tmp_path / "audit.jsonl")

    result = logger.log_decision({
        "transaction_id": "TXN-001",
        "amount": 500,
        "risk_level": "LOW",
        "decision": "ALLOW",
    })

    assert result["transaction_id"] == "TXN-001"
    assert result["decision"] == "ALLOW"
    assert result["previous_hash"] == "GENESIS"
    assert result["record_hash"]


def test_audit_records_form_a_chain(tmp_path):
    logger = AuditLogger(tmp_path / "audit.jsonl")

    first = logger.log_decision({
        "transaction_id": "TXN-001",
        "decision": "ALLOW",
    })

    second = logger.log_decision({
        "transaction_id": "TXN-002",
        "decision": "BLOCK",
    })

    assert second["previous_hash"] == first["record_hash"]


def test_audit_log_is_persistent(tmp_path):
    path = tmp_path / "audit.jsonl"

    AuditLogger(path).log_decision({
        "transaction_id": "TXN-001",
        "decision": "REVIEW",
    })

    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]

    assert len(records) == 1
    assert records[0]["decision"] == "REVIEW"

def test_valid_audit_log_passes_verification(tmp_path):
    logger = AuditLogger(tmp_path / "audit.jsonl")

    logger.log_decision({
        "transaction_id": "TXN-001",
        "decision": "ALLOW",
    })
    logger.log_decision({
        "transaction_id": "TXN-002",
        "decision": "BLOCK",
    })

    assert logger.verify_integrity() is True


def test_modified_audit_record_fails_verification(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)

    logger.log_decision({
        "transaction_id": "TXN-001",
        "decision": "ALLOW",
    })

    record = json.loads(path.read_text(encoding="utf-8"))
    record["decision"] = "BLOCK"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    assert logger.verify_integrity() is False


def test_history_can_be_scoped_to_user(tmp_path):
    logger = AuditLogger(tmp_path / "audit.jsonl")
    logger.log_decision({"transaction_id": "TXN-A", "user_id": "user-a", "decision": "ALLOW"})
    logger.log_decision({"transaction_id": "TXN-B", "user_id": "user-b", "decision": "BLOCK"})

    from backend.audit.audit_service import AuditService

    records = AuditService(tmp_path / "audit.jsonl").get_history(user_id="user-a")

    assert [record["transaction_id"] for record in records] == ["TXN-A"]