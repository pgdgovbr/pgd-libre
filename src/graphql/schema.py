import uuid

import strawberry
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter
from strawberry.permission import BasePermission
from strawberry.types import Info

from ..auth.deps import get_optional_user
from ..database import get_db
from ..models.institucional import StatusAto, StatusPgd
from ..models.user import User
from ..services import institucional as svc
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
from .permissions import IsAdmin


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


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAdmin])
    async def criar_unidade_autorizadora(
        self, info: Info, input: CriarUnidadeAutorizadoraInput
    ) -> UnidadeAutorizadoraType:
        db: AsyncSession = info.context["db"]
        user: User = info.context["user"]
        from ..models.institucional import OrigemUnidade

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


async def get_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> dict:
    return {"request": request, "db": db, "user": user}


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(schema, context_getter=get_context)
