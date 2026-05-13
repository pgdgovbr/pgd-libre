# Handoff: Estado atual + próximas sprints (2.6 → 2.8)

**Data:** 2026-05-13  
**Estado da suite:** 269 passed, 8 skipped — zero falhas  
**Branch:** HEAD (não commitado — todo o trabalho das sprints 2.3–2.5 está no working tree)

---

## O que foi feito nesta sessão

### Sprint 2.3 ✅ — Fechamento de TCs abertos
- `src/services/relatorios.py`: +`relatorio_pe_avaliacao_pendente()`, +`relatorio_frequencia()`
- `src/integration/mapper.py`: `_contribuicao()` agora inclui `rotulo` condicionalmente
- `tests/test_relatorios.py`: +2 casos TC-M07-009
- `tests/test_gestao_rh.py`: +2 unit tests TC-M10-002, +1 integration test TC-M10-007

### Sprint 2.4 ✅ — Camada GraphQL
- `src/graphql/participante.py`: `ProcessoSelecaoType`, `TermoGuardaEquipamentoType`, `CriteriosPrioridadeGql`, `ConfirmarSelecaoInput`, `RegistrarAutorizacaoEquipamentosInput`
- `src/graphql/plano.py`: `ContribuicaoType.rotulo`, `PlanoEntregasType.{aprovado_por_user_id, data_aprovacao}`, `AprovarPlanoEntregasInput`, `PlanoTrabalhoType.contribuicoes` (lazy-load safe via `__dict__`)
- `src/graphql/schema.py`: +3 mutations (`confirmarSelecao`, `aprovarPlanoEntregas`, `registrarAutorizacaoEquipamentos`) + 4 queries de relatório
- `tests/test_gql_novos.py`: 6 testes GQL verdes

### Sprint 2.5 ✅ — Jornadas E2E
- `tests/test_jornadas.py`: JU-01 a JU-07 (7 jornadas, todas verdes)

---

## Estado do backlog

### TCs cobertos até agora
- M02 ✅ 29/29 · M03 ✅ 19/19 · M04 ✅ 36/36 · M06 ✅ 5/5
- M07 ✅ 9/9 · M09 ✅ 5/5 · M10 ⏳ 7/13 (faltam 005, 006, 008, 009, 010, 013)
- Outros módulos: cobertos em 2.1/2.2

### O que resta (deferido)

| Sprint | TC/RF | Tema | Requer |
|--------|-------|------|--------|
| 2.6 | TC-M10-008 | Afastamentos destacados | Novo modelo `Afastamento` |
| 2.7 | TC-M10-005/006 | Adicional noturno | Novo modelo `AutorizacaoAdicionalNoturno` |
| 2.8 | RF-037 + JU-08 | Delegação de competência | Modelo `DelegacaoCompetencia` + RBAC dinâmico |
| — | RF-024 | Agendamento Cloud Scheduler | Infra externa (GCP) — deferido |
| — | RF-025 | CRUD usuários admin | UX admin — baixa urgência |

---

## Próximas sprints (a planejar)

### Sprint 2.6 — TC-M10-008: Afastamentos com código PGD diferenciado

**Contexto:** O relatório de frequência (`relatorio_frequencia`) retorna participantes com PT ativo no período. TC-M10-008 exige que afastamentos legais (licença médica, maternidade, etc.) sejam **destacados** no relatório, pois têm código PGD diferente no SIAPE Frequência.

**O que construir (TDD):**
1. Novo modelo `Afastamento` em `src/models/participante.py`:
   - `participante_id` (FK)
   - `tipo_afastamento` (enum: `LICENCA_MEDICA`, `LICENCA_MATERNIDADE`, `FERIAS`, `LICENCA_CAPACITACAO`, `OUTROS`)
   - `data_inicio` (Date)
   - `data_fim` (Date, nullable — afastamentos em curso)
   - `observacao` (Text, nullable)

2. Nova migration em `alembic/versions/`

3. Serviço `registrar_afastamento()` em `src/services/participante.py`

4. Ajuste em `relatorio_frequencia()` para retornar `(participante, afastamento | None)` — ou um novo `relatorio_afastamentos()` separado

5. GQL: tipo `AfastamentoType`, input `RegistrarAfastamentoInput`, mutation `registrarAfastamento`, campo opcional na query `relatorioFrequencia`

6. Testes em `tests/test_afastamentos.py` (novo arquivo)

**Arquivos críticos:**
- `src/models/participante.py` — novo `TipoAfastamento` enum + `Afastamento` model
- `src/services/participante.py` — `registrar_afastamento()`
- `src/services/relatorios.py` — ajuste em `relatorio_frequencia()` ou novo `relatorio_afastamentos()`
- `src/graphql/participante.py` — `AfastamentoType`, `RegistrarAfastamentoInput`
- `src/graphql/schema.py` — mutation + query
- `alembic/versions/` — nova migration

---

### Sprint 2.7 — TC-M10-005/006: Adicional Noturno

**Contexto:** Servidores em teletrabalho que trabalham regularmente em horário noturno (22h–05h) têm direito a adicional noturno, mas precisam de **autorização prévia** da chefia. TC-M10-005 cobre a criação da autorização; TC-M10-006 cobre a validação de que PT com teletrabalho noturno sem autorização é rejeitado.

**O que construir (TDD):**
1. Novo modelo `AutorizacaoAdicionalNoturno` em `src/models/participante.py`:
   - `participante_id` (FK)
   - `data_inicio_autorizacao` (Date)
   - `data_fim_autorizacao` (Date, nullable)
   - `autorizado_por_user_id` (FK users)
   - `horario_inicio_noturno` (Time)
   - `horario_fim_noturno` (Time)

2. Serviço `autorizar_adicional_noturno()` em `src/services/participante.py`

3. Validação: `validate_adicional_noturno_autorizado()` — verifica se participante tem autorização ativa antes de criar PT com flag noturna

4. GQL: tipo + input + mutation

5. Testes em `tests/test_adicional_noturno.py`

**Arquivos críticos:**
- `src/models/participante.py`
- `src/services/participante.py`
- `src/graphql/participante.py` + `schema.py`
- `alembic/versions/`

---

### Sprint 2.8 — RF-037: Delegação de Competência + JU-08

**Contexto:** RF-037 permite que uma `UnidadeAutorizadora` delegue competências (ex: aprovar planos de entregas, realizar seleção) para uma `UnidadeInstituidora` ou chefia específica. JU-08 é a jornada E2E que usa essa delegação.

**O que construir (TDD):**
1. Novo modelo `DelegacaoCompetencia` em `src/models/institucional.py`:
   - `delegante_id` (FK unidade_autorizadora ou user)
   - `delegatario_id` (FK user)
   - `competencia` (enum: `APROVAR_PLANO_ENTREGAS`, `REALIZAR_SELECAO`, `AVALIAR_REGISTROS`)
   - `unidade_execucao_id` (FK, nullable — delegação restrita a UE específica)
   - `data_inicio` / `data_fim` (Date)
   - `ativo` (bool)

2. Serviço `delegar_competencia()` + `revogar_delegacao()` em `src/services/institucional.py`

3. Ajuste em permission classes (`src/graphql/permissions.py`): `has_delegated_permission()` — checa `DelegacaoCompetencia` antes de negar acesso

4. JU-08 em `tests/test_jornadas.py`: admin delega `APROVAR_PLANO_ENTREGAS` para chefia → chefia aprova PE → verificar audit log

5. Testes em `tests/test_delegacao.py`

**Arquivos críticos:**
- `src/models/institucional.py`
- `src/services/institucional.py`
- `src/graphql/permissions.py`
- `src/graphql/institucional.py` + `schema.py`
- `tests/test_delegacao.py` (novo)
- `tests/test_jornadas.py` — +JU-08

---

## Sequência TDD recomendada

```
Sprint 2.6:
  1. tests/test_afastamentos.py (RED) — modelo, serviço, relatorio
  2. Afastamento model + migration (GREEN)
  3. registrar_afastamento() service (GREEN)
  4. relatorio_afastamentos() / ajuste relatorio_frequencia (GREEN)
  5. GQL AfastamentoType + mutation (GREEN)

Sprint 2.7:
  6. tests/test_adicional_noturno.py (RED) — autorização + validação
  7. AutorizacaoAdicionalNoturno model + migration (GREEN)
  8. autorizar_adicional_noturno() + validate_* (GREEN)
  9. GQL (GREEN)

Sprint 2.8:
  10. tests/test_delegacao.py (RED) + JU-08 em test_jornadas.py (RED)
  11. DelegacaoCompetencia model + migration (GREEN)
  12. delegar_competencia() + revogar_delegacao() (GREEN)
  13. has_delegated_permission() no permission check (GREEN)
  14. JU-08 verde (GREEN)
```

---

## Comandos para retomar

```bash
cd /Users/nitai/dev/destaquesgovbr/pgd-libre/pgd-libre
source .venv/bin/activate

# Verificar estado atual
pytest -q --tb=no   # deve mostrar 269 passed

# Rodar sprint específica
pytest tests/test_afastamentos.py -v   # após escrever os testes
```

---

## Padrões estabelecidos no projeto

- **Migrations:** manuais (autogenerate não funciona com DB vazio); colocar em `alembic/versions/`, nomear `YYYYMMDD_XXXXXXXX_descricao.py`, encadear off da última versão
- **Enums SQLAlchemy:** sempre `default=` Python-side, nunca `server_default=`
- **Testes:** `asyncio_mode = "auto"` — todos async sem decorator
- **GQL enums:** Strawberry serializa pelo `.name` (maiúsculo), não pelo `.value`
- **Lazy load GQL:** usar `obj.__dict__.get("relacao")` em vez de `obj.relacao` nos helpers `_to_type()` para evitar `MissingGreenlet`
- **`modalidades_autorizadas`:** parâmetro opcional em `criar_unidade_instituidora()`, default `[1,2,3]`
- **`chefia_user_id`:** parâmetro obrigatório em `pactu_tcr()`, passar `None` em testes

---

## Arquivos chave de referência

| Arquivo | O que contém |
|---------|-------------|
| `src/models/participante.py` | Todos os modelos do participante, TCR, ProcessoSelecao, etc. |
| `src/models/plano.py` | PlanoEntregas, PlanoTrabalho, Contribuicao, AvaliacaoRegistrosExecucao |
| `src/models/institucional.py` | UA, UI, UE, AtoAutorizacao |
| `src/services/participante.py` | cadastrar_participante, pactu_tcr, confirmar_selecao, registrar_autorizacao_equipamentos |
| `src/services/plano_entregas.py` | criar_plano_entregas, aprovar_plano_entregas, avaliar_pe |
| `src/services/relatorios.py` | 5 relatórios de conformidade + relatorio_frequencia |
| `src/graphql/schema.py` | Schema monolítico: ~30 mutations + ~18 queries |
| `src/graphql/participante.py` | Tipos GQL do participante (padrão a seguir) |
| `alembic/versions/` | Última migration: `20260513_b1c2d3e4f5a6_*.py` |
| `tests/conftest.py` | Fixtures `db`, `client`, helpers `persist_user`, `set_auth_cookie` |
| `tests/test_gestao_rh.py` | Padrão `_setup()` + `_make_participante()` |
| `tests/test_jornadas.py` | Padrão de jornadas E2E (helper `_base()`, `_tcr()`, etc.) |
