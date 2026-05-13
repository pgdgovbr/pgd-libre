"""Sprint 1.6 — Auditoria: testes de imutabilidade e log (TC-M07)."""
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditAction, AuditLog
from src.models.institucional import OrigemUnidade
from src.models.user import UserRole
from src.services.audit import log_audit
from src.services.institucional import (
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
)

from .conftest import persist_user


async def test_audit_log_criado_ao_criar_ua(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Audit",
        sigla="UAA",
        user=admin,
    )
    result = await db.execute(
        select(AuditLog).where(AuditLog.table_name == "unidades_autorizadoras")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1
    log = logs[0]
    assert log.action == AuditAction.CREATE
    assert log.user_id == admin.id
    assert log.user_email == admin.email


async def test_audit_log_tem_old_e_new_values_no_update(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=2,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Status",
        sigla="UAS",
        user=admin,
    )
    ato = await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia="P001",
        user=admin,
    )
    from src.services.institucional import atualizar_status_ato
    from src.models.institucional import StatusAto

    await atualizar_status_ato(
        db, ato_id=ato.id, novo_status=StatusAto.SUSPENSO, user=admin
    )

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.table_name == "atos_autorizacao",
            AuditLog.action == AuditAction.UPDATE,
        )
    )
    log = result.scalar_one()
    assert log.old_values["status"] == "ativo"
    assert log.new_values["status"] == "suspenso"


async def test_audit_log_e_imutavel_sem_delete_api(db: AsyncSession):
    """AuditLog has no update/delete operations exposed in service layer."""
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    entry = await log_audit(
        db,
        table_name="test_table",
        record_id="abc-123",
        action=AuditAction.CREATE,
        user=admin,
        new_values={"field": "value"},
    )
    await db.commit()

    # Verify it's stored
    result = await db.execute(
        select(AuditLog).where(AuditLog.table_name == "test_table")
    )
    stored = result.scalar_one()
    assert stored.record_id == "abc-123"
    assert stored.new_values["field"] == "value"

    # No UPDATE or DELETE functions exist in audit service
    from src.services import audit as audit_svc
    public_fns = [fn for fn in dir(audit_svc) if not fn.startswith("_")]
    assert "delete_audit" not in public_fns
    assert "update_audit" not in public_fns


async def test_audit_log_sem_usuario_quando_sistema(db: AsyncSession):
    entry = await log_audit(
        db,
        table_name="test_sys",
        record_id="sys-001",
        action=AuditAction.CREATE,
        user=None,
    )
    await db.commit()
    assert entry.user_id is None
    assert entry.user_email is None
