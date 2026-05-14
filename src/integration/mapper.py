"""Maps local SQLAlchemy models to api-pgd-central JSON payloads."""

from ..models.participante import Participante
from ..models.plano import (
    AvaliacaoRegistrosExecucao,
    Contribuicao,
    Entrega,
    PlanoEntregas,
    PlanoTrabalho,
)


def _entrega(e: Entrega) -> dict:
    return {
        "id_entrega": e.id_entrega,
        "entrega_cancelada": e.entrega_cancelada,
        "nome_entrega": e.nome_entrega,
        "meta_entrega": e.meta_entrega,
        "tipo_meta": e.tipo_meta.value,
        "data_entrega": e.data_entrega.isoformat(),
        "nome_unidade_demandante": e.nome_unidade_demandante,
        "nome_unidade_destinataria": e.nome_unidade_destinataria,
    }


def _contribuicao(c: Contribuicao) -> dict:
    d = {
        "id_contribuicao": c.id_contribuicao,
        "tipo_contribuicao": c.tipo_contribuicao,
        "percentual_contribuicao": c.percentual_contribuicao,
        "id_plano_entregas": c.id_plano_entregas,
        "id_entrega": c.id_entrega,
    }
    if c.rotulo is not None:
        d["rotulo"] = c.rotulo
    return d


def _avaliacao_registros_execucao(a: AvaliacaoRegistrosExecucao) -> dict | None:
    """Returns None for records not yet evaluated (api-pgd requires both fields)."""
    if a.avaliacao_registros_execucao is None or a.data_avaliacao_registros_execucao is None:
        return None
    return {
        "id_periodo_avaliativo": a.id_periodo_avaliativo,
        "data_inicio_periodo_avaliativo": a.data_inicio_periodo_avaliativo.isoformat(),
        "data_fim_periodo_avaliativo": a.data_fim_periodo_avaliativo.isoformat(),
        "avaliacao_registros_execucao": a.avaliacao_registros_execucao,
        "data_avaliacao_registros_execucao": a.data_avaliacao_registros_execucao.isoformat(),
    }


def plano_entregas_to_payload(pe: PlanoEntregas) -> dict:
    return {
        "origem_unidade": pe.origem_unidade.value,
        "cod_unidade_autorizadora": pe.cod_unidade_autorizadora,
        "cod_unidade_instituidora": pe.cod_unidade_instituidora,
        "cod_unidade_executora": pe.cod_unidade_executora,
        "id_plano_entregas": pe.id_plano_entregas,
        "status": pe.status,
        "data_inicio": pe.data_inicio.isoformat(),
        "data_termino": pe.data_termino.isoformat(),
        "avaliacao": pe.avaliacao,
        "data_avaliacao": pe.data_avaliacao.isoformat() if pe.data_avaliacao else None,
        "entregas": [_entrega(e) for e in pe.entregas],
    }


def plano_trabalho_to_payload(pt: PlanoTrabalho) -> dict:
    avaliacoes = [
        a_dict for a in pt.avaliacoes if (a_dict := _avaliacao_registros_execucao(a)) is not None
    ]
    return {
        "origem_unidade": pt.origem_unidade.value,
        "cod_unidade_autorizadora": pt.cod_unidade_autorizadora,
        "id_plano_trabalho": pt.id_plano_trabalho,
        "status": pt.status,
        "cod_unidade_executora": pt.cod_unidade_executora,
        "cpf_participante": pt.cpf_participante,
        "matricula_siape": pt.matricula_siape,
        "cod_unidade_lotacao_participante": pt.cod_unidade_lotacao_participante,
        "data_inicio": pt.data_inicio.isoformat(),
        "data_termino": pt.data_termino.isoformat(),
        "carga_horaria_disponivel": pt.carga_horaria_disponivel,
        "contribuicoes": [_contribuicao(c) for c in pt.contribuicoes],
        "avaliacoes_registros_execucao": avaliacoes,
    }


def participante_to_payload(p: Participante) -> dict:
    return {
        "origem_unidade": p.origem_unidade.value,
        "cod_unidade_autorizadora": p.cod_unidade_autorizadora,
        "cod_unidade_lotacao": p.cod_unidade_lotacao,
        "matricula_siape": p.matricula_siape,
        "cod_unidade_instituidora": p.cod_unidade_instituidora,
        "cpf": p.cpf,
        "situacao": p.situacao,
        "modalidade_execucao": p.modalidade_execucao,
        "data_assinatura_tcr": p.data_assinatura_tcr.isoformat(),
    }
