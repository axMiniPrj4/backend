from sqlalchemy.orm import Session

from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User


def record_audit(
    db: Session,
    admin: User,
    *,
    action: str,
    target_type: str,
    target_id: int | None = None,
    target_label: str = "",
    detail: str | None = None,
) -> AdminAuditLog:
    log = AdminAuditLog(
        admin_id=admin.id,
        admin_login_id=admin.login_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label or "",
        detail=detail,
    )
    db.add(log)
    return log
