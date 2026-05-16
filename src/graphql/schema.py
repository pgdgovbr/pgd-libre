import uuid
from datetime import date

import strawberry
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from ..auth.deps import get_optional_user
from ..database import get_db
from ..models.institucional import Competencia, OrigemUnidade, StatusAto
from ..models.participante import (
    MotivoDesligamento,
    RegimeExecucao,
    TipoAfastamento,
    TipoVinculo,
)
from ..models.plano import DecisaoRecurso, TipoMeta
from ..models.user import User
from ..services import avaliacao as av_svc
from ..services import institucional as svc
from ..services import participante as participante_svc
from ..services import plano_entregas as pe_svc
from ..services import plano_trabalho as pt_svc
from .institucional import (
    AtoAutorizacaoType,
    CriarAtoAutorizacaoInput,
    CriarUnidadeAutorizadoraInput,
    CriarUnidadeInstituidoraInput,
    DelegacaoCompetenciaType,
    DelegarCompetenciaInput,
    ResultadoPublicoType,
    StatusAtoGql,
    UnidadeAutorizadoraType,
    UnidadeInstituidoraType,
    _ato_to_type,
    _delegacao_to_type,
    _ua_to_type,
    _ui_to_type,
)
from .notificacao import NotificacaoType, _notificacao_to_type
from .participante import (
    AfastamentoType,
    AutorizacaoAdicionalNoturnoType,
    AutorizarAdicionalNoturnoInput,
    CadastrarParticipanteInput,
    ConfirmarSelecaoInput,
    ConvocacaoType,
    CriarConvocacaoInput,
    MotivoDesligamentoGql,
    PactuarTCRInput,
    ParticipanteType,
    ProcessoSelecaoType,
    RegistrarAfastamentoInput,
    RegistrarAutorizacaoEquipamentosInput,
    TCRType,
    TermoGuardaEquipamentoType,
    _afastamento_to_type,
    _autorizacao_noturna_to_type,
    _convocacao_to_type,
    _participante_to_type,
    _processo_selecao_to_type,
    _tcr_to_type,
    _termo_guarda_to_type,
)
from .permissions import IsAdmin, IsAuthenticated, IsChefiaOrAbove, IsGestorOrAdmin
from .plano import (
    AdicionarContribuicaoInput,
    AprovarPlanoEntregasInput,
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


@strawberry.type
class ConformidadeEntidadeType:
    tipo: str
    total: int
    enviados: int
    pendentes: int
    com_erro: int


@strawberry.type
class PainelConformidadeType:
    participantes: ConformidadeEntidadeType
    planos_entregas: ConformidadeEntidadeType
    planos_trabalho: ConformidadeEntidadeType


def _ua_cod(info: Info) -> int | None:
    """Returns the user's cod_unidade_autorizadora, or None if ADMIN (sees all)."""
    from ..models.user import UserRole

    user: User | None = info.context.get("user")
    if user is None or user.role == UserRole.ADMIN:
        return None
    return user.cod_unidade_autorizadora


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
        return UserType(id=user.id, email=user.email, name=user.name, role=user.role.value)

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

    @strawberry.field(permission_classes=[IsChefiaOrAbove])
    async def participante(self, info: Info, id: strawberry.ID) -> ParticipanteType | None:
        from sqlalchemy import select

        from ..models.participante import Participante

        db: AsyncSession = info.context["db"]
        ua_cod = _ua_cod(info)
        stmt = select(Participante).where(Participante.id == uuid.UUID(str(id)))
        if ua_cod is not None:
            stmt = stmt.where(Participante.cod_unidade_autorizadora == ua_cod)
        result = await db.execute(stmt)
        p = result.scalar_one_or_none()
        return _participante_to_type(p) if p else None

    @strawberry.field(permission_classes=[IsChefiaOrAbove])
    async def listar_participantes(self, info: Info) -> list[ParticipanteType]:
        from sqlalchemy import select

        from ..models.participante import Participante

        db: AsyncSession = info.context["db"]
        ua_cod = _ua_cod(info)
        stmt = select(Participante)
        if ua_cod is not None:
            stmt = stmt.where(Participante.cod_unidade_autorizadora == ua_cod)
        result = await db.execute(stmt)
        return [_participante_to_type(p) for p in result.scalars()]

    # --- Sprints 1.3–1.5 ---

    @strawberry.field(permission_classes=[IsChefiaOrAbove])
    async def plano_entregas(self, info: Info, id: strawberry.ID) -> PlanoEntregasType | None:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..models.plano import PlanoEntregas

        db: AsyncSession = info.context["db"]
        ua_cod = _ua_cod(info)
        stmt = (
            select(PlanoEntregas)
            .options(selectinload(PlanoEntregas.entregas))
            .where(PlanoEntregas.id == uuid.UUID(str(id)))
        )
        if ua_cod is not None:
            stmt = stmt.where(PlanoEntregas.cod_unidade_autorizadora == ua_cod)
        result = await db.execute(stmt)
        pe = result.scalar_one_or_none()
        return _pe_to_type(pe) if pe else None

    @strawberry.field(permission_classes=[IsChefiaOrAbove])
    async def listar_planos_entregas(self, info: Info) -> list[PlanoEntregasType]:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..models.plano import PlanoEntregas

        db: AsyncSession = info.context["db"]
        ua_cod = _ua_cod(info)
        stmt = select(PlanoEntregas).options(selectinload(PlanoEntregas.entregas))
        if ua_cod is not None:
            stmt = stmt.where(PlanoEntregas.cod_unidade_autorizadora == ua_cod)
        result = await db.execute(stmt)
        return [_pe_to_type(pe) for pe in result.scalars()]

    @strawberry.field(permission_classes=[IsChefiaOrAbove])
    async def plano_trabalho(self, info: Info, id: strawberry.ID) -> PlanoTrabalhoType | None:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..models.plano import PlanoTrabalho

        db: AsyncSession = info.context["db"]
        ua_cod = _ua_cod(info)
        stmt = (
            select(PlanoTrabalho)
            .options(
                selectinload(PlanoTrabalho.contribuicoes),
                selectinload(PlanoTrabalho.avaliacoes),
            )
            .where(PlanoTrabalho.id == uuid.UUID(str(id)))
        )
        if ua_cod is not None:
            stmt = stmt.where(PlanoTrabalho.cod_unidade_autorizadora == ua_cod)
        result = await db.execute(stmt)
        pt = result.scalar_one_or_none()
        return _pt_to_type(pt) if pt else None

    @strawberry.field(permission_classes=[IsChefiaOrAbove])
    async def listar_planos_trabalho(self, info: Info) -> list[PlanoTrabalhoType]:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..models.plano import PlanoTrabalho

        db: AsyncSession = info.context["db"]
        ua_cod = _ua_cod(info)
        stmt = select(PlanoTrabalho).options(
            selectinload(PlanoTrabalho.contribuicoes),
            selectinload(PlanoTrabalho.avaliacoes),
        )
        if ua_cod is not None:
            stmt = stmt.where(PlanoTrabalho.cod_unidade_autorizadora == ua_cod)
        result = await db.execute(stmt)
        return [_pt_to_type(pt) for pt in result.scalars()]

    @strawberry.field
    async def meus_planos_trabalho(self, info: Info) -> list[PlanoTrabalhoType]:
        """Planos de trabalho do servidor autenticado (acesso a partir do próprio user)."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..models.participante import Participante
        from ..models.plano import PlanoTrabalho

        db: AsyncSession = info.context["db"]
        user: User | None = info.context.get("user")
        if user is None:
            return []
        # Resolver participante pelo email do user
        part_res = await db.execute(select(Participante).where(Participante.email == user.email))
        participante = part_res.scalar_one_or_none()
        if participante is None:
            return []
        stmt = (
            select(PlanoTrabalho)
            .options(
                selectinload(PlanoTrabalho.contribuicoes),
                selectinload(PlanoTrabalho.avaliacoes),
            )
            .where(PlanoTrabalho.participante_id == participante.id)
        )
        result = await db.execute(stmt)
        return [_pt_to_type(pt) for pt in result.scalars()]

    @strawberry.field
    async def registro_execucao(self, info: Info, id: strawberry.ID) -> AvaliacaoType | None:
        """Retorna ARE pelo id. Servidor vê o próprio; chefia vê todos da UA."""
        from sqlalchemy import select

        from ..models.plano import AvaliacaoRegistrosExecucao, PlanoTrabalho

        db: AsyncSession = info.context["db"]
        user: User | None = info.context.get("user")
        if user is None:
            return None
        stmt = (
            select(AvaliacaoRegistrosExecucao)
            .join(PlanoTrabalho, AvaliacaoRegistrosExecucao.plano_trabalho_id == PlanoTrabalho.id)
            .where(AvaliacaoRegistrosExecucao.id == uuid.UUID(str(id)))
        )
        if user.cod_unidade_autorizadora is not None:
            stmt = stmt.where(
                PlanoTrabalho.cod_unidade_autorizadora == user.cod_unidade_autorizadora
            )
        result = await db.execute(stmt)
        are = result.scalar_one_or_none()
        return _avaliacao_to_type(are) if are else None

    @strawberry.field(permission_classes=[IsChefiaOrAbove])
    async def listar_convocacoes(
        self, info: Info, participante_id: strawberry.ID
    ) -> list[ConvocacaoType]:
        from sqlalchemy import select

        from ..models.participante import Convocacao

        db: AsyncSession = info.context["db"]
        result = await db.execute(
            select(Convocacao)
            .where(Convocacao.participante_id == uuid.UUID(str(participante_id)))
            .order_by(Convocacao.data_convocacao.desc())
        )
        return [_convocacao_to_type(c) for c in result.scalars()]

    # --- Sprint 1.6 ---

    @strawberry.field(permission_classes=[IsAuthenticated])
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

    # --- Sprint 2.2 ---

    @strawberry.field(permission_classes=[IsAdmin])
    async def painel_conformidade(self, info: Info) -> PainelConformidadeType:
        from sqlalchemy import func, select

        from ..models.participante import Participante
        from ..models.plano import PlanoEntregas, PlanoTrabalho
        from ..models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

        db: AsyncSession = info.context["db"]

        async def _stats(model: type, tipo: TipoEntidadeSync) -> ConformidadeEntidadeType:
            total_r = await db.execute(select(func.count()).select_from(model))
            total = total_r.scalar_one()

            env_r = await db.execute(
                select(func.count()).select_from(model).where(model.api_sincronizado_em.isnot(None))
            )
            enviados = env_r.scalar_one()

            # entidades com pelo menos um registro de falha e ainda não enviadas
            com_erro_r = await db.execute(
                select(func.count(RegistroEnvioAPI.entidade_id.distinct())).where(
                    RegistroEnvioAPI.tipo_entidade == tipo,
                    RegistroEnvioAPI.sucesso == False,  # noqa: E712
                )
            )
            com_erro = com_erro_r.scalar_one()

            return ConformidadeEntidadeType(
                tipo=tipo.value,
                total=total,
                enviados=enviados,
                pendentes=total - enviados,
                com_erro=com_erro,
            )

        return PainelConformidadeType(
            participantes=await _stats(Participante, TipoEntidadeSync.PARTICIPANTE),
            planos_entregas=await _stats(PlanoEntregas, TipoEntidadeSync.PLANO_ENTREGAS),
            planos_trabalho=await _stats(PlanoTrabalho, TipoEntidadeSync.PLANO_TRABALHO),
        )

    # --- Sprint 2.4 — Relatórios de conformidade ---

    @strawberry.field(permission_classes=[IsGestorOrAdmin])
    async def relatorio_sem_plano_trabalho(
        self,
        info: Info,
        cod_unidade_autorizadora: int | None = None,
    ) -> list[ParticipanteType]:
        from ..services import relatorios as rel_svc

        db: AsyncSession = info.context["db"]
        ua_cod = cod_unidade_autorizadora if cod_unidade_autorizadora is not None else _ua_cod(info)
        participantes = await rel_svc.relatorio_sem_plano_trabalho(db, ua_cod)
        return [_participante_to_type(p) for p in participantes]

    @strawberry.field(permission_classes=[IsGestorOrAdmin])
    async def relatorio_registros_atraso(
        self,
        info: Info,
        referencia: date,
        cod_unidade_autorizadora: int | None = None,
    ) -> list[AvaliacaoType]:
        from ..services import relatorios as rel_svc

        db: AsyncSession = info.context["db"]
        ua_cod = cod_unidade_autorizadora if cod_unidade_autorizadora is not None else _ua_cod(info)
        avaliacoes = await rel_svc.relatorio_registros_atraso(db, referencia, ua_cod)
        return [_avaliacao_to_type(a) for a in avaliacoes]

    @strawberry.field(permission_classes=[IsGestorOrAdmin])
    async def relatorio_avaliacoes_pendentes(
        self,
        info: Info,
        referencia: date,
        cod_unidade_autorizadora: int | None = None,
    ) -> list[AvaliacaoType]:
        from ..services import relatorios as rel_svc

        db: AsyncSession = info.context["db"]
        ua_cod = cod_unidade_autorizadora if cod_unidade_autorizadora is not None else _ua_cod(info)
        avaliacoes = await rel_svc.relatorio_avaliacoes_pendentes(db, referencia, ua_cod)
        return [_avaliacao_to_type(a) for a in avaliacoes]

    @strawberry.field(permission_classes=[IsGestorOrAdmin])
    async def relatorio_pe_avaliacao_pendente(
        self,
        info: Info,
        referencia: date,
        cod_unidade_autorizadora: int | None = None,
    ) -> list[PlanoEntregasType]:
        from ..services import relatorios as rel_svc

        db: AsyncSession = info.context["db"]
        ua_cod = cod_unidade_autorizadora if cod_unidade_autorizadora is not None else _ua_cod(info)
        planos = await rel_svc.relatorio_pe_avaliacao_pendente(db, referencia, ua_cod)
        return [_pe_to_type(pe) for pe in planos]

    # --- Sprint 2.6 — Afastamentos (TC-M10-008) ---

    @strawberry.field(permission_classes=[IsGestorOrAdmin])
    async def relatorio_afastamentos(
        self,
        info: Info,
        cod_unidade_autorizadora: int,
        ano: int,
        mes: int,
    ) -> list[AfastamentoType]:
        from ..services import relatorios as rel_svc

        db: AsyncSession = info.context["db"]
        afastamentos = await rel_svc.relatorio_afastamentos(
            db,
            cod_unidade_autorizadora=cod_unidade_autorizadora,
            ano=ano,
            mes=mes,
        )
        return [_afastamento_to_type(a) for a in afastamentos]


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
                uuid.UUID(str(input.tcr_anterior_id)) if input.tcr_anterior_id else None
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

    @strawberry.mutation(permission_classes=[IsChefiaOrAbove])
    async def registrar_comparecimento(
        self,
        info: Info,
        convocacao_id: strawberry.ID,
        data_efetiva: date,
    ) -> ConvocacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        c = await participante_svc.registrar_comparecimento(
            db,
            convocacao_id=uuid.UUID(str(convocacao_id)),
            data_efetiva=data_efetiva,
            user=user,
            ip_address=_ip(info),
        )
        return _convocacao_to_type(c)

    @strawberry.mutation(permission_classes=[IsChefiaOrAbove])
    async def cancelar_convocacao(
        self,
        info: Info,
        convocacao_id: strawberry.ID,
    ) -> ConvocacaoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        c = await participante_svc.cancelar_convocacao(
            db,
            convocacao_id=uuid.UUID(str(convocacao_id)),
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
                uuid.UUID(str(input.plano_entregas_id)) if input.plano_entregas_id else None
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
            rotulo=input.rotulo,
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
        justificativa: str | None = None,
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
        justificativa: str | None = None,
        nova_nota: int | None = None,
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

    # --- Sprint 2.2 ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def reprocessar_envio(
        self,
        info: Info,
        tipo_entidade: str,
        entidade_id: strawberry.ID,
    ) -> bool:
        """Remove registros de falha para a entidade, permitindo retry imediato."""
        import uuid as _uuid

        from sqlalchemy import delete

        from ..models.sync_log import RegistroEnvioAPI, TipoEntidadeSync

        db: AsyncSession = info.context["db"]
        await db.execute(
            delete(RegistroEnvioAPI).where(
                RegistroEnvioAPI.tipo_entidade == TipoEntidadeSync(tipo_entidade),
                RegistroEnvioAPI.entidade_id == _uuid.UUID(str(entidade_id)),
                RegistroEnvioAPI.sucesso == False,  # noqa: E712
            )
        )
        await db.commit()
        return True

    # --- Sprint 2.4 — Seleção, aprovação de PE, equipamentos ---

    @strawberry.mutation(permission_classes=[IsChefiaOrAbove])
    async def confirmar_selecao(
        self, info: Info, input: ConfirmarSelecaoInput
    ) -> ProcessoSelecaoType:
        from ..models.participante import CriteriosPrioridade
        from ..services.participante import CandidatoSelecao

        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        candidatos = [
            CandidatoSelecao(
                id=c.id,
                nome=c.nome,
                criterio=CriteriosPrioridade(c.criterio.value),
            )
            for c in input.candidatos
        ]
        ps = await participante_svc.confirmar_selecao(
            db,
            unidade_execucao_id=uuid.UUID(str(input.unidade_execucao_id)),
            candidatos=candidatos,
            n_vagas=input.n_vagas,
            criterios_tecnicos=input.criterios_tecnicos,
            user=user,
            ip_address=_ip(info),
        )
        return _processo_selecao_to_type(ps)

    @strawberry.mutation(permission_classes=[IsChefiaOrAbove])
    async def aprovar_plano_entregas(
        self, info: Info, input: AprovarPlanoEntregasInput
    ) -> PlanoEntregasType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        pe = await pe_svc.aprovar_plano_entregas(
            db,
            plano_id=uuid.UUID(str(input.plano_id)),
            aprovador_user_id=input.aprovador_user_id,
            user=user,
            ip_address=_ip(info),
        )
        return _pe_to_type(pe)

    @strawberry.mutation(permission_classes=[IsChefiaOrAbove])
    async def registrar_autorizacao_equipamentos(
        self, info: Info, input: RegistrarAutorizacaoEquipamentosInput
    ) -> TermoGuardaEquipamentoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        termo = await participante_svc.registrar_autorizacao_equipamentos(
            db,
            participante_id=uuid.UUID(str(input.participante_id)),
            tcr_id=uuid.UUID(str(input.tcr_id)),
            descricao_equipamentos=input.descricao_equipamentos,
            data_autorizacao=input.data_autorizacao,
            modalidade_execucao=input.modalidade_execucao,
            user=user,
            ip_address=_ip(info),
        )
        return _termo_guarda_to_type(termo)

    # --- Sprint 2.6 — Afastamentos (TC-M10-008) ---

    @strawberry.mutation(permission_classes=[IsChefiaOrAbove])
    async def registrar_afastamento(
        self, info: Info, input: RegistrarAfastamentoInput
    ) -> AfastamentoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        afa = await participante_svc.registrar_afastamento(
            db,
            participante_id=uuid.UUID(str(input.participante_id)),
            tipo_afastamento=TipoAfastamento(input.tipo_afastamento.value),
            data_inicio=input.data_inicio,
            data_fim=input.data_fim,
            observacao=input.observacao,
            user=user,
            ip_address=_ip(info),
        )
        return _afastamento_to_type(afa)

    # --- Sprint 2.7 — Adicional Noturno (TC-M10-005/006) ---

    @strawberry.mutation(permission_classes=[IsChefiaOrAbove])
    async def autorizar_adicional_noturno(
        self, info: Info, input: AutorizarAdicionalNoturnoInput
    ) -> AutorizacaoAdicionalNoturnoType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        auth = await participante_svc.autorizar_adicional_noturno(
            db,
            participante_id=uuid.UUID(str(input.participante_id)),
            data_inicio_autorizacao=input.data_inicio_autorizacao,
            data_fim_autorizacao=input.data_fim_autorizacao,
            horario_inicio_noturno=input.horario_inicio_noturno,
            horario_fim_noturno=input.horario_fim_noturno,
            justificativa=input.justificativa,
            user=user,
            ip_address=_ip(info),
        )
        return _autorizacao_noturna_to_type(auth)

    # --- Sprint 2.8 — Delegação de competência (RF-037) ---

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def delegar_competencia(
        self, info: Info, input: DelegarCompetenciaInput
    ) -> DelegacaoCompetenciaType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        d = await svc.delegar_competencia(
            db,
            delegante_user_id=user.id,
            delegatario_user_id=input.delegatario_user_id,
            competencia=Competencia(input.competencia.value),
            unidade_execucao_id=(
                uuid.UUID(str(input.unidade_execucao_id)) if input.unidade_execucao_id else None
            ),
            data_inicio=input.data_inicio,
            data_fim=input.data_fim,
            motivo=input.motivo,
            user=user,
            ip_address=_ip(info),
        )
        return _delegacao_to_type(d)

    @strawberry.mutation(permission_classes=[IsAdmin])
    async def revogar_delegacao(
        self, info: Info, delegacao_id: strawberry.ID
    ) -> DelegacaoCompetenciaType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        d = await svc.revogar_delegacao(
            db,
            delegacao_id=uuid.UUID(str(delegacao_id)),
            user=user,
            ip_address=_ip(info),
        )
        return _delegacao_to_type(d)


async def get_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    return {"request": request, "db": db, "user": user}


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(schema, context_getter=get_context)
