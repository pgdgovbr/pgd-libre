from datetime import UTC, datetime

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
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


def _make_mail_config() -> ConnectionConfig:
    s = get_settings()
    return ConnectionConfig(
        MAIL_USERNAME=s.MAIL_USERNAME,
        MAIL_PASSWORD=s.MAIL_PASSWORD,  # type: ignore[arg-type]
        MAIL_FROM=s.MAIL_FROM,  # type: ignore[arg-type]
        MAIL_PORT=s.MAIL_PORT,
        MAIL_SERVER=s.MAIL_SERVER,
        MAIL_STARTTLS=s.MAIL_STARTTLS,
        MAIL_SSL_TLS=s.MAIL_SSL_TLS,
        USE_CREDENTIALS=bool(s.MAIL_USERNAME),
        VALIDATE_CERTS=False,
    )


async def enviar_notificacoes_pendentes(
    db: AsyncSession,
    mail: FastMail | None = None,
) -> int:
    """Sends all unsent notifications. Returns count sent."""
    from ..models.user import User

    result = await db.execute(select(Notificacao).where(Notificacao.enviada == False))  # noqa: E712
    pendentes = result.scalars().all()
    if not pendentes:
        return 0

    user_ids = {n.destinatario_user_id for n in pendentes if n.destinatario_user_id}
    user_emails: dict[int, str] = {}
    if user_ids:
        r = await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))
        user_emails = {row.id: row.email for row in r}

    if mail is None:
        mail = FastMail(_make_mail_config())

    count = 0
    for n in pendentes:
        email = n.destinatario_email or user_emails.get(n.destinatario_user_id)  # type: ignore[arg-type]
        if not email:
            continue
        msg = MessageSchema(
            subject=f"PGD Libre: {n.tipo_evento.value.replace('_', ' ').title()}",
            recipients=[email],  # type: ignore[list-item]
            body=n.conteudo,
            subtype=MessageType.plain,
        )
        await mail.send_message(msg)
        n.enviada = True
        n.enviada_em = datetime.now(UTC)
        count += 1

    await db.commit()
    return count
