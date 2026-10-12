import os

from fastapi import APIRouter, HTTPException, Query

from backend.audit.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit"])


def get_audit_service():
    return AuditService(
        os.getenv("PAYSHIELD_AUDIT_LOG", "data/audit_log.jsonl")
    )


@router.get("/history")
def audit_history(
    limit: int = Query(default=50, ge=1, le=500),
):
    try:
        return {
            "records": get_audit_service().get_history(limit=limit)
        }
    except OSError:
        raise HTTPException(
            status_code=500,
            detail="Unable to read audit history",
        )