"""Testes para src/models/ — enums, defaults e constraints."""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditAction, AuditLog
from src.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def test_user_role_enum_values() -> None:
    assert UserRole.ADMIN == "admin"
    assert UserRole.GESTOR_UNIDADE == "gestor_unidade"
    assert UserRole.CHEFE_IMEDIATO == "chefe_imediato"
    assert UserRole.SERVIDOR == "servidor"
    assert len(UserRole) == 4


def test_audit_action_enum_values() -> None:
    assert AuditAction.CREATE == "CREATE"
    assert AuditAction.UPDATE == "UPDATE"
    assert AuditAction.DELETE == "DELETE"
    assert len(AuditAction) == 3


# ---------------------------------------------------------------------------
# User — defaults e persistência
# ---------------------------------------------------------------------------

async def test_user_default_role_is_servidor(db: AsyncSession) -> None:
    user = User(email="def@test.gov.br", name="Default")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert user.role == UserRole.SERVIDOR


async def test_user_default_is_active(db: AsyncSession) -> None:
    user = User(email="active@test.gov.br", name="Active")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert user.is_active is True


async def test_user_gets_pk_after_persist(db: AsyncSession) -> None:
    user = User(email="pk@test.gov.br", name="PK")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert isinstance(user.id, int)
    assert user.id > 0


async def test_user_created_at_set_automatically(db: AsyncSession) -> None:
    user = User(email="ts@test.gov.br", name="TS")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    assert user.created_at is not None


# ---------------------------------------------------------------------------
# User — constraint de e-mail único
# ---------------------------------------------------------------------------

async def test_user_email_unique_constraint(db: AsyncSession) -> None:
    u1 = User(email="dup@test.gov.br", name="U1")
    u2 = User(email="dup@test.gov.br", name="U2")
    db.add(u1)
    db.add(u2)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ---------------------------------------------------------------------------
# AuditLog — persistência básica
# ---------------------------------------------------------------------------

async def test_audit_log_persists(db: AsyncSession) -> None:
    log = AuditLog(
        table_name="users",
        record_id="99",
        action=AuditAction.CREATE,
        new_values={"email": "x@x.br"},
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    assert isinstance(log.id, int)
    assert log.action == AuditAction.CREATE
    assert log.new_values == {"email": "x@x.br"}
    assert log.old_values is None
    assert log.created_at is not None


async def test_audit_log_supports_all_actions(db: AsyncSession) -> None:
    for action in AuditAction:
        log = AuditLog(table_name="t", record_id="1", action=action)
        db.add(log)
    await db.commit()
