"""Service: Reescrever com IA — Bedrock + auditoria + rate limit.

Espelha o padrão de `clipping/consolidator.py` (boto3 + invoke_model + retry
com ThrottlingException backoff). Retorno é síncrono: texto reescrito
+ contagem de tokens + latência.

Funções públicas:
- `reescrever_registro(...)` — chama o LLM e devolve o texto + métricas
- `registrar_evento_geracao(...)` — persiste AIRewriteEvent
- `marcar_evento_aplicado(db, event_id)` — flip applied=True
- `contar_eventos_ultima_hora(db, user_id)` — para rate limit
- `verificar_rate_limit(db, user_id, limit)` — (allowed, retry_after_seconds)
- `TEMPLATES` — descrição de cada template para injetar no user message
- `AI_SYSTEM_PROMPT`, `AI_USER_PROMPT_DEFAULT` — textos fixos do handoff
"""

from __future__ import annotations

import json
import logging
import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.ai_rewrite import AIRewriteEvent

logger = logging.getLogger(__name__)

TemplateId = Literal["entrega", "cronologico", "contribuicao", "star"]

AI_SYSTEM_PROMPT = """Você é um assistente especializado em comunicação institucional do serviço público federal brasileiro. Sua tarefa é REESCREVER o "Registro de Execução" mensal de um servidor participante do Programa de Gestão e Desempenho (PGD), seguindo o template indicado.

Regras invioláveis:
1. NÃO invente fatos, datas, números, sistemas ou nomes não citados pelo usuário.
2. NÃO altere o sentido das entregas relatadas.
3. Use linguagem formal, em português brasileiro, voz ativa, 1ª pessoa do singular.
4. Preserve referências a contribuições do Plano de Trabalho quando o usuário mencionar.
5. Quando o registro original for vago, NÃO complete com suposições — sinalize a lacuna entre colchetes: [precisa de detalhe].
6. Mantenha verbos no pretérito perfeito (entreguei, conduzi, documentei).
7. Se o template exigir métrica e ela não estiver no texto, deixe [quantificar] no lugar.

Saída: SOMENTE o texto reescrito, sem comentários, sem introdução, sem instruções adicionais."""

AI_USER_PROMPT_DEFAULT = """Reescreva o texto acima usando o template selecionado.

Destaque entregas concretas e evite generalidades. Vincule cada item, quando possível, a uma contribuição do meu plano. Se algum trecho estiver vago, sinalize com [precisa de detalhe] em vez de inventar."""

TEMPLATES: dict[str, dict[str, str]] = {
    "entrega": {
        "nome": "Por entrega",
        "desc": (
            "Estruture como uma lista numerada de ENTREGAS. Para cada entrega: "
            "nome no topo, contribuição vinculada do PT (se houver), e linhas "
            "curtas com Resultado, Volume/Quantidade, Pendências. Use formato "
            "hierárquico com indentação."
        ),
    },
    "cronologico": {
        "nome": "Cronológico",
        "desc": (
            "Estruture em blocos semanais (SEMANA 1, SEMANA 2…). Em cada "
            "semana, parágrafo único descrevendo atividades em ordem temporal. "
            "Use datas quando o usuário fornecer."
        ),
    },
    "contribuicao": {
        "nome": "Por contribuição do plano",
        "desc": (
            "Agrupe as entregas POR CONTRIBUIÇÃO do Plano de Trabalho. Cada "
            "bloco começa com o nome da contribuição e percentual. Embaixo, "
            "bullets com as atividades vinculadas àquela contribuição."
        ),
    },
    "star": {
        "nome": "STAR",
        "desc": (
            "Estruture em 4 blocos exatamente nesta ordem: SITUAÇÃO (contexto "
            "do mês), TAREFA (o que tinha que fazer), AÇÃO (o que fez), "
            "RESULTADO (entregas concretas mensuráveis). Mantenha 1 parágrafo "
            "curto por bloco."
        ),
    },
}


class RewriteError(Exception):
    """Erro irrecuperável ao chamar o LLM (timeout, 5xx persistente, etc)."""


class TemplateInvalidoError(ValueError):
    """template_id não está em TEMPLATES."""


def _bedrock_client():
    import boto3  # local para facilitar mock

    settings = get_settings()
    return boto3.client("bedrock-runtime", region_name=settings.AWS_DEFAULT_REGION)


def _build_messages(
    *, texto_atual: str, template_id: TemplateId, instrucao_adicional: str
) -> list[dict]:
    if template_id not in TEMPLATES:
        raise TemplateInvalidoError(f"template_id inválido: {template_id}")
    tpl = TEMPLATES[template_id]
    user = (
        "## Registro original do servidor:\n\n"
        f"{texto_atual}\n\n"
        f"## Template solicitado: {tpl['nome']}\n\n"
        f"{tpl['desc']}\n\n"
        "## Instrução adicional do usuário:\n\n"
        f"{instrucao_adicional}"
    )
    return [{"role": "user", "content": user}]


def reescrever_registro(
    *,
    texto_atual: str,
    template_id: TemplateId,
    instrucao_adicional: str,
    client=None,
) -> tuple[str, int, int, int]:
    """Chama Bedrock e retorna (texto_reescrito, tokens_in, tokens_out, latency_ms).

    Levanta TemplateInvalidoError se template_id for desconhecido.
    Levanta RewriteError se todas as tentativas de retry falharem.
    """
    from botocore.exceptions import ClientError

    settings = get_settings()
    messages = _build_messages(
        texto_atual=texto_atual,
        template_id=template_id,
        instrucao_adicional=instrucao_adicional,
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": settings.BEDROCK_MAX_TOKENS,
        "temperature": 0.3,
        "system": AI_SYSTEM_PROMPT,
        "messages": messages,
    }
    bedrock = client or _bedrock_client()
    last_err: Exception | None = None
    started = time.time()
    for attempt in range(settings.BEDROCK_MAX_RETRIES):
        try:
            response = bedrock.invoke_model(
                modelId=settings.BEDROCK_MODEL_ID,
                body=json.dumps(body),
            )
            raw = response["body"].read()
            payload = json.loads(raw)
            text = payload["content"][0]["text"]
            usage = payload.get("usage", {})
            tokens_in = int(usage.get("input_tokens", 0))
            tokens_out = int(usage.get("output_tokens", 0))
            latency = int((time.time() - started) * 1000)
            logger.info(
                f"Bedrock rewrite ok (attempt {attempt + 1}, "
                f"{len(text)} chars, in={tokens_in}, out={tokens_out}, {latency}ms)"
            )
            return text, tokens_in, tokens_out, latency
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            last_err = exc
            logger.warning(
                f"Bedrock rewrite attempt {attempt + 1}/{settings.BEDROCK_MAX_RETRIES} "
                f"failed: {code} — {exc}"
            )
            if attempt < settings.BEDROCK_MAX_RETRIES - 1:
                if code == "ThrottlingException":
                    sleep_s = 1.0 * (2**attempt) + random.uniform(0, 0.5)
                else:
                    sleep_s = 0.2 * (2**attempt)
                time.sleep(sleep_s)
    raise RewriteError(
        f"Bedrock falhou após {settings.BEDROCK_MAX_RETRIES} tentativas"
    ) from last_err


async def contar_eventos_ultima_hora(db: AsyncSession, user_id: int) -> int:
    """Conta AIRewriteEvent do usuário na última hora (usado pelo rate limit)."""
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    result = await db.execute(
        select(func.count(AIRewriteEvent.id)).where(
            AIRewriteEvent.user_id == user_id,
            AIRewriteEvent.created_at >= cutoff,
        )
    )
    return int(result.scalar_one())


async def verificar_rate_limit(
    db: AsyncSession, user_id: int, limit: int | None = None
) -> tuple[bool, int]:
    """Retorna (allowed, retry_after_seconds)."""
    settings = get_settings()
    effective_limit = limit if limit is not None else settings.AI_REWRITE_RATE_LIMIT_PER_HOUR
    n = await contar_eventos_ultima_hora(db, user_id)
    if n < effective_limit:
        return True, 0
    # Retry-after: tempo até o evento mais antigo dentro da janela sair
    result = await db.execute(
        select(func.min(AIRewriteEvent.created_at)).where(
            AIRewriteEvent.user_id == user_id,
            AIRewriteEvent.created_at >= datetime.now(UTC) - timedelta(hours=1),
        )
    )
    earliest = result.scalar_one_or_none()
    if earliest is None:
        return True, 0
    retry_after = int((earliest + timedelta(hours=1) - datetime.now(UTC)).total_seconds())
    return False, max(retry_after, 1)


async def registrar_evento_geracao(
    db: AsyncSession,
    *,
    user_id: int,
    registro_id: uuid.UUID | None,
    template_id: str,
    instrucao_custom: bool,
    chars_in: int,
    chars_out: int,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    model: str,
    ip_address: str | None = None,
    error_message: str | None = None,
) -> AIRewriteEvent:
    ev = AIRewriteEvent(
        user_id=user_id,
        registro_id=registro_id,
        template_id=template_id,
        instrucao_custom=instrucao_custom,
        chars_in=chars_in,
        chars_out=chars_out,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        model=model,
        ip_address=ip_address,
        error_message=error_message,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


async def marcar_evento_aplicado(
    db: AsyncSession, *, event_id: uuid.UUID, user_id: int
) -> AIRewriteEvent | None:
    """Marca evento como aplicado se pertencer ao user. Retorna None se não pertencer."""
    result = await db.execute(
        select(AIRewriteEvent).where(
            AIRewriteEvent.id == event_id,
            AIRewriteEvent.user_id == user_id,
        )
    )
    ev = result.scalar_one_or_none()
    if ev is None:
        return None
    ev.applied = True
    await db.commit()
    await db.refresh(ev)
    return ev
