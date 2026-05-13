from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notificacao import Notificacao, TipoEvento


async def criar_notificacao(
    db: AsyncSession,
    *,
    tipo_evento: TipoEvento,
    conteudo: str,
    destinatario_user_id: int | None = None,
    destinatario_email: str | None = None,
    contexto: dict | None = None,
) -> Notificacao:
    n = Notificacao(
        tipo_evento=tipo_evento,
        conteudo=conteudo,
        destinatario_user_id=destinatario_user_id,
        destinatario_email=destinatario_email,
        contexto=contexto,
    )
    db.add(n)
    await db.flush()
    return n
