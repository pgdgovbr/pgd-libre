from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditAction, AuditLog
from ..models.user import User


async def log_audit(
    db: AsyncSession,
    *,
    table_name: str,
    record_id: str,
    action: AuditAction,
    user: User | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry
