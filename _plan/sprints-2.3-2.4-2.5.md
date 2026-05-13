# Plano: Sprints 2.3 → 2.5 — Fechamento de TCs, GraphQL e Jornadas de Usuário

## Status de implementação (atualizado 2026-05-13)

### Sprint 2.3 — em andamento

| Item | Código | Teste | Status |
|------|--------|-------|--------|
| TC-M07-009: PE com avaliação pendente | `src/services/relatorios.py` ✅ | `tests/test_relatorios.py` +2 casos ✅ | ✅ Implementado |
| TC-M10-002: rotulo no payload da API | `src/integration/mapper.py` ✅ | `tests/test_gestao_rh.py` +2 unit tests ✅ | ✅ Implementado |
| TC-M10-007: relatório de frequência | `src/services/relatorios.py` ✅ | `tests/test_gestao_rh.py` +1 integration test ⚠️ | ⚠️ Teste escrito, não verificado — PE sobreposição fix aplicado mas testes não re-rodados |

**Próximo passo imediato:** rodar `pytest tests/test_relatorios.py tests/test_gestao_rh.py -v` para confirmar Sprint 2.3 verde, depois iniciar Sprint 2.4.

### Sprint 2.4 — não iniciado

### Sprint 2.5 — não iniciado

---

## Context

Com os 10 RFs implementados (v0.4), 157/189 TCs estão verdes. Restam três frentes:
1. Pequenos TCs abertos sem novos modelos (TC-M07-009, TC-M10-002, TC-M10-007)
2. Camada GraphQL dos serviços novos (sem ela, nenhum cliente consume os 10 RFs)
3. Jornadas de usuário E2E (JU-01 a JU-07) que cruzam múltiplos módulos via GraphQL

---

## Sprint 2.3 — Fechamento de TCs abertos

> Objetivo: 160+/189 TCs verdes; zero novos modelos; testes e serviço puro.

### 2.3-A — TC-M07-009: Planos de entregas com avaliação pendente

**O que adicionar em `src/services/relatorios.py`:**

```python
async def relatorio_pe_avaliacao_pendente(
    db: AsyncSession,
    referencia: date,
    cod_unidade_autorizadora: int | None = None,
) -> list[PlanoEntregas]:
    # STATUS_PE_CONCLUIDO == 4 e avaliacao IS NULL
    # deadline: data_termino + 30 < referencia
```

Query: `PlanoEntregas` onde `status == 4 AND avaliacao IS NULL AND data_termino + 30 < referencia`.
Filtro opcional por `cod_unidade_autorizadora`.

**Teste em `tests/test_relatorios.py`** — padrão idêntico aos TC-M07-005/006/007/008:
- Criar PE com `status = STATUS_PE_CONCLUIDO`, `avaliacao = None`, `data_termino` no passado
- Chamar `relatorio_pe_avaliacao_pendente(db, referencia=date(2026,3,1), ...)`
- Verificar que `pe.id in ids`
- Variante: PE já avaliado (`avaliacao = 3`) não aparece

**Arquivo crítico:** `src/services/relatorios.py`  
**Funções a reusar:** padrão de `relatorio_avaliacoes_pendentes` (join + where)  
**Imports necessários:** `PlanoEntregas`, `STATUS_PE_CONCLUIDO` de `src/models/plano.py`

---

### 2.3-B — TC-M10-002: Rótulo de ação de desenvolvimento no payload da API

**O que alterar em `src/integration/mapper.py`:**

Função `_contribuicao(c: Contribuicao) -> dict` — atualmente mapeia 5 campos. Adicionar:
```python
"rotulo": c.rotulo,   # nullable str; None → omitido ou enviado como null
```

**Teste em `tests/test_gestao_rh.py`** (novo caso no final do arquivo):
- Criar PT com contribuição tipo 2 + `rotulo="acao_desenvolvimento"`
- Importar `mapear_plano_trabalho` (ou equivalente) do mapper
- Verificar que a contribuição no payload contém `"rotulo": "acao_desenvolvimento"`

**Arquivo crítico:** `src/integration/mapper.py`  
**Função a alterar:** `_contribuicao()`  
**Atenção:** verificar se a API PGD Central aceita o campo `rotulo` — se não aceitar, omitir quando `None` e incluir apenas quando presente.

---

### 2.3-C — TC-M10-007: Relatório de frequência/códigos PGD

**O que adicionar em `src/services/relatorios.py`:**

```python
async def relatorio_frequencia(
    db: AsyncSession,
    cod_unidade_autorizadora: int,
    ano: int,
    mes: int,
) -> list[Participante]:
    # Retorna participantes ativos (situacao == 1) da unidade
    # cujo plano de trabalho (status 3 ou 4) cobre o período ano/mes
```

O "código PGD" a lançar no SIAPE Frequência é derivado da `modalidade_execucao` do participante — não requer novo campo de modelo.

**Teste em `tests/test_gestao_rh.py`** (ou novo `tests/test_frequencia.py`):
- Criar 3 participantes ativos na unidade com PT em execução em fevereiro/2026
- Criar 1 participante sem PT ativo no período → não deve aparecer
- Chamar `relatorio_frequencia(db, cod_unidade_autorizadora=X, ano=2026, mes=2)`
- Verificar que os 3 aparecem e o 4º não

**Nota:** TC-M10-008 (afastamentos destacados) exige novo modelo `Afastamento` — **deferido para Sprint 2.6**.

**Arquivo crítico:** `src/services/relatorios.py`  
**Imports:** `PlanoTrabalho`, `STATUS_PT_EM_EXECUCAO`, `STATUS_PT_CONCLUIDO`

---

## Sprint 2.4 — Camada GraphQL dos novos serviços

> Objetivo: todos os 10 RFs implementados consumíveis via API GraphQL; testes GQL adicionados.

**Arquivo central:** `src/graphql/schema.py` (monolítico, 25 mutations + 13 queries já lá)

### 2.4-A — Novos tipos GraphQL

Adicionar em `src/graphql/participante.py`:

```python
@strawberry.type
class ProcessoSelecaoType:
    id: strawberry.ID
    unidade_execucao_id: strawberry.ID
    criterios_tecnicos: str
    n_vagas: int
    resultado: strawberry.scalars.JSON
    created_at: datetime

@strawberry.type
class TermoGuardaEquipamentoType:
    id: strawberry.ID
    participante_id: strawberry.ID
    tcr_id: strawberry.ID
    descricao_equipamentos: str
    data_autorizacao: date
```

Adicionar helper converters `_processo_selecao_to_type()` e `_termo_guarda_to_type()`.

Adicionar em `src/graphql/plano.py`:
- `ContribuicaoType`: adicionar campo `rotulo: Optional[str] = None`
- `PlanoEntregasType`: adicionar `aprovado_por_user_id: Optional[int]`, `data_aprovacao: Optional[date]`

---

### 2.4-B — Novos inputs GraphQL

Adicionar em `src/graphql/participante.py`:

```python
@strawberry.input
class CandidatoSelecaoInput:
    id: str
    nome: str
    criterio: CriteriosPrioridadeGql  # novo enum

@strawberry.input
class ConfirmarSelecaoInput:
    unidade_execucao_id: strawberry.ID
    candidatos: list[CandidatoSelecaoInput]
    n_vagas: int
    criterios_tecnicos: str

@strawberry.input
class RegistrarAutorizacaoEquipamentosInput:
    participante_id: strawberry.ID
    tcr_id: strawberry.ID
    descricao_equipamentos: str
    data_autorizacao: date
    modalidade_execucao: int
```

Adicionar em `src/graphql/plano.py`:
```python
@strawberry.input
class AprovarPlanoEntregasInput:
    plano_id: strawberry.ID
    aprovador_user_id: int
```

---

### 2.4-C — Novas mutations em `src/graphql/schema.py`

Seguindo o padrão exato dos 25 existentes:

```python
@strawberry.mutation(permission_classes=[IsChefiaOrAbove])
async def confirmar_selecao(self, info: Info, input: ConfirmarSelecaoInput) -> ProcessoSelecaoType:
    # Converte candidatos: list[CandidatoSelecao dataclass]
    # Chama participante_svc.confirmar_selecao()

@strawberry.mutation(permission_classes=[IsGestorOrAdmin])
async def aprovar_plano_entregas(self, info: Info, input: AprovarPlanoEntregasInput) -> PlanoEntregasType:
    # Chama pe_svc.aprovar_plano_entregas()

@strawberry.mutation(permission_classes=[IsChefiaOrAbove])
async def registrar_autorizacao_equipamentos(
    self, info: Info, input: RegistrarAutorizacaoEquipamentosInput
) -> TermoGuardaEquipamentoType:
    # Chama participante_svc.registrar_autorizacao_equipamentos()
```

---

### 2.4-D — Novas queries de relatório em `src/graphql/schema.py`

```python
@strawberry.field(permission_classes=[IsGestorOrAdmin])
async def relatorio_sem_plano_trabalho(
    self, info: Info, cod_unidade_autorizadora: Optional[int] = None
) -> list[ParticipanteType]: ...

@strawberry.field(permission_classes=[IsGestorOrAdmin])
async def relatorio_registros_atraso(
    self, info: Info, referencia: date, cod_unidade_autorizadora: Optional[int] = None
) -> list[AvaliacaoType]: ...

@strawberry.field(permission_classes=[IsGestorOrAdmin])
async def relatorio_avaliacoes_pendentes(
    self, info: Info, referencia: date, cod_unidade_autorizadora: Optional[int] = None
) -> list[AvaliacaoType]: ...

@strawberry.field(permission_classes=[IsGestorOrAdmin])
async def relatorio_pe_avaliacao_pendente(
    self, info: Info, referencia: date, cod_unidade_autorizadora: Optional[int] = None
) -> list[PlanoEntregasType]: ...
```

---

### 2.4-E — Testes GQL

Adicionar em `tests/test_graphql.py` (ou novo `tests/test_gql_novos.py`):

- `test_gql_confirmar_selecao` — mutation com `criterios_tecnicos` + verificar `ProcessoSelecao` criado
- `test_gql_aprovar_plano_entregas` — mutation; verificar `aprovado_por_user_id` e `data_aprovacao`
- `test_gql_aprovar_instituidora_rejeitado` — deve retornar erro GQL
- `test_gql_registrar_autorizacao_equipamentos` — mutation; verificar `TermoGuardaEquipamento`
- `test_gql_relatorio_sem_plano_trabalho` — query; verificar participante aparece
- `test_gql_rotulo_contribuicao_em_query` — query `planoTrabalho { contribuicoes { rotulo } }`

**Padrão:** `client.post("/graphql", json={"query": "mutation {...}"})` + `set_auth_cookie(client, user)`

---

## Sprint 2.5 — Jornadas de Usuário E2E (JU-01 a JU-07)

> Objetivo: 7 jornadas end-to-end via GraphQL, banco real, verificação de estado + audit log.
> Pré-requisito: Sprint 2.4 concluída (mutations novas disponíveis).

**Novo arquivo:** `tests/test_jornadas.py`

**Fixture de estado compartilhado** (helper `_estado_ju01(db)`) que retorna `{ua, ui, ue, admin, chefia, nivel_sup}` — reutilizada por JU-02 em diante.

### JU-01 — Configuração inicial do PGD
Sequência de mutations GQL: `criarUnidadeAutorizadora` → `criarAtoAutorizacao` → `criarUnidadeInstituidora` → assert `pgd_autorizado = true`, `status = em_vigor`, 4+ `AuditLog`.

### JU-02 — Onboarding de participante até TCR ativo
Depende de JU-01. Mutations: `cadastrarParticipante` → `pactuarTcr` → `assinarTcrChefia` → assert `TCR.status = ativo`.

### JU-03 — Ciclo completo plano → avaliação
Depende de JU-02 + mutation `aprovarPlanoEntregas` (Sprint 2.4). 15 passos sequenciais; verificar `PlanoEntregas.status = 5`, 3 avaliações, 3 notificações.

### JU-04 — Ciclo negativo: nota 5, recurso, compensação
Depende de JU-03. Verificar: recurso persistido com `acatado = false`, novo TCR com `carga_horaria_compensacao`, soma > 100% aceita.

### JU-05 — Seleção com excesso de candidatos
Depende de JU-01 + mutation `confirmarSelecao` (Sprint 2.4). 5 candidatos, 2 vagas; verificar ordem de prioridade e log de auditoria.

### JU-06 — Suspensão do PGD e retorno
Depende de JU-02. Mutation `suspenderPgd` → verificar 5 planos cancelados + 10 notificações.

### JU-07 — Retry de envio à API Central
Independente. Mock da API com 503 → 3 falhas → reprocessamento manual → sucesso. Reutiliza padrão de `test_conformidade.py`.

**JU-08 deferida** — depende de RF-037 (delegação), não implementado.

---

## Sequência de execução por TDD

```
Sprint 2.3:
  1. test_relatorio_pe_avaliacao_pendente (RED→GREEN) ✅ DONE
  2. relatorio_pe_avaliacao_pendente() em relatorios.py ✅ DONE
  3. test_rotulo_no_payload_api (RED→GREEN) ✅ DONE
  4. mapper._contribuicao() atualizado ✅ DONE
  5. test_relatorio_frequencia (escrito, fix PE sobreposição aplicado) ⚠️ VERIFICAR
  6. relatorio_frequencia() em relatorios.py ✅ DONE

Sprint 2.4: (não iniciado)
  7. Tipos + inputs em participante.py e plano.py
  8. Tests GQL (RED) em test_graphql.py ou test_gql_novos.py
  9. Mutations + queries em schema.py (GREEN)

Sprint 2.5: (não iniciado)
  10. tests/test_jornadas.py — JU-01..07 (RED)
  11. Ajustes menores de service/schema necessários (GREEN)
```

---

## Arquivos críticos

| Arquivo | Operação | Status |
|---------|----------|--------|
| `src/services/relatorios.py` | +`relatorio_pe_avaliacao_pendente`, +`relatorio_frequencia` | ✅ Feito |
| `src/integration/mapper.py` | +`rotulo` em `_contribuicao()` | ✅ Feito |
| `tests/test_relatorios.py` | +2 casos TC-M07-009 | ✅ Feito |
| `tests/test_gestao_rh.py` | +2 unit TC-M10-002, +1 integration TC-M10-007 | ⚠️ Escrito; TC-M10-007 com fix pendente de verificação |
| `src/graphql/participante.py` | +`ProcessoSelecaoType`, `TermoGuardaEquipamentoType`, `ConfirmarSelecaoInput`, `RegistrarAutorizacaoEquipamentosInput`, enum `CriteriosPrioridadeGql` | ❌ Não iniciado |
| `src/graphql/plano.py` | +`rotulo` em `ContribuicaoType`; +`aprovado_por_user_id`/`data_aprovacao` em `PlanoEntregasType`; +`AprovarPlanoEntregasInput` | ❌ Não iniciado |
| `src/graphql/schema.py` | +3 mutations, +4 queries | ❌ Não iniciado |
| `tests/test_graphql.py` | +6 casos GQL (Sprint 2.4) | ❌ Não iniciado |
| `tests/test_jornadas.py` | Novo arquivo — JU-01 a JU-07 | ❌ Não iniciado |
| `alembic/versions/` | Nenhuma nova migração necessária — todos os modelos já existem | — |

### Detalhe do fix pendente (TC-M10-007)

O teste `test_relatorio_frequencia_retorna_participantes_no_periodo` falhava porque criava 3 `PlanoEntregas` para o mesmo `ue.id` no mesmo período (violação de sobreposição). O fix — mover `criar_plano_entregas` para fora do loop e compartilhar um único PE — foi aplicado como última edição antes do interrupt. **Verificar rodando os testes antes de avançar para Sprint 2.4.**

---

## Verificação

```bash
# Após Sprint 2.3
pytest tests/test_relatorios.py tests/test_gestao_rh.py -v

# Após Sprint 2.4
pytest tests/test_graphql.py -v    # ou test_gql_novos.py
ruff check src tests               # sem novos erros

# Após Sprint 2.5
pytest tests/test_jornadas.py -v

# Suite completa — target: ~180+/189 TCs
pytest -q
```

---

## Deferidos (fora deste plano)

| Item | Motivo |
|------|--------|
| TC-M10-008 afastamentos | Requer novo modelo `Afastamento` — sprint isolada |
| TC-M10-005/006 adicional noturno | Requer novo modelo/service de autorização noturna |
| RF-037 delegação + JU-08 | Requer modelo `DelegacaoCompetencia` + RBAC dinâmico |
| RF-024 TC-M05-010 agendamento | Requer integração Cloud Scheduler — infra externa |
| RF-025 CRUD usuários | UX admin — baixa urgência vs. cobertura legal |
