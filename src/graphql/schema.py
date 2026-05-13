import uuid
from datetime import date
from typing import Optional

import strawberry
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from ..auth.deps import get_optional_user
from ..database import get_db
from ..models.institucional import OrigemUnidade, StatusAto, StatusPgd
from ..models.participante import MotivoDesligamento, RegimeExecucao, TipoVinculo
from ..models.plano import DecisaoRecurso, TipoMeta
from ..models.user import User
from ..models.notificacao import TipoEvento as _TipoEvento
from ..services import avaliacao as av_svc
from ..services import institucional as svc
from ..services import notificacao as notif_svc
from ..services import participante as participante_svc
from ..services import plano_entregas as pe_svc
from ..services import plano_trabalho as pt_svc
from .institucional import (
    AtoAutorizacaoType,
    CriarAtoAutorizacaoInput,
    CriarUnidadeAutorizadoraInput,
    CriarUnidadeInstituidoraInput,
    OrigemUnidadeGql,
    ResultadoPublicoType,
    StatusAtoGql,
    UnidadeAutorizadoraType,
    UnidadeInstituidoraType,
    _ato_to_type,
    _ua_to_type,
    _ui_to_type,
)
from .participante import (
    CadastrarParticipanteInput,
    ConvocacaoType,
    CriarConvocacaoInput,
    MotivoDesligamentoGql,
    ParticipanteType,
    PactuarTCRInput,
    TCRType,
    _convocacao_to_type,
    _participante_to_type,
    _tcr_to_type,
)
from .permissions import IsAdmin
from .notificacao import NotificacaoType, _notificacao_to_type
from .plano import (
    AdicionarContribuicaoInput,
    AvaliacaoType,
    ContribuicaoType,
    CriarEntregaInput,
    CriarPlanoEntregasInput,
    CriarPlanoTrabalhoInput,
    DecisaoRecursoGql,
    EntregaType,
    PlanoEntregasType,
    PlanoTrabalhoType,
    RegistrarExecucaoInput,
    _avaliacao_to_type,
    _contribuicao_to_type,
    _entrega_to_type,
    _pe_to_type,
    _pt_to_type,
)


def _ip(info: Info) -> str | None:
    request: Request = info.context["request"]
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@strawberry.type
class UserType:
    id: int
    email: str
    name: str
    role: str


@strawberry.type
class Query:
    @strawberry.field
    def health(self) -> str:
        return "ok"

    @strawberry.field
    def me(self, info: Info) -> UserType | None:
        user: User | None = info.context.get("user")
        if not user:
            return None
        return UserType(
            id=user.id, email=user.email, name=user.name, role=user.role.value
        )

    # --- Sprint 1.1 ---

    @strawberry.field(permission_classes=[IsAdmin])
    async def unidade_autorizadora(
        self, info: Info, id: strawberry.ID
    ) -> UnidadeAutorizadoraType | None:
        db: AsyncSession = info.context["db"]
        ua = await svc.get_unidade_autorizadora(db, uuid.UUID(str(id)))
        return _ua_to_type(ua) if ua else None

    @strawberry.field(permission_classes=[IsAdmin])
    async def unidade_instituidora(
        self, info: Info, id: strawberry.ID
    ) -> UnidadeInstituidoraType | None:
        db: AsyncSession = info.context["db"]
        ui = await svc.get_unidade_instituidora(db, uuid.UUID(str(id)))
        return _ui_to_type(ui) if ui else None

    @strawberry.field
    async def resultados_publicos(self, info: Info) -> list[ResultadoPublicoType]:
        db: AsyncSession = info.context["db"]
        rows = await svc.listar_resultados_publicos(db)
        return [ResultadoPublicoType(**r) for r in rows]

    # --- Sprints 1.2–1.4 ---

    @strawberry.field(permission_classes=[IsAdmin])
    async def participante(
        self, info: Info, id: strawberry.ID
    ) -> ParticipanteType | None:
        db: AsyncSession = info.context["db"]
        p = await participante_svc.get_participante(db, uuid.UUID(str(id)))
        return _participante_to_type(p) if p else None

    # --- Sprints 1.3–1.5 ---

    @strawberry.field(permission_classes=[IsAdmin])
    async def plano_entregas(
        self, info: Info, id: strawberry.ID
    ) -> PlanoEntregasType | None:
        db: AsyncSession = info.context["db"]
        pe = await pe_svc.get_plano_entregas(db, uuid.UUID(str(id)))
        return _pe_to_type(pe) if pe else None

    @strawberry.field(permission_classes=[IsAdmin])
    async def plano_trabalho(
        self, info: Info, id: strawberry.ID
    ) -> PlanoTrabalhoType | None:
        db: AsyncSession = info.context["db"]
        pt = await pt_svc.get_plano_trabalho(db, uuid.UUID(str(id)))
        return _pt_to_type(pt) if pt else None

    # --- Sprint 1.6 ---

    @strawberry.field(permission_classes=[IsAdmin])
    async def minhas_notificacoes(self, info: Info) -> list[NotificacaoType]:
        from sqlalchemy import select
        from ..models.notificacao import Notificacao
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        result = await db.execute(
            select(Notificacao)
            .where(Notificacao.destinatario_user_id == user.id)
            .order_by(Notificacao.created_at.desc())
            .limit(50)
        )
        return [_notificacao_to_type(n) for n in result.scalars()]


@strawberry.type
class Mutation:
    # --- Sprint 1.1 ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def criar_unidade_autorizadora(
        self, info: Info, input: CriarUnidadeAutorizadoraInput
    ) -> UnidadeAutorizadoraType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        ua = await svc.criar_unidade_autorizadora(
            db,
            cod_unidade_autorizadora=input.cod_unidade_autorizadora,
            origem_unidade=OrigemUnidade(input.origem_unidade.value),
            nome=input.nome,
            sigla=input.sigla,
            user=user,
            ip_address=_ip(info),
        )
        return _ua_to_type(ua)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def criar_ato_autorizacao(
        self,
        info: Info,
        unidade_autorizadora_id: strawberry.ID,
        input: CriarAtoAutorizacaoInput,
    ) -> AtoAutorizacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        ato = await svc.criar_ato_autorizacao(
            db,
            unidade_autorizadora_id=uuid.UUID(str(unidade_autorizadora_id)),
            autoridade=input.autoridade,
            data_publicacao=input.data_publicacao,
            referencia=input.referencia,
            user=user,
            ip_address=_ip(info),
        )
        return _ato_to_type(ato)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def atualizar_status_ato(
        self,
        info: Info,
        ato_id: strawberry.ID,
        status: StatusAtoGql,
    ) -> AtoAutorizacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        ato = await svc.atualizar_status_ato(
            db,
            ato_id=uuid.UUID(str(ato_id)),
            novo_status=StatusAto(status.value),
            user=user,
            ip_address=_ip(info),
        )
        return _ato_to_type(ato)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def criar_unidade_instituidora(
        self,
        info: Info,
        unidade_autorizadora_id: strawberry.ID,
        input: CriarUnidadeInstituidoraInput,
    ) -> UnidadeInstituidoraType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        ui = await svc.criar_unidade_instituidora(
            db,
            unidade_autorizadora_id=uuid.UUID(str(unidade_autorizadora_id)),
            cod_unidade_instituidora=input.cod_unidade_instituidora,
            nome=input.nome,
            sigla=input.sigla,
            ato_instituicao_ref=input.ato_instituicao_ref,
            data_instituicao=input.data_instituicao,
            tipos_atividades=input.tipos_atividades,
            modalidades_autorizadas=input.modalidades_autorizadas,
            conteudo_minimo_tcr=input.conteudo_minimo_tcr,
            prazo_antecedencia_convocacao_dias=input.prazo_antecedencia_convocacao_dias,
            vagas_percentual_presencial=input.vagas_percentual_presencial,
            vagas_percentual_tt_parcial=input.vagas_percentual_tt_parcial,
            vagas_percentual_tt_integral=input.vagas_percentual_tt_integral,
            vagas_percentual_tt_exterior=input.vagas_percentual_tt_exterior,
            nivel_produtividade_adicional_tt=input.nivel_produtividade_adicional_tt,
            vedacoes_participacao=input.vedacoes_participacao,
            criterios_selecao_adicionais=input.criterios_selecao_adicionais,
            procedimento_registro_comparecimento=input.procedimento_registro_comparecimento,
            user=user,
            ip_address=_ip(info),
        )
        return _ui_to_type(ui)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def suspender_pgd(
        self,
        info: Info,
        unidade_instituidora_id: strawberry.ID,
        motivo: str,
    ) -> UnidadeInstituidoraType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        ui = await svc.suspender_pgd(
            db,
            unidade_instituidora_id=uuid.UUID(str(unidade_instituidora_id)),
            motivo=motivo,
            user=user,
            ip_address=_ip(info),
        )
        return _ui_to_type(ui)

    # --- Sprint 1.2 — Participante ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def cadastrar_participante(
        self, info: Info, input: CadastrarParticipanteInput
    ) -> ParticipanteType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        p = await participante_svc.cadastrar_participante(
            db,
            origem_unidade=OrigemUnidade(input.origem_unidade.value),
            cod_unidade_autorizadora=input.cod_unidade_autorizadora,
            cod_unidade_lotacao=input.cod_unidade_lotacao,
            matricula_siape=input.matricula_siape,
            cod_unidade_instituidora=input.cod_unidade_instituidora,
            cpf=input.cpf,
            nome=input.nome,
            email=input.email,
            modalidade_execucao=input.modalidade_execucao,
            data_assinatura_tcr=input.data_assinatura_tcr,
            tipo_vinculo=TipoVinculo(input.tipo_vinculo.value),
            unidade_execucao_id=uuid.UUID(str(input.unidade_execucao_id)),
            cumpriu_estagio_probatorio=input.cumpriu_estagio_probatorio,
            data_fim_estagio_probatorio=input.data_fim_estagio_probatorio,
            data_ingresso_pgd=input.data_ingresso_pgd,
            user=user,
            ip_address=_ip(info),
        )
        return _participante_to_type(p)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def desligar_participante(
        self,
        info: Info,
        participante_id: strawberry.ID,
        motivo: MotivoDesligamentoGql,
    ) -> ParticipanteType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        p = await participante_svc.desligar_participante(
            db,
            participante_id=uuid.UUID(str(participante_id)),
            motivo=MotivoDesligamento(motivo.value),
            user=user,
            ip_address=_ip(info),
        )
        return _participante_to_type(p)

    # --- Sprint 1.2 — TCR ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def pactuar_tcr(
        self,
        info: Info,
        participante_id: strawberry.ID,
        input: PactuarTCRInput,
    ) -> TCRType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        tcr = await participante_svc.pactu_tcr(
            db,
            participante_id=uuid.UUID(str(participante_id)),
            chefia_user_id=input.chefia_user_id,
            modalidade_execucao=input.modalidade_execucao,
            regime_execucao=RegimeExecucao(input.regime_execucao.value),
            prazo_antecedencia_convocacao_dias=input.prazo_antecedencia_convocacao_dias,
            canais_comunicacao=input.canais_comunicacao,
            responsabilidades=input.responsabilidades,
            ciencia_instalacoes_ergonomia=input.ciencia_instalacoes_ergonomia,
            ciencia_nao_direito_adquirido=input.ciencia_nao_direito_adquirido,
            ciencia_custeio_estrutura=input.ciencia_custeio_estrutura,
            saldo_banco_horas=input.saldo_banco_horas,
            acoes_melhoria=input.acoes_melhoria,
            tcr_anterior_id=(
                uuid.UUID(str(input.tcr_anterior_id))
                if input.tcr_anterior_id
                else None
            ),
            user=user,
            ip_address=_ip(info),
        )
        return _tcr_to_type(tcr)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def assinar_tcr_chefia(
        self,
        info: Info,
        tcr_id: strawberry.ID,
    ) -> TCRType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        tcr = await participante_svc.assinar_tcr_chefia(
            db,
            tcr_id=uuid.UUID(str(tcr_id)),
            user=user,
            ip_address=_ip(info),
        )
        return _tcr_to_type(tcr)

    # --- Sprint 1.4 — Convocação ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def criar_convocacao(
        self,
        info: Info,
        participante_id: strawberry.ID,
        unidade_execucao_id: strawberry.ID,
        input: CriarConvocacaoInput,
    ) -> ConvocacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        c = await participante_svc.criar_convocacao(
            db,
            participante_id=uuid.UUID(str(participante_id)),
            unidade_execucao_id=uuid.UUID(str(unidade_execucao_id)),
            canal_comunicacao=input.canal_comunicacao,
            data_convocacao=input.data_convocacao,
            data_comparecimento_prevista=input.data_comparecimento_prevista,
            horario_comparecimento=input.horario_comparecimento,
            local_comparecimento=input.local_comparecimento,
            periodo_presencial_inicio=input.periodo_presencial_inicio,
            periodo_presencial_fim=input.periodo_presencial_fim,
            motivo=input.motivo,
            chefia_user_id=input.chefia_user_id,
            user=user,
            ip_address=_ip(info),
        )
        return _convocacao_to_type(c)

    # --- Sprint 1.3 — Plano de Entregas ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def criar_plano_entregas(
        self, info: Info, input: CriarPlanoEntregasInput
    ) -> PlanoEntregasType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pe = await pe_svc.criar_plano_entregas(
            db,
            id_plano_entregas=input.id_plano_entregas,
            origem_unidade=OrigemUnidade(input.origem_unidade.value),
            cod_unidade_autorizadora=input.cod_unidade_autorizadora,
            cod_unidade_instituidora=input.cod_unidade_instituidora,
            cod_unidade_executora=input.cod_unidade_executora,
            unidade_execucao_id=uuid.UUID(str(input.unidade_execucao_id)),
            data_inicio=input.data_inicio,
            data_termino=input.data_termino,
            user=user,
            ip_address=_ip(info),
        )
        return _pe_to_type(pe)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def criar_entrega(
        self,
        info: Info,
        plano_entregas_id: strawberry.ID,
        input: CriarEntregaInput,
    ) -> EntregaType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        e = await pe_svc.criar_entrega(
            db,
            id_entrega=input.id_entrega,
            plano_entregas_id=uuid.UUID(str(plano_entregas_id)),
            nome_entrega=input.nome_entrega,
            meta_entrega=input.meta_entrega,
            tipo_meta=TipoMeta(input.tipo_meta.value),
            data_entrega=input.data_entrega,
            nome_unidade_demandante=input.nome_unidade_demandante,
            nome_unidade_destinataria=input.nome_unidade_destinataria,
            user=user,
            ip_address=_ip(info),
        )
        return _entrega_to_type(e)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def iniciar_execucao_plano_entregas(
        self, info: Info, plano_id: strawberry.ID
    ) -> PlanoEntregasType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pe = await pe_svc.iniciar_execucao_pe(
            db, plano_id=uuid.UUID(str(plano_id)), user=user, ip_address=_ip(info)
        )
        return _pe_to_type(pe)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def concluir_plano_entregas(
        self, info: Info, plano_id: strawberry.ID
    ) -> PlanoEntregasType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pe = await pe_svc.concluir_pe(
            db, plano_id=uuid.UUID(str(plano_id)), user=user, ip_address=_ip(info)
        )
        return _pe_to_type(pe)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def avaliar_plano_entregas(
        self,
        info: Info,
        plano_id: strawberry.ID,
        avaliacao: int,
        data_avaliacao: date,
    ) -> PlanoEntregasType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pe = await pe_svc.avaliar_pe(
            db,
            plano_id=uuid.UUID(str(plano_id)),
            avaliacao=avaliacao,
            data_avaliacao=data_avaliacao,
            user=user,
            ip_address=_ip(info),
        )
        return _pe_to_type(pe)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def cancelar_plano_entregas(
        self, info: Info, plano_id: strawberry.ID
    ) -> PlanoEntregasType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pe = await pe_svc.cancelar_pe(
            db, plano_id=uuid.UUID(str(plano_id)), user=user, ip_address=_ip(info)
        )
        return _pe_to_type(pe)

    # --- Sprint 1.4 — Plano de Trabalho ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def criar_plano_trabalho(
        self,
        info: Info,
        participante_id: strawberry.ID,
        input: CriarPlanoTrabalhoInput,
    ) -> PlanoTrabalhoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pt = await pt_svc.criar_plano_trabalho(
            db,
            id_plano_trabalho=input.id_plano_trabalho,
            origem_unidade=OrigemUnidade(input.origem_unidade.value),
            cod_unidade_autorizadora=input.cod_unidade_autorizadora,
            cod_unidade_executora=input.cod_unidade_executora,
            cod_unidade_lotacao_participante=input.cod_unidade_lotacao_participante,
            participante_id=uuid.UUID(str(participante_id)),
            cpf_participante=input.cpf_participante,
            matricula_siape=input.matricula_siape,
            data_inicio=input.data_inicio,
            data_termino=input.data_termino,
            carga_horaria_disponivel=input.carga_horaria_disponivel,
            criterios_avaliacao=input.criterios_avaliacao,
            plano_entregas_id=(
                uuid.UUID(str(input.plano_entregas_id))
                if input.plano_entregas_id
                else None
            ),
            user=user,
            ip_address=_ip(info),
        )
        return _pt_to_type(pt)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def adicionar_contribuicao(
        self,
        info: Info,
        plano_trabalho_id: strawberry.ID,
        input: AdicionarContribuicaoInput,
    ) -> ContribuicaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        c = await pt_svc.adicionar_contribuicao(
            db,
            id_contribuicao=input.id_contribuicao,
            plano_trabalho_id=uuid.UUID(str(plano_trabalho_id)),
            tipo_contribuicao=input.tipo_contribuicao,
            percentual_contribuicao=input.percentual_contribuicao,
            descricao=input.descricao,
            id_plano_entregas=input.id_plano_entregas,
            id_entrega=input.id_entrega,
            user=user,
            ip_address=_ip(info),
        )
        return _contribuicao_to_type(c)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def iniciar_execucao_plano_trabalho(
        self, info: Info, plano_id: strawberry.ID
    ) -> PlanoTrabalhoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pt = await pt_svc.iniciar_execucao_pt(
            db, plano_id=uuid.UUID(str(plano_id)), user=user, ip_address=_ip(info)
        )
        return _pt_to_type(pt)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def cancelar_plano_trabalho(
        self, info: Info, plano_id: strawberry.ID
    ) -> PlanoTrabalhoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pt = await pt_svc.cancelar_pt(
            db, plano_id=uuid.UUID(str(plano_id)), user=user, ip_address=_ip(info)
        )
        return _pt_to_type(pt)

    # --- Sprint 1.5 — Registro de Execução ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def registrar_execucao(
        self,
        info: Info,
        plano_trabalho_id: strawberry.ID,
        input: RegistrarExecucaoInput,
    ) -> AvaliacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        are = await pt_svc.registrar_execucao(
            db,
            id_periodo_avaliativo=input.id_periodo_avaliativo,
            plano_trabalho_id=uuid.UUID(str(plano_trabalho_id)),
            data_inicio_periodo_avaliativo=input.data_inicio_periodo_avaliativo,
            data_fim_periodo_avaliativo=input.data_fim_periodo_avaliativo,
            descricao_execucao=input.descricao_execucao,
            ocorrencias=input.ocorrencias,
            user=user,
            ip_address=_ip(info),
        )
        return _avaliacao_to_type(are)

    # --- Sprint 1.5 — Avaliação e Recurso ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def avaliar_registros_execucao(
        self,
        info: Info,
        avaliacao_id: strawberry.ID,
        nota: int,
        data_avaliacao: date,
        justificativa: Optional[str] = None,
    ) -> AvaliacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        are = await av_svc.avaliar_registros_execucao(
            db,
            avaliacao_id=uuid.UUID(str(avaliacao_id)),
            nota=nota,
            data_avaliacao=data_avaliacao,
            justificativa=justificativa,
            user=user,
            ip_address=_ip(info),
        )
        return _avaliacao_to_type(are)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def abrir_recurso(
        self,
        info: Info,
        avaliacao_id: strawberry.ID,
        texto: str,
    ) -> AvaliacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        are = await av_svc.abrir_recurso(
            db,
            avaliacao_id=uuid.UUID(str(avaliacao_id)),
            texto=texto,
            user=user,
            ip_address=_ip(info),
        )
        return _avaliacao_to_type(are)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def decidir_recurso(
        self,
        info: Info,
        avaliacao_id: strawberry.ID,
        decisao: DecisaoRecursoGql,
        justificativa: Optional[str] = None,
        nova_nota: Optional[int] = None,
    ) -> AvaliacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        are = await av_svc.decidir_recurso(
            db,
            avaliacao_id=uuid.UUID(str(avaliacao_id)),
            decisao=DecisaoRecurso(decisao.value),
            justificativa=justificativa,
            nova_nota=nova_nota,
            user=user,
            ip_address=_ip(info),
        )
        return _avaliacao_to_type(are)


async def get_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    return {"request": request, "db": db, "user": user}


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(schema, context_getter=get_context)
