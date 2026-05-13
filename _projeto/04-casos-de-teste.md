# Casos de Teste — PGD Libre

**Versão:** 0.3 — 2026-05-13  
**Abordagem:** TDD (Test-Driven Development)  
**Referência:** `01-requisitos-funcionais.md` (v0.4) · `02-modelo-dados-e-workflows.md` (v0.2)

> **Propósito:** Este documento define os casos de teste que governam a implementação. Cada funcionalidade deve ter seus testes escritos e falhando *antes* do código de produção existir. Um requisito funcional está concluído somente quando todos os seus casos de teste passam.

---

## Convenções

### Identificadores

```
TC-[MÓDULO]-[SEQUÊNCIA]
TC-M01-003  →  Módulo 1 (Gestão Institucional), caso de teste 3
```

| Módulo | Prefixo |
|--------|---------|
| Transversais (Auth, Audit, RBAC) | TC-TX |
| Gestão Institucional | TC-M01 |
| Gestão de Participantes | TC-M02 |
| Plano de Entregas | TC-M03 |
| Plano de Trabalho | TC-M04 |
| Integração API Central | TC-M05 |
| Autenticação e RBAC | TC-M06 |
| Auditoria | TC-M07 |
| Notificações | TC-M08 |
| Configuração e Multi-tenant | TC-M09 |
| Gestão de Pessoas / RH | TC-M10 |
| Multi-tenant (isolamento por unidade) | TC-MT |
| Sprint 2.2 — Conformidade / Retry | TC-S22 |

### Categorias de teste

| Sigla | Categoria | O que testa |
|-------|-----------|-------------|
| `[U]` | Unit | Função/serviço isolado; sem I/O externo; mocks permitidos |
| `[I]` | Integration | Camadas reais juntas (DB, ORM, service); sem browser |
| `[E]` | E2E | Fluxo completo via GraphQL/HTTP; DB real; sem mocks |

### Prioridade

| P1 | Obrigatório por lei; bloqueia MVP |
| P2 | Obrigatório por lei; não bloqueia MVP imediato |
| P3 | Derivado / qualidade |

### Notação

Dado/Quando/Então no nível do teste. "Cenário base" em cada grupo = happy path; demais = variantes negativas ou de borda.

---

## TC-TX — Transversais

Estes casos se aplicam a **toda operação de escrita** no sistema, independentemente do módulo. Não precisam ser repetidos em cada RF; são referenciados como "verificar TC-TX-001 e TC-TX-002".

### TC-TX-001 — Log de auditoria gerado em toda operação de escrita `[I]` P1

**Dado** que qualquer entidade do domínio é criada, atualizada ou tem status alterado,  
**Quando** a operação conclui com sucesso,  
**Então:**
- Um registro `AuditLog` é criado com `table_name`, `record_id`, `action` (CREATE/UPDATE/DELETE), `user_id`, `user_email`, `ip_address`, `created_at`, e os campos `old_values` / `new_values` corretos.
- O registro de auditoria é imutável: nenhuma API expõe operação de UPDATE ou DELETE sobre `AuditLog`.

**Variante:** operação que falha (validação ou erro de DB) não gera log de auditoria.

---

### TC-TX-002 — Operação de escrita exige usuário autenticado `[I]` P1

**Dado** que nenhum cookie `access_token` está presente,  
**Quando** qualquer mutation GraphQL ou endpoint REST de escrita é chamado,  
**Então** o sistema retorna erro de autenticação (HTTP 401 / GraphQL `UNAUTHENTICATED`).

---

### TC-TX-003 — Acesso negado por papel retorna 403 com mensagem descritiva `[I]` P1

**Dado** que o usuário está autenticado mas possui papel insuficiente,  
**Quando** tenta executar operação que exige papel superior,  
**Então** o sistema retorna HTTP 403 / GraphQL `FORBIDDEN` com mensagem indicando o papel necessário.

---

### TC-TX-004 — Isolamento multi-tenant por `(origem_unidade, cod_unidade_autorizadora)` `[I]` P1

**Dado** que existem dados de dois órgãos distintos (autorizadoras diferentes),  
**Quando** um usuário do Órgão A realiza qualquer query,  
**Então** nunca retorna registros do Órgão B, mesmo que os IDs sejam fornecidos explicitamente.

---

## TC-M01 — Gestão Institucional

### RF-001 — Ato de Autorização

#### TC-M01-001 — Registro bem-sucedido do ato de autorização `[I]` P1

**Dado** que o usuário tem papel `admin`,  
**Quando** submete a mutation `criarAtoAutorizacao` com todos os campos obrigatórios preenchidos (autoridade, data de publicação, número/referência, status=`ativo`),  
**Então:**
- O ato é persistido com `status = ativo`.
- A `UnidadeAutorizadora` passa a ter `pgd_autorizado = true`.
- Log de auditoria gerado (TC-TX-001).

---

#### TC-M01-002 — Campos obrigatórios do ato de autorização `[U]` P1

**Dado** a mutation `criarAtoAutorizacao`,  
**Quando** qualquer campo obrigatório (autoridade, data, referência) é omitido,  
**Então** o sistema retorna erro de validação com identificação do campo ausente.

---

#### TC-M01-003 — Somente `admin` pode registrar ato de autorização `[I]` P1

**Dado** que o usuário tem papel `gestor_unidade` ou `chefe_imediato` ou `servidor`,  
**Quando** tenta criar ou alterar o ato de autorização,  
**Então** retorna FORBIDDEN (TC-TX-003).

---

#### TC-M01-004 — Consulta pública do ato de autorização `[I]` P2

**Dado** que o ato de autorização está registrado,  
**Quando** qualquer usuário autenticado (qualquer papel) consulta o ato,  
**Então** o ato é retornado com todos os campos.

---

#### TC-M01-005 — Mudança de status do ato (Ativo → Suspenso → Revogado) `[I]` P1

**Dado** que existe um ato com status `ativo`,  
**Quando** o admin atualiza para `suspenso`,  
**Então** `pgd_autorizado` da autorizadora passa a `false` e log de auditoria é gerado com `old_values.status = "ativo"` e `new_values.status = "suspenso"`.

---

### RF-002 — Ato de Instituição do PGD

#### TC-M01-006 — Registro do ato de instituição exige ato de autorização ativo `[I]` P1

**Dado** que não existe ato de autorização ativo para a unidade autorizadora,  
**Quando** o admin tenta registrar o ato de instituição,  
**Então** o sistema rejeita com mensagem "Ato de autorização ativo obrigatório".

---

#### TC-M01-007 — Registro bem-sucedido do ato de instituição `[I]` P1

**Dado** que o ato de autorização está ativo,  
**Quando** o admin registra o ato de instituição com: unidade instituidora, tipos de atividades, modalidades autorizadas, percentuais de vagas, prazo de antecedência para convocação, conteúdo mínimo do TCR,  
**Então:**
- `UnidadeInstituidora` é criada com `status = em_vigor`.
- Todos os campos persistidos corretamente.
- Log de auditoria gerado.

---

#### TC-M01-008 — Percentual de vagas para TT exterior não pode superar 2% do total `[U]` P1

**Dado** que o ato de instituição é registrado com `vagas_percentual_tt_exterior = 3`,  
**Quando** a regra de negócio valida o percentual,  
**Então** retorna erro de validação "Teletrabalho no exterior limitado a 2% do total de participantes em PGD" (IN24 Art.12 §único).

---

#### TC-M01-009 — Campos do nível de produtividade adicional para teletrabalho `[U]` P1

**Dado** a mutation de criação de ato de instituição,  
**Quando** o campo `nivel_produtividade_adicional_tt` é preenchido (opcional),  
**Então** o valor é persistido e recuperável na consulta do ato.

---

### RF-003 — Suspensão e Revogação do PGD

#### TC-M01-010 — Suspensão exige fundamentação `[U]` P1

**Dado** que existe um PGD ativo para uma unidade instituidora,  
**Quando** o admin tenta suspender sem preencher `motivo_suspensao_revogacao`,  
**Então** retorna erro de validação "Fundamentação obrigatória para suspensão/revogação".

---

#### TC-M01-011 — Suspensão do PGD atualiza planos de trabalho ativos `[I]` P1

**Dado** que existem 3 planos de trabalho em status "Em Execução" (3) para participantes da unidade instituidora,  
**Quando** o admin registra a suspensão do PGD com justificativa,  
**Então:**
- `UnidadeInstituidora.status = suspenso`.
- Os 3 planos de trabalho transitam para `Cancelado (1)`.
- Notificações enviadas a todos os participantes afetados (TC-M08-006).
- Log de auditoria para cada alteração de plano.

---

#### TC-M01-012 — Planos de entregas ativos cancelados na revogação `[I]` P1

**Dado** que existe um plano de entregas em status "Em Execução" para a unidade,  
**Quando** o PGD é revogado,  
**Então** o plano de entregas também transita para `Cancelado (1)`.

---

### RF-004 — Publicidade

#### TC-M01-013 — Endpoint público de resultados não exige autenticação `[E]` P1

**Dado** que existem planos de entregas no status `Avaliado (5)` para ao menos uma unidade,  
**Quando** o endpoint público de resultados é chamado sem `access_token`,  
**Então** retorna HTTP 200 com resultados consolidados por unidade de execução.

---

#### TC-M01-014 — Resultados públicos contêm apenas dados do período mais recente `[I]` P2

**Dado** que há resultados de múltiplos anos para a mesma unidade,  
**Quando** o endpoint público é consultado,  
**Então** os dados são filtráveis por período; o padrão retorna o período mais recente.

---

#### TC-M01-015 — Download do ato de instituição disponível para admin `[I]` P2

**Dado** que o ato de instituição está registrado,  
**Quando** o admin acessa a funcionalidade de download/exportação do ato,  
**Então** o sistema retorna o documento (PDF ou texto estruturado) com todos os campos do ato.

---

## TC-M02 — Gestão de Participantes

### RF-005 — Cadastro de Participante

#### TC-M02-001 — CPF com dígitos verificadores inválidos é rejeitado `[U]` P1

**Dado** a mutation `cadastrarParticipante`,  
**Quando** o campo `cpf` contém 11 dígitos mas o 10º ou 11º dígito verificador está errado,  
**Então** retorna erro de validação "CPF inválido".

---

#### TC-M02-002 — CPF com todos os dígitos iguais é rejeitado `[U]` P1

**Dado** a mutation `cadastrarParticipante`,  
**Quando** `cpf = "11111111111"` (ou qualquer sequência homogênea de 11 dígitos),  
**Então** retorna erro de validação "CPF inválido".

---

#### TC-M02-003 — Matrícula SIAPE com 7 dígitos, não todos iguais `[U]` P1

**Dado** a mutation `cadastrarParticipante`,  
**Quando** `matricula_siape = "1234567"` (válido) ou `matricula_siape = "123456"` (6 dígitos, inválido) ou `matricula_siape = "1111111"` (todos iguais, inválido),  
**Então** apenas o primeiro caso é aceito; os demais retornam erro de validação.

---

#### TC-M02-004 — Cadastro bem-sucedido do participante `[I]` P1

**Dado** que existe unidade instituidora ativa e o participante atende os critérios de elegibilidade,  
**Quando** a chefia registra o participante com todos os campos obrigatórios válidos (CPF, matrícula, unidade de lotação, modalidade, data assinatura TCR, tipo de vínculo),  
**Então:**
- `Participante` criado com `situacao = 1` (Ativo).
- Log de auditoria gerado.
- Participante disponível para inclusão em planos de trabalho.

---

#### TC-M02-005 — Teletrabalho exige estágio probatório de 1 ano `[U]` P1

**Dado** que `modalidade_execucao` está entre 2 e 5 (teletrabalho),  
**Quando** `cumpriu_estagio_probatorio = false` ou o campo não está preenchido,  
**Então** retorna erro de validação "Teletrabalho exige cumprimento de 1 ano de estágio probatório (IN24 Art.10 §2º)".

---

#### TC-M02-006 — Teletrabalho vedado antes de 6 meses após movimentação `[U]` P1

**Dado** que o participante veio de outro órgão em teletrabalho ou regime de controle de frequência,  
**Quando** `data_ingresso_pgd` é anterior a 6 meses após a movimentação,  
**Então** retorna erro de validação "Aguardar 6 meses após a movimentação para aderir ao teletrabalho (IN24 Art.10 §3º)".

---

#### TC-M02-007 — Limite de 2% para teletrabalho no exterior (`modalidade = 4` ou `5`) `[I]` P1

**Dado** que o número atual de participantes em `modalidade_execucao = 5` já corresponde a 2% do total de participantes em PGD do órgão,  
**Quando** a chefia tenta cadastrar um novo participante com `modalidade_execucao = 5`,  
**Então** retorna erro "Limite de 2% para teletrabalho no exterior (§7º) atingido (IN24 Art.12 §único)".

---

#### TC-M02-008 — Estagiário requer acordo TCE como substituto do TCR `[U]` P1

**Dado** que `tipo_vinculo = "estagiario"`,  
**Quando** o plano de trabalho é pactuado sem TCE registrado como instrumento substituto,  
**Então** retorna erro "Para estagiários, o TCR deve constar no Termo de Compromisso de Estágio (IN52 Art.20)".

---

#### TC-M02-009 — Empregado de empresa pública exige autorização de origem para teletrabalho `[U]` P1

**Dado** que `tipo_vinculo = "empregado_publico"` e `modalidade_execucao != 1` (não presencial),  
**Quando** o participante é cadastrado sem o campo de autorização de origem preenchido,  
**Então** retorna erro "Empregado de empresa pública em exercício na administração federal requer autorização da entidade de origem (D11 Art.9º §4º)".

---

#### TC-M02-010 — Data mínima de assinatura do TCR `[U]` P1

**Dado** a mutation `cadastrarParticipante`,  
**Quando** `data_assinatura_tcr` é anterior a 2023-07-31,  
**Então** retorna erro de validação "Data de assinatura do TCR anterior ao início da vigência do Decreto 11.072/2022".

---

#### TC-M02-011 — Modalidade presencial (`modalidade = 1`) não exige estágio probatório `[U]` P1

**Dado** que `modalidade_execucao = 1`,  
**Quando** o participante é cadastrado com `cumpriu_estagio_probatorio = false`,  
**Então** o cadastro é aceito (modalidade presencial não é teletrabalho).

---

### RF-006 — Seleção com Critérios de Prioridade

#### TC-M02-012 — Ordenação de candidatos por prioridade legal `[U]` P1

**Dado** que há 5 candidatos e apenas 3 vagas, sendo:
- Candidato A: pessoa com deficiência
- Candidato B: responsável por dependente com deficiência
- Candidato C: mobilidade reduzida
- Candidato D: horário especial (art. 98)
- Candidato E: sem prioridade especial,

**Quando** o serviço de seleção é executado com as prioridades padrão (ordem legal),  
**Então** os candidatos A, B e C são selecionados; D e E ficam fora; a justificativa é registrada.

---

#### TC-M02-013 — Critérios da seleção são registrados no log de auditoria `[I]` P1

**Dado** que o processo de seleção é executado,  
**Quando** a chefia confirma ou ajusta a seleção,  
**Então** o log de auditoria contém os critérios técnicos utilizados e o usuário responsável.

---

#### TC-M02-014 — Seleção é impessoal: baseada em atividades e experiência `[I]` P1

**Dado** que a chefia tenta selecionar candidatos sem critério técnico registrado,  
**Quando** submete a confirmação da seleção,  
**Então** o sistema exige preenchimento do campo de critérios técnicos de adesão.

---

### RF-007 — Pactuação do TCR

#### TC-M02-015 — TCR exige todos os campos obrigatórios `[U]` P1

**Dado** a mutation `pactuarTCR`,  
**Quando** qualquer dos seguintes campos está ausente: `responsabilidades`, `modalidade_execucao`, `prazo_antecedencia_convocacao_dias`, `canais_comunicacao`, `ciencia_instalacoes_ergonomia`, `ciencia_nao_direito_adquirido`, `ciencia_custeio_estrutura`,  
**Então** retorna erro de validação indicando o campo ausente.

---

#### TC-M02-016 — Assinatura dupla: participante E chefia `[I]` P1

**Dado** que apenas o participante assinou o TCR,  
**Quando** a chefia ainda não confirmou,  
**Então** o TCR tem `status = pendente` e não pode ser usado para criar plano de trabalho.

**Então** após a chefia confirmar, `status = ativo` e o plano de trabalho pode ser criado.

---

#### TC-M02-017 — Plano de trabalho sem TCR ativo é rejeitado `[I]` P1

**Dado** que o participante não tem TCR com `status = ativo`,  
**Quando** a chefia tenta criar um plano de trabalho para o participante,  
**Então** retorna erro "TCR ativo obrigatório para criação de plano de trabalho".

---

#### TC-M02-018 — TCR com ações de melhoria obrigatório após avaliação 4 ou 5 `[I]` P1

**Dado** que o plano de trabalho anterior foi avaliado com código 4 (inadequado),  
**Quando** a chefia pactuaria novo TCR sem preencher `acoes_melhoria`,  
**Então** retorna erro "Ações de melhoria obrigatórias no TCR quando plano anterior avaliado como inadequado (IN52 Art.3º)".

---

#### TC-M02-019 — TCR com saldo de banco de horas registra prazo de 6 meses `[U]` P1

**Dado** que o participante entra no PGD com saldo positivo de 10 horas em banco de horas,  
**Quando** o TCR é pactuado com `saldo_banco_horas = 10`,  
**Então** `prazo_compensacao_banco_horas` é automaticamente calculado como `data_assinatura_participante + 6 meses`.

---

#### TC-M02-020 — Alteração nas condições do TCR exige novo TCR `[I]` P1

**Dado** que existe um TCR com `status = ativo`,  
**Quando** a chefia tenta alterar `modalidade_execucao` diretamente no TCR existente,  
**Então** retorna erro "Alteração das condições exige pactuação de novo TCR (IN24 Art.15 §único)".

**E** o fluxo correto (criar novo TCR que referencia o anterior via `tcr_anterior_id`) é aceito.

---

### RF-008 — Desligamento de Participante

#### TC-M02-021 — Desligamento exige hipótese e justificativa `[U]` P1

**Dado** a mutation `desligarParticipante`,  
**Quando** `motivo_desligamento` está ausente,  
**Então** retorna erro de validação "Hipótese de desligamento obrigatória".

---

#### TC-M02-022 — Desligamento atualiza status do participante e registra data de retorno `[I]` P1

**Dado** que o participante está em teletrabalho (modalidade 2 ou 3),  
**Quando** a chefia registra desligamento por `interesse_administracao`,  
**Então:**
- `Participante.situacao = 0` (Inativo).
- `data_desligamento` preenchida com a data atual.
- Data prevista de retorno ao controle de frequência = hoje + 30 dias.
- Notificação enviada ao participante (TC-M08-006).

---

#### TC-M02-023 — Participante no exterior tem prazo de retorno de 2 meses `[U]` P1

**Dado** que o participante tem `modalidade_execucao` igual a 4 ou 5 (teletrabalho no exterior),  
**Quando** o desligamento é registrado,  
**Então** a data prevista de retorno é = hoje + 2 meses.

---

### RF-009 — Convocação Presencial

#### TC-M02-024 — Convocação sem antecedência mínima do TCR é rejeitada `[I]` P1

**Dado** que o TCR do participante estabelece prazo mínimo de 5 dias para convocação,  
**Quando** a chefia registra convocação com antecedência de 3 dias,  
**Então** retorna erro "Prazo mínimo de convocação (5 dias) não observado (D11 Art.9º V)".

---

#### TC-M02-025 — Convocação válida notifica participante e registra evento `[I]` P1

**Dado** que a convocação tem antecedência igual ou superior ao prazo do TCR,  
**Quando** a chefia registra a convocação com canal, horário, local e período,  
**Então:**
- Convocação persistida com todos os campos.
- Notificação enviada pelo canal definido no TCR (TC-M08-005).
- Log de auditoria gerado.

---

### RF-032 — Retirada de Equipamentos

#### TC-M02-026 — Retirada de equipamentos vedada para teletrabalho parcial `[U]` P1

**Dado** que o participante está em modalidade de teletrabalho parcial (modalidade 2),  
**Quando** a chefia tenta registrar autorização de retirada de equipamentos,  
**Então** retorna erro "Retirada de equipamentos permitida apenas para teletrabalho integral (IN24 Art.16)".

---

#### TC-M02-027 — Termo de Guarda e Responsabilidade vinculado ao TCR `[I]` P1

**Dado** que o participante está em teletrabalho integral e o órgão autoriza a retirada,  
**Quando** a autorização e o Termo de Guarda são registrados,  
**Então** o registro fica vinculado ao `tcr_id` vigente do participante e disponível para consulta e auditoria.

---

### RF-033 — Acumulação de Cargos

#### TC-M02-028 — Declaração de ausência de prejuízo obrigatória para acumuladores `[I]` P1

**Dado** que o participante tem `acumula_cargos = true`,  
**Quando** o plano de trabalho é pactuado sem que todos os 4 itens da declaração sejam confirmados,  
**Então** retorna erro "Declaração de ausência de prejuízo obrigatória para acumuladores de cargos (IN52 Art.19)".

---

#### TC-M02-029 — Declaração de acumulação rastreável no log de auditoria `[I]` P1

**Dado** que o participante confirma a declaração de ausência de prejuízo,  
**Quando** o plano de trabalho é pactuado,  
**Então** a declaração é persistida com `user_id`, `data_hora` e os 4 itens confirmados individualmente.

---

## TC-M03 — Plano de Entregas

### RF-010 — Elaboração do Plano de Entregas

#### TC-M03-001 — Duração máxima de 1 ano `[U]` P1

**Dado** a mutation `criarPlanoEntregas`,  
**Quando** `data_termino - data_inicio > 365 dias` (ou 366 em ano bissexto, usando cálculo de data real),  
**Então** retorna erro de validação "Duração máxima de 1 ano (IN24 Art.18 §1º)".

---

#### TC-M03-002 — `data_termino` não pode ser anterior ou igual a `data_inicio` `[U]` P1

**Dado** a mutation `criarPlanoEntregas`,  
**Quando** `data_termino <= data_inicio`,  
**Então** retorna erro de validação "Data de término deve ser posterior à data de início".

---

#### TC-M03-003 — Plano sem entregas (exceto cancelado) é rejeitado `[U]` P1

**Dado** a mutation `criarPlanoEntregas` com `status != 1` (não é Cancelado),  
**Quando** `lista_entregas` está vazia,  
**Então** retorna erro "Plano de entregas deve ter ao menos uma entrega".

---

#### TC-M03-004 — IDs de entrega devem ser únicos dentro do plano `[U]` P1

**Dado** a mutation `criarPlanoEntregas`,  
**Quando** duas entregas possuem o mesmo `id_entrega`,  
**Então** retorna erro "IDs de entrega devem ser únicos dentro do plano".

---

#### TC-M03-005 — Sobreposição de períodos para a mesma unidade executora é rejeitada `[I]` P1

**Dado** que existe um plano de entregas ativo (`status` 3, 4 ou 5) para a Unidade X no período 2026-01-01 a 2026-06-30,  
**Quando** a chefia tenta criar outro plano para a Unidade X com período 2026-04-01 a 2026-12-31,  
**Então** retorna HTTP 422 / GraphQL `BAD_USER_INPUT` com mensagem "Sobreposição de período com plano de entregas ativo para esta unidade".

---

#### TC-M03-006 — Dois planos sem sobreposição para a mesma unidade são aceitos `[I]` P1

**Dado** que existe plano encerrado (status 4 ou 5) terminando em 2025-12-31,  
**Quando** a chefia cria novo plano com `data_inicio = 2026-01-01`,  
**Então** o novo plano é criado com sucesso.

---

#### TC-M03-007 — Plano criado com status inicial Aprovado (2) `[I]` P1

**Dado** que a chefia submete o plano com todos os campos válidos,  
**Quando** a mutation é executada,  
**Então** `PlanoEntregas.status = 2` (Aprovado), independente do valor informado pelo chamador.

---

#### TC-M03-008 — Criação de plano requer papel `chefe_imediato` ou superior `[I]` P1

**Dado** que o usuário tem papel `servidor`,  
**Quando** tenta criar plano de entregas,  
**Então** retorna FORBIDDEN.

---

### RF-011 — Aprovação pelo Nível Hierárquico Superior

#### TC-M03-009 — Aprovação pelo nível superior atualiza status e notifica chefia `[I]` P1

**Dado** que o plano está no status Aprovado (2) e foi submetido ao nível superior,  
**Quando** o nível superior aprova (sem ajustes),  
**Então:**
- `aprovado_por_user_id` e `data_aprovacao` preenchidos.
- Notificação enviada à chefia.
- Log de auditoria gerado.

---

#### TC-M03-010 — Unidade instituidora dispensa aprovação hierárquica `[I]` P1

**Dado** que `UnidadeExecucao.coincide_com_instituidora = true`,  
**Quando** o plano de entregas é submetido,  
**Então** transita diretamente para "Em Execução" (3) sem aguardar aprovação do nível superior.

---

#### TC-M03-011 — Chefia não pode aprovar o próprio plano de entregas `[I]` P1

**Dado** que o usuário é a própria chefia que criou o plano,  
**Quando** tenta aprovar o plano,  
**Então** retorna FORBIDDEN "A chefia criadora não pode aprovar o próprio plano".

---

### RF-012 — Execução e Monitoramento

#### TC-M03-012 — Transição Aprovado (2) → Em Execução (3) `[I]` P1

**Dado** que o plano está no status 2 (Aprovado),  
**Quando** a chefia inicia a execução,  
**Então** `PlanoEntregas.status = 3` (Em Execução).

---

#### TC-M03-013 — Ajuste durante execução exige data e justificativa `[U]` P1

**Dado** que o plano está Em Execução (3),  
**Quando** a chefia altera uma entrega sem fornecer justificativa,  
**Então** retorna erro "Justificativa obrigatória para ajustes durante a execução".

---

#### TC-M03-014 — Ajuste em plano Em Execução comunica ao nível superior `[I]` P1

**Dado** que a chefia registra ajuste justificado em entrega durante a execução,  
**Quando** o ajuste é salvo,  
**Então** `ajustes_comunicados_em` é preenchido com data/hora atual; log de auditoria gerado.

---

### RF-013 — Avaliação do Plano de Entregas

#### TC-M03-015 — Avaliação só pode ser registrada pelo nível hierárquico superior `[I]` P1

**Dado** que o plano está Concluído (4),  
**Quando** a própria chefia tenta avaliar o plano,  
**Então** retorna FORBIDDEN "Avaliação deve ser feita pelo nível hierárquico superior (IN24 Art.22)".

---

#### TC-M03-016 — Avaliação dentro do prazo de 30 dias `[U]` P1

**Dado** que o plano passou para Concluído (4) em uma data X,  
**Quando** o sistema verifica conformidade de prazos,  
**Então** avaliações com `data_avaliacao > X + 30 dias` são marcadas como "avaliação em atraso" no relatório de conformidade.

---

#### TC-M03-017 — Avaliação na escala 1–5 transiciona para Avaliado (5) `[I]` P1

**Dado** que o plano está Concluído (4),  
**Quando** o nível superior registra avaliação com `avaliacao = 3` (Adequado) e `data_avaliacao = hoje`,  
**Então** `PlanoEntregas.status = 5` (Avaliado); dados disponíveis para envio à API Central.

---

#### TC-M03-018 — `data_avaliacao` não pode ser anterior à `data_inicio` do plano `[U]` P1

**Dado** que o plano tem `data_inicio = 2026-01-01`,  
**Quando** a avaliação é registrada com `data_avaliacao = 2025-12-31`,  
**Então** retorna erro "Data de avaliação anterior à data de início do plano".

---

#### TC-M03-019 — Avaliação não se aplica a unidade instituidora `[I]` P1

**Dado** que `UnidadeExecucao.coincide_com_instituidora = true`,  
**Quando** o nível superior tenta avaliar o plano de entregas,  
**Então** retorna erro "Avaliação do plano de entregas não se aplica à unidade instituidora (IN24 Art.22 §2º)".

---

## TC-M04 — Plano de Trabalho

### RF-014 — Elaboração e Pactuação

#### TC-M04-001 — TCR ativo é pré-condição `[I]` P1

**Dado** que o participante não tem TCR com `status = ativo`,  
**Quando** a chefia tenta criar o plano de trabalho,  
**Então** retorna erro "TCR ativo obrigatório para plano de trabalho".

---

#### TC-M04-002 — Plano de entregas aprovado ou em execução é pré-condição `[I]` P1

**Dado** que não existe plano de entregas com `status` 2 ou 3 para a unidade de execução,  
**Quando** a chefia tenta criar o plano de trabalho,  
**Então** retorna erro "Plano de entregas aprovado ou em execução obrigatório".

---

#### TC-M04-003 — `data_inicio` do PT deve ser >= `data_inicio` do PE referenciado `[U]` P1

**Dado** que o plano de entregas referenciado tem `data_inicio = 2026-03-01`,  
**Quando** o plano de trabalho é criado com `data_inicio = 2026-02-01`,  
**Então** retorna erro "Data de início do plano de trabalho anterior à data de início do plano de entregas vinculado".

---

#### TC-M04-004 — Duração máxima de 1 ano `[U]` P1

Análogo ao TC-M03-001 para planos de trabalho.

---

#### TC-M04-005 — Sobreposição de períodos por participante é rejeitada `[I]` P1

**Dado** que existe plano de trabalho ativo (status 3 ou 4) para o participante no período 2026-01-01 a 2026-06-30,  
**Quando** a chefia tenta criar novo plano para o mesmo participante com período sobreposto,  
**Então** retorna HTTP 422 / `BAD_USER_INPUT` "Sobreposição de período com plano de trabalho ativo para este participante".

---

#### TC-M04-006 — Soma das contribuições = 100% (caso normal) `[U]` P1

**Dado** a mutation `criarPlanoTrabalho` com 3 contribuições de 40%, 40% e 30%,  
**Quando** a validação de percentuais é executada,  
**Então** retorna erro "Soma dos percentuais de contribuição deve ser 100% (atual: 110%)".

---

#### TC-M04-007 — Soma < 100% sem contexto de banco de horas é rejeitada `[U]` P1

**Dado** que o TCR não registra saldo de banco de horas a usufruir,  
**Quando** a soma das contribuições é 90%,  
**Então** retorna erro "Soma dos percentuais de contribuição deve ser 100%".

---

#### TC-M04-008 — Soma > 100% com compensação de horas é aceita `[U]` P1

**Dado** que o TCR registra `carga_horaria_compensacao > 0` (horas a compensar),  
**Quando** a soma das contribuições é 120%,  
**Então** o plano é aceito (compensação permite soma > 100%).

---

#### TC-M04-009 — Soma < 100% com usufruto de banco de horas é aceita `[U]` P1

**Dado** que o TCR registra `saldo_banco_horas > 0` (crédito a usufruir),  
**Quando** a soma das contribuições é 80%,  
**Então** o plano é aceito (usufruto de saldo permite soma < 100%).

---

#### TC-M04-010 — Contribuição tipo 1 exige `id_plano_entregas` e `id_entrega` `[U]` P1

**Dado** que uma contribuição tem `tipo = 1`,  
**Quando** `id_plano_entregas` ou `id_entrega` está ausente,  
**Então** retorna erro "Contribuição tipo 1 exige referência ao plano de entregas e à entrega".

---

#### TC-M04-011 — Contribuição tipo 2 não aceita `id_plano_entregas` `[U]` P1

**Dado** que uma contribuição tem `tipo = 2`,  
**Quando** `id_plano_entregas` está preenchido,  
**Então** retorna erro "Contribuição tipo 2 não pode referenciar plano de entregas".

---

#### TC-M04-012 — Contribuição tipo 3 aceita referência a outra unidade `[U]` P1

**Dado** que uma contribuição tem `tipo = 3` com referência a plano de entregas de outra unidade,  
**Quando** a contribuição é validada,  
**Então** é aceita; o sistema não exige que a unidade referenciada seja a unidade de execução do participante.

---

#### TC-M04-013 — Lista de contribuições vazia rejeitada (exceto status Cancelado) `[U]` P1

**Dado** a mutation `criarPlanoTrabalho` com `status != 1` e `lista_contribuicoes = []`,  
**Quando** a validação ocorre,  
**Então** retorna erro "Plano de trabalho deve ter ao menos uma contribuição".

---

### RF-015 — Registro de Execução

#### TC-M04-014 — Registro de execução aceito apenas em status Em Execução (3) `[I]` P1

**Dado** que o plano de trabalho está em status Aprovado (2),  
**Quando** o participante tenta registrar execução,  
**Então** retorna erro "Registro de execução disponível apenas para planos Em Execução".

---

#### TC-M04-015 — Prazo de registro: plano ≤ 30 dias → 10 dias após encerramento `[U]` P1

**Dado** que o plano tem duração de 20 dias e encerrou em 2026-06-20,  
**Quando** o serviço verifica prazos,  
**Então** o prazo limite para registro é 2026-06-30 (10 dias após encerramento).

---

#### TC-M04-016 — Prazo de registro: plano > 30 dias → até o 10º dia do mês subsequente `[U]` P1

**Dado** que o plano tem duração de 90 dias e o período de registro é fevereiro de 2026,  
**Quando** o serviço verifica prazos,  
**Então** o prazo limite para o registro de fevereiro é 2026-03-10.

---

#### TC-M04-017 — Alerta 3 dias antes do prazo de registro `[I]` P1

**Dado** que o prazo de registro de um participante é 2026-03-10,  
**Quando** o worker de lembretes roda em 2026-03-07,  
**Então** notificação de prazo iminente é enviada ao participante (TC-M08-003).

---

#### TC-M04-018 — Chefia pode ajustar plano durante execução com justificativa `[I]` P1

**Dado** que o plano está Em Execução (3),  
**Quando** a chefia registra ajuste em contribuição com justificativa,  
**Então** a alteração é registrada com `user_id`, `data_hora`, `justificativa`; log de auditoria gerado; participante notificado.

---

### RF-016 — Transição de Status do Plano de Trabalho

#### TC-M04-019 — Máquina de estados: transições válidas `[U]` P1

Para o plano de trabalho, as transições válidas são:
- `2 → 3` (Aprovado → Em Execução): aceita.
- `3 → 4` (Em Execução → Concluído): aceita.
- `2 → 1`, `3 → 1`, `4 → 1` (qualquer → Cancelado): aceita.

**Dado** cada transição acima,  
**Quando** executada,  
**Então** o status é atualizado com sucesso.

---

#### TC-M04-020 — Máquina de estados: transições inválidas `[U]` P1

Transições inválidas: `4 → 3`, `1 → 2`, `3 → 2`, `5 → qualquer`.  
**Quando** tentadas,  
**Então** retorna erro "Transição de status inválida".

---

### RF-017 — Avaliação pelo Período Avaliativo

#### TC-M04-021 — Avaliação realizada em até 20 dias `[U]` P1

**Dado** que o participante finalizou o registro de execução em uma data X,  
**Quando** o serviço de conformidade verifica,  
**Então** avaliações com `data_avaliacao > X + 20 dias` são marcadas como "avaliação em atraso".

---

#### TC-M04-022 — Avaliações 1, 4 e 5 exigem justificativa obrigatória `[U]` P1

**Dado** a mutation `avaliarPeriodo`,  
**Quando** `avaliacao = 1` (Excepcional), `4` (Inadequado) ou `5` (Não executado) e `justificativa` está ausente,  
**Então** retorna erro "Justificativa obrigatória para esta avaliação (IN24 Art.21)".

---

#### TC-M04-023 — Avaliação registrada notifica participante imediatamente `[I]` P1

**Dado** que a chefia registra qualquer avaliação,  
**Quando** a avaliação é salva,  
**Então** notificação imediata é enviada ao participante com o resultado (TC-M08-001).

---

#### TC-M04-024 — Avaliação 4 (inadequado por execução abaixo) sinaliza ações de melhoria `[I]` P1

**Dado** que a chefia registra avaliação 4 com causa "execução abaixo do esperado (sem inexecução)" e justificativa,  
**Quando** a avaliação é salva,  
**Então:**
- Sistema sinaliza "ações de melhoria obrigatórias no próximo TCR".
- Notificação enviada ao participante com prazo para recurso.
- Log de auditoria gerado.

---

#### TC-M04-025 — Avaliação 4 por inexecução parcial sinaliza ações de melhoria + compensação `[I]` P1

**Dado** que a chefia registra avaliação 4 com causa "inexecução parcial" e justificativa,  
**Quando** a avaliação é salva,  
**Então:**
- Sistema sinaliza "ações de melhoria + compensação de carga horária no próximo plano".
- Participante notificado (TC-M08-001).

---

#### TC-M04-026 — Avaliação 5 (não executado) sinaliza ações de melhoria + compensação + possível desconto `[I]` P1

**Dado** que a chefia registra avaliação 5 com justificativa,  
**Quando** a avaliação é salva,  
**Então:**
- Sinalização de "ações de melhoria + compensação no próximo plano".
- Se a inexecução não tiver justificativa aceita: sinalizar possível desconto em folha.
- Chefia recebe aviso sobre obrigação de encaminhar dados à gestão de pessoas se desconto for aplicável.

---

### RF-018 — Recurso de Avaliação

#### TC-M04-027 — Recurso disponível apenas para avaliações 4 ou 5 `[I]` P1

**Dado** que o participante foi avaliado com código 3 (Adequado),  
**Quando** tenta submeter recurso,  
**Então** retorna erro "Recurso disponível apenas para avaliações Inadequado (4) ou Não Executado (5)".

---

#### TC-M04-028 — Prazo de recurso: 10 dias após notificação `[U]` P1

**Dado** que o participante foi notificado da avaliação 4 em uma data X,  
**Quando** o participante tenta submeter recurso após X + 11 dias,  
**Então** retorna erro "Prazo de recurso expirado (10 dias a partir da notificação)".

---

#### TC-M04-029 — Recurso submetido notifica chefia com prazo de 10 dias `[I]` P1

**Dado** que o participante submete recurso dentro do prazo,  
**Quando** o recurso é registrado,  
**Então** notificação enviada à chefia com prazo de 10 dias para resposta (TC-M08-002).

---

#### TC-M04-030 — Chefia aceita recurso: avaliação ajustada `[I]` P1

**Dado** que a chefia decide acatar o recurso,  
**Quando** registra a decisão com `acatado = true` e nova avaliação,  
**Então** a avaliação original é atualizada (mantendo histórico via log de auditoria); participante notificado.

---

#### TC-M04-031 — Chefia nega recurso: fundamentação obrigatória `[U]` P1

**Dado** que a chefia decide não acatar o recurso,  
**Quando** registra a decisão com `acatado = false` sem `fundamentacao`,  
**Então** retorna erro "Fundamentação obrigatória ao não acatar recurso".

---

#### TC-M04-032 — Decisão do recurso sempre rastreável `[I]` P1

**Dado** que qualquer decisão (acatar ou não acatar) é registrada,  
**Quando** o log de auditoria é consultado,  
**Então** contém `user_id`, `data_hora`, `decisao`, `fundamentacao` (quando aplicável), vinculados ao recurso.

---

### RF-019 — Compensação de Carga Horária

#### TC-M04-033 — Próximo plano pré-preenchido com carga de compensação `[I]` P1

**Dado** que o plano anterior foi avaliado com código 4 por inexecução de 20 horas,  
**Quando** a chefia cria o próximo plano de trabalho para o participante,  
**Então:**
- O sistema pré-preenche `carga_horaria_compensacao = 20` no novo TCR.
- Exige preenchimento de `prazo_compensacao_inexecucao` no TCR.

---

#### TC-M04-034 — Compensação permite soma de percentuais > 100% `[U]` P1

**Dado** que o TCR registra `carga_horaria_compensacao > 0`,  
**Quando** a soma das contribuições é 120%,  
**Então** a validação aceita (IN52 Art.5º).

---

### RF-020 — Banco de Horas

#### TC-M04-035 — Nova adesão ao banco de horas bloqueada para participantes do PGD `[I]` P1

**Dado** que o participante tem `situacao = 1` (ativo no PGD),  
**Quando** o sistema de RH tenta registrar nova adesão ao banco de horas,  
**Então** retorna erro "Participantes do PGD não podem aderir ao banco de horas (IN52 Art.18)".

---

#### TC-M04-036 — Saldo de banco de horas registrado no TCR com prazo de 6 meses `[I]` P1

**Dado** que um participante entra no PGD com saldo de banco de horas,  
**Quando** o TCR é pactuado,  
**Então** `saldo_banco_horas` é registrado e `prazo_compensacao_banco_horas = data_assinatura + 6 meses`.

---

---

## TC-M05 — Integração com a API PGD Central

### RF-021 — Envio de Participantes

#### TC-M05-001 — Envio mapeado com todos os campos obrigatórios `[I]` P1

**Dado** que um participante foi cadastrado ou teve `situacao`/`modalidade_execucao` alterada,  
**Quando** o worker de sincronização executa,  
**Então** o payload enviado ao endpoint `PUT /organizacao/{origem_unidade}/{cod_unidade_autorizadora}/{cod_unidade_lotacao}/participante/{matricula_siape}` contém todos os campos obrigatórios: `origem_unidade`, `cod_unidade_autorizadora`, `cod_unidade_lotacao`, `matricula_siape`, `cod_unidade_instituidora`, `cpf`, `situacao`, `modalidade_execucao`, `data_assinatura_tcr`.

---

#### TC-M05-002 — Retentativa com backoff em falha 5xx ou timeout `[U]` P1

**Dado** que a API Central retorna HTTP 503 na primeira tentativa,  
**Quando** o worker executa a retentativa,  
**Então:**
- 1ª retentativa após 1 minuto.
- 2ª retentativa após 5 minutos.
- 3ª retentativa após 30 minutos.
- Após 3 falhas: `RegistroEnvioAPI.status = erro_permanente`; alerta ao administrador.

---

#### TC-M05-003 — Falha de validação 422 registrada sem retentativa `[I]` P1

**Dado** que a API Central retorna HTTP 422 (erro de validação),  
**Quando** o worker recebe a resposta,  
**Então** o erro é registrado em `RegistroEnvioAPI` com `http_status = 422` e `resposta_body` completo; **nenhuma retentativa** automática (o dado é inválido e precisa de correção manual).

---

#### TC-M05-004 — Envio bem-sucedido atualiza `api_sincronizado_em` `[I]` P1

**Dado** que a API Central retorna HTTP 200 ou 201,  
**Quando** o worker confirma sucesso,  
**Então** o registro do participante tem `api_sincronizado_em = now()`.

---

#### TC-M05-005 — User-Agent obrigatório nas requisições à API Central `[U]` P1

**Dado** que o cliente HTTP da API Central é configurado,  
**Quando** qualquer requisição é feita,  
**Então** o header `User-Agent` está presente com valor configurável (ex.: `pgd-libre/1.0`).

---

### RF-022 — Envio de Planos de Entregas

#### TC-M05-006 — Apenas planos nos status 3, 4 e 5 são enviados `[I]` P1

**Dado** que existem planos nos status 1, 2, 3, 4 e 5,  
**Quando** o worker de sincronização executa,  
**Então** apenas planos com `status in (3, 4, 5)` são incluídos no lote de envio.

---

#### TC-M05-007 — Payload do plano de entregas contém todos os campos do schema da API `[I]` P1

**Dado** que um plano de entregas passa para status 3,  
**Quando** o mapper é executado,  
**Então** o payload contém: `origem_unidade`, `cod_unidade_autorizadora`, `cod_unidade_instituidora`, `cod_unidade_executora`, `id_plano_entregas`, `status`, `data_inicio`, `data_termino`, `avaliacao` (quando status=5), `data_avaliacao` (quando status=5), `lista_entregas` completa.

---

### RF-023 — Envio de Planos de Trabalho

#### TC-M05-008 — Apenas planos nos status 3 e 4 são enviados `[I]` P1

**Dado** que existem planos de trabalho nos status 1, 2, 3 e 4,  
**Quando** o worker executa,  
**Então** apenas `status in (3, 4)` são enviados.

---

#### TC-M05-009 — Payload inclui contribuições e avaliações de registros de execução `[I]` P1

**Dado** que o plano de trabalho tem 2 contribuições e 1 avaliação de registro de execução,  
**Quando** o mapper é executado,  
**Então** o payload inclui `lista_contribuicoes` e `avaliacoes_registros_execucao` com todos os campos mapeados.

---

### RF-024 — Agendamento e Monitoramento

#### TC-M05-010 — Envio manual sob demanda pelo administrador `[E]` P2

**Dado** que o admin acessa o painel de integração,  
**Quando** aciona o envio manual,  
**Então** o worker é disparado imediatamente e o resultado aparece no histórico em até 5 minutos.

---

#### TC-M05-011 — Painel de conformidade exibe pendentes, erros e enviados `[E]` P2

**Dado** que há: 5 participantes enviados com sucesso, 2 com erro, 3 pendentes,  
**Quando** o admin acessa o painel de conformidade,  
**Então** exibe os totais corretos com detalhes de cada categoria.

---

#### TC-M05-012 — Reprocessamento manual de envios com falha `[I]` P2

**Dado** que há `RegistroEnvioAPI` com `status = erro_permanente`,  
**Quando** o admin aciona reprocessamento desse registro,  
**Então** uma nova tentativa de envio é realizada e o resultado é registrado.

---

---

## TC-M06 — Autenticação e RBAC

### RF-025 — Gestão de Usuários

#### TC-M06-001 — Login com Google OAuth redireciona e cria sessão `[E]` P1

**Dado** que `GOOGLE_CLIENT_ID` está configurado,  
**Quando** o usuário acessa `/auth/login/google`,  
**Então** é redirecionado para o Google; após callback com token válido, cookie `access_token` (httpOnly, SameSite=Lax) é definido e o usuário é criado/atualizado no banco.

---

#### TC-M06-002 — Usuário criado via OAuth tem papel padrão `servidor` `[I]` P1

**Dado** que um novo e-mail realiza login pela primeira vez via OAuth,  
**Quando** o callback é processado,  
**Então** um `User` é criado com `role = servidor` e `is_active = true`.

---

#### TC-M06-003 — Admin pode alterar papel de qualquer usuário `[I]` P1

**Dado** que o usuário autenticado tem papel `admin`,  
**Quando** executa a mutation `atualizarPapelUsuario(userId, role: "chefe_imediato")`,  
**Então** o usuário tem `role = chefe_imediato`; log de auditoria gerado.

---

#### TC-M06-004 — Usuário não pode alterar o próprio papel `[I]` P1

**Dado** que o usuário autenticado tem papel `admin`,  
**Quando** tenta alterar o próprio papel,  
**Então** retorna FORBIDDEN "Não é permitido alterar o próprio papel".

---

#### TC-M06-005 — Desativação de usuário revoga acesso imediatamente `[I]` P1

**Dado** que o admin desativa um usuário (`is_active = false`),  
**Quando** o usuário desativado tenta realizar qualquer requisição autenticada,  
**Então** retorna 401 "Conta desativada".

---

#### TC-M06-006 — Logout exclui cookie `access_token` `[E]` P1

**Dado** que o usuário está autenticado (cookie presente),  
**Quando** chama `POST /auth/logout`,  
**Então** o cookie `access_token` é removido da resposta; requisições subsequentes sem novo login retornam 401.

---

#### TC-M06-007 — Provider não configurado retorna 404 `[I]` P1

**Dado** que `GOVBR_CLIENT_ID` não está configurado,  
**Quando** o usuário acessa `/auth/login/govbr`,  
**Então** retorna HTTP 404 "Provider 'govbr' não configurado".

---

### RF-026 — Controle de Acesso por Papel (RBAC)

#### TC-M06-008 — Matriz de papéis: admin acessa tudo `[I]` P1

**Dado** que o usuário tem papel `admin`,  
**Quando** executa qualquer operação do sistema,  
**Então** nenhuma operação retorna FORBIDDEN por papel.

---

#### TC-M06-009 — Servidor só acessa seu próprio plano de trabalho `[I]` P1

**Dado** que o usuário tem papel `servidor` e está vinculado ao participante X,  
**Quando** tenta consultar o plano de trabalho do participante Y,  
**Então** retorna FORBIDDEN ou a query retorna resultado vazio.

---

#### TC-M06-010 — Servidor não pode criar plano de trabalho `[I]` P1

**Dado** que o usuário tem papel `servidor`,  
**Quando** tenta executar a mutation `criarPlanoTrabalho`,  
**Então** retorna FORBIDDEN.

---

#### TC-M06-011 — `chefe_imediato` só acessa dados de sua própria unidade `[I]` P1

**Dado** que o usuário tem papel `chefe_imediato` vinculado à Unidade X,  
**Quando** tenta aprovar um plano de entregas da Unidade Y,  
**Então** retorna FORBIDDEN.

---

#### TC-M06-012 — JWT expirado retorna 401 `[U]` P1

**Dado** que o token JWT tem `exp` no passado,  
**Quando** o middleware `get_optional_user` valida o token,  
**Então** retorna `user = None`; a requisição de recurso protegido retorna 401.

---

#### TC-M06-013 — JWT assinado com chave errada retorna 401 `[U]` P1

**Dado** que o token JWT foi assinado com uma `SECRET_KEY` diferente da configurada no servidor,  
**Quando** o middleware valida o token,  
**Então** retorna `user = None`; requisição protegida retorna 401.

---

---

## TC-M07 — Auditoria e Rastreabilidade

### RF-027 — Log de Auditoria

#### TC-M07-001 — Log de auditoria não pode ser deletado via API `[I]` P1

**Dado** que existe um registro em `AuditLog`,  
**Quando** qualquer usuário (incluindo `admin`) tenta deletar via API,  
**Então** a operação é bloqueada (endpoint não existe ou retorna 405 Method Not Allowed).

---

#### TC-M07-002 — Log de auditoria não pode ser modificado via API `[I]` P1

**Dado** que existe um registro em `AuditLog`,  
**Quando** qualquer usuário tenta modificar via API,  
**Então** a operação é bloqueada.

---

#### TC-M07-003 — `old_values` e `new_values` refletem estado exato antes e depois `[I]` P1

**Dado** que um participante tem `modalidade_execucao = 1` e é alterado para `2`,  
**Quando** a atualização é persistida,  
**Então** o log gerado tem:
```json
{ "old_values": { "modalidade_execucao": 1 }, "new_values": { "modalidade_execucao": 2 } }
```

---

#### TC-M07-004 — CPF não aparece em logs de auditoria em texto claro `[I]` P1

**Dado** que um participante com CPF `123.456.789-09` é criado,  
**Quando** o log de auditoria é consultado,  
**Então** o CPF aparece mascarado (ex.: `123.***.***-09`) no campo `new_values`.

---

### RF-028 — Relatórios de Conformidade

#### TC-M07-005 — Relatório: participantes sem plano de trabalho ativo `[I]` P2

**Dado** que existem participantes ativos (situacao=1) sem plano de trabalho em status 3 ou 4,  
**Quando** o relatório de conformidade é gerado,  
**Então** esses participantes aparecem na lista "Sem plano de trabalho ativo".

---

#### TC-M07-006 — Relatório: planos de trabalho com registro em atraso `[I]` P2

**Dado** que o prazo de registro de execução de um participante venceu sem registro,  
**Quando** o relatório é gerado,  
**Então** o plano aparece na lista "Registros em atraso" com indicação do prazo vencido.

---

#### TC-M07-007 — Relatório: planos com avaliação pendente (chefia) `[I]` P2

**Dado** que o prazo de avaliação de 20 dias expirou sem avaliação da chefia,  
**Quando** o relatório é gerado,  
**Então** o plano aparece em "Avaliações pendentes (chefia)".

---

#### TC-M07-008 — Relatório: registros não enviados à API PGD Central `[I]` P2

**Dado** que há participantes/planos com `api_sincronizado_em = null` ou desatualizados,  
**Quando** o relatório é gerado,  
**Então** são listados em "Pendentes de envio à API Central".

---

#### TC-M07-009 — Relatório exportável em CSV `[E]` P3

**Dado** que o admin seleciona qualquer relatório de conformidade,  
**Quando** aciona "Exportar CSV",  
**Então** o arquivo gerado contém os mesmos dados exibidos na tela, em formato CSV válido.

---

---

## TC-M08 — Notificações

### RF-029 — Sistema de Notificações

#### TC-M08-001 — Notificação imediata ao participante após avaliação `[I]` P1

**Dado** que a chefia registra qualquer avaliação (código 1–5),  
**Quando** a avaliação é persistida,  
**Então** e-mail + notificação no sistema são enviados ao participante com: código da avaliação, descrição, data, e (se código = 4 ou 5) prazo de 10 dias para recurso.

---

#### TC-M08-002 — Notificação à chefia quando recurso é submetido `[I]` P1

**Dado** que o participante submete recurso,  
**Quando** o recurso é registrado,  
**Então** e-mail + notificação são enviados à chefia com: identificação do participante, plano, data do recurso, e prazo de 10 dias para resposta.

---

#### TC-M08-003 — Alerta ao participante 3 dias antes do prazo de registro `[I]` P1

**Dado** que o prazo de registro de execução do participante é em 3 dias,  
**Quando** o worker de lembretes roda (diariamente),  
**Então** notificação é enviada ao participante indicando o prazo.

---

#### TC-M08-004 — Alerta à chefia 3 dias antes do prazo de avaliação `[I]` P1

**Dado** que o prazo de avaliação da chefia vence em 3 dias,  
**Quando** o worker de lembretes roda,  
**Então** notificação é enviada à chefia indicando o plano e o prazo.

---

#### TC-M08-005 — Notificação de convocação presencial imediata `[I]` P1

**Dado** que a chefia registra convocação presencial válida,  
**Quando** a convocação é persistida,  
**Então** notificação imediata é enviada pelo canal definido no TCR do participante.

---

#### TC-M08-006 — Notificação de desligamento com prazo de retorno `[I]` P1

**Dado** que o desligamento é registrado,  
**Quando** o evento é processado,  
**Então** e-mail + notificação são enviados ao participante com: hipótese de desligamento e data prevista de retorno ao controle de frequência.

---

#### TC-M08-007 — Suspensão/revogação notifica TODOS os participantes ativos `[I]` P1

**Dado** que o PGD de uma unidade tem 47 participantes ativos,  
**Quando** o admin registra a suspensão,  
**Então** notificações são enviadas a todos os 47 participantes.

---

#### TC-M08-008 — Notificação não enviada quando operação falha `[U]` P1

**Dado** que uma operação (ex.: avaliação) falha por erro de validação antes de persistir,  
**Quando** o erro é retornado ao chamador,  
**Então** nenhuma notificação é despachada.

---

---

## TC-M09 — Configuração e Multi-tenant

### RF-030 — Multi-Tenant

#### TC-M09-001 — Dados isolados entre unidades autorizadoras distintas (TC-TX-004 especializado) `[I]` P1

**Dado** que o Órgão A e o Órgão B compartilham a mesma instalação,  
**Quando** o admin do Órgão A consulta planos de entregas,  
**Então** apenas planos do Órgão A (mesmo `origem_unidade` + `cod_unidade_autorizadora`) são retornados.

---

#### TC-M09-002 — Participante com mesma matrícula em órgãos diferentes é distinto `[I]` P1

**Dado** que dois órgãos distintos têm participantes com a mesma `matricula_siape`,  
**Quando** qualquer operação referencia um participante,  
**Então** a chave completa `(origem_unidade, cod_unidade_autorizadora, cod_unidade_lotacao, matricula_siape)` é usada para identificação única.

---

### RF-031 — Escalas Customizadas

#### TC-M09-003 — Escala customizada mapeada para escala padrão 1–5 `[U]` P1

**Dado** que a unidade configura escala `A=1, B=2, C=3, D=4, E=5`,  
**Quando** o avaliador registra avaliação "B" nessa escala,  
**Então** `avaliacao` armazenado internamente é `2` (Alto desempenho); `avaliacao_customizada = "B"` preservado.

---

#### TC-M09-004 — Envio à API Central usa apenas valor padrão `[U]` P1

**Dado** que o plano foi avaliado com valor customizado "B" (equivalente a 2),  
**Quando** o mapper gera o payload para a API Central,  
**Então** o campo `avaliacao` no payload é `2` (nunca "B").

---

#### TC-M09-005 — Escala customizada com mapeamento incompleto é rejeitada `[U]` P1

**Dado** que a unidade tenta configurar escala com `A=1, B=2, C=3` (omitindo 4 e 5),  
**Quando** a configuração é salva,  
**Então** retorna erro "A escala deve mapear todos os valores de 1 a 5 para garantir cobertura completa dos casos".

---

---

## TC-M10 — Gestão de Pessoas e RH

### RF-034 — Ações de Desenvolvimento em Serviço

#### TC-M10-001 — Ação de desenvolvimento registrada como contribuição tipo 2 `[I]` P1

**Dado** que a chefia elabora o plano de trabalho com uma contribuição do tipo 2 marcada como "ação de desenvolvimento em serviço",  
**Quando** o plano é pactuado,  
**Então** a contribuição é persistida com `tipo = 2`, `rotulo = "acao_desenvolvimento"`, `descricao`, `periodo` e `carga_horaria`.

---

#### TC-M10-002 — Ação de desenvolvimento incluída no payload da API Central `[I]` P1

**Dado** que o plano de trabalho contém contribuição de ação de desenvolvimento,  
**Quando** o mapper gera o payload,  
**Então** a contribuição está presente no `lista_contribuicoes` com `tipo = 2`.

---

### RF-035 — Adicionais Ocupacionais e Noturno

#### TC-M10-003 — Participante sujeito a adicional ocupacional exige plano mensal `[I]` P1

**Dado** que o participante está em modalidade presencial ou teletrabalho parcial e sujeito a adicional de insalubridade,  
**Quando** a chefia tenta criar plano de trabalho com duração de 90 dias,  
**Então** retorna erro "Participante sujeito a adicional ocupacional requer plano de trabalho com periodicidade mensal (IN52 Art.8º §2º)".

---

#### TC-M10-004 — Teletrabalho integral veda adicionais ocupacionais `[U]` P1

**Dado** que o participante está em teletrabalho integral (modalidade 3),  
**Quando** o sistema de RH tenta registrar adicional de insalubridade,  
**Então** retorna erro "Adicional de insalubridade/periculosidade vedado para teletrabalho integral (D11 Art.15)".

---

#### TC-M10-005 — Autorização de atividade noturna exige documentação completa `[I]` P1

**Dado** a mutation `registrarAutorizacaoAtividadeNoturna`,  
**Quando** qualquer dos campos obrigatórios está ausente: `justificativa`, `periodo_inicio`, `periodo_fim`, `horario_inicio`, `horario_fim`, `relacao_nominal_participantes`,  
**Então** retorna erro com o campo ausente.

---

#### TC-M10-006 — Autorização noturna gera documento para gestão de pessoas `[I]` P1

**Dado** que a chefia registra autorização de atividade noturna com todos os campos,  
**Quando** a autorização é salva,  
**Então** o sistema gera (ou disponibiliza para geração) o documento de encaminhamento à gestão de pessoas contendo: autorização, justificativa, período, horário, relação nominal.

---

### RF-036 — Registro de Frequência / Códigos PGD

#### TC-M10-007 — Listagem de participantes com código PGD por unidade e período `[I]` P2

**Dado** que existem 10 participantes ativos na Unidade X,  
**Quando** a chefia consulta a listagem de frequência para o período de fevereiro/2026,  
**Então** retorna os 10 participantes com o código de participação em PGD a ser lançado no sistema de frequência.

---

#### TC-M10-008 — Participantes com afastamentos destacados na listagem `[I]` P2

**Dado** que 3 dos 10 participantes têm licença ou afastamento registrado no plano de trabalho em fevereiro,  
**Quando** a listagem é gerada,  
**Então** os 3 participantes aparecem destacados com indicação do tipo de afastamento.

---

### RF-037 — Delegação de Competências da Chefia

#### TC-M10-009 — Delegação válida concede acesso ao delegado `[I]` P1

**Dado** que a chefia da unidade registra delegação para a chefia imediata do participante, especificando competências e prazo,  
**Quando** o delegado tenta exercer as competências delegadas,  
**Então** o acesso é concedido.

---

#### TC-M10-010 — Elaboração do plano de entregas não pode ser delegada `[I]` P1

**Dado** que a chefia tenta registrar delegação incluindo a competência "elaborar plano de entregas",  
**Quando** a delegação é submetida,  
**Então** retorna erro "A competência de elaboração e monitoramento do plano de entregas não pode ser delegada (IN24 Art.25 §único)".

---

#### TC-M10-011 — Delegação registrada no log de auditoria `[I]` P1

**Dado** que uma delegação é criada ou revogada,  
**Quando** a operação é concluída,  
**Então** log de auditoria gerado com: `delegante_user_id`, `delegado_user_id`, `competencias`, `prazo`, `acao` (criação/revogação).

---

#### TC-M10-012 — Delegação expirada revoga acesso automaticamente `[I]` P1

**Dado** que o prazo de vigência da delegação venceu,  
**Quando** o delegado tenta exercer a competência delegada,  
**Então** retorna FORBIDDEN "Delegação expirada".

---

#### TC-M10-013 — Delegação pode ser revogada antecipadamente pelo delegante `[I]` P1

**Dado** que existe delegação vigente,  
**Quando** a chefia registra revogação antecipada,  
**Então** o acesso do delegado às competências delegadas é imediatamente encerrado.

---

---

## Cobertura e Rastreabilidade

### Mapa de cobertura RF → TCs

| RF | TCs | Status |
|----|-----|--------|
| RF-001 | TC-M01-001 a TC-M01-005 | ✅ `test_institucional.py` |
| RF-002 | TC-M01-006 a TC-M01-009 | ✅ `test_institucional.py` |
| RF-003 | TC-M01-010 a TC-M01-012 | ✅ `test_institucional.py` |
| RF-004 | TC-M01-013 a TC-M01-015 | ⏳ TC-013 ✅ `test_public.py`; 014-015 ❌ |
| RF-005 | TC-M02-001 a TC-M02-011 | ✅ `test_participante.py` |
| RF-006 | TC-M02-012 a TC-M02-014 | ✅ `test_selecao.py` |
| RF-007 | TC-M02-015 a TC-M02-020 | ✅ `test_participante.py` |
| RF-008 | TC-M02-021 a TC-M02-023 | ✅ `test_participante.py` |
| RF-009 | TC-M02-024 a TC-M02-025 | ✅ `test_participante.py` |
| RF-010 | TC-M03-001 a TC-M03-008 | ✅ `test_plano_entregas.py` |
| RF-011 | TC-M03-009 a TC-M03-011 | ✅ `test_aprovacao_pe.py` |
| RF-012 | TC-M03-012 a TC-M03-014 | ✅ `test_plano_entregas.py` |
| RF-013 | TC-M03-015 a TC-M03-019 | ✅ `test_plano_entregas.py` |
| RF-014 | TC-M04-001 a TC-M04-013 | ✅ `test_plano_trabalho.py` |
| RF-015 | TC-M04-014 a TC-M04-018 | ✅ `test_plano_trabalho.py` |
| RF-016 | TC-M04-019 a TC-M04-020 | ✅ `test_plano_trabalho.py` |
| RF-017 | TC-M04-021 a TC-M04-026 | ✅ `test_avaliacao.py` |
| RF-018 | TC-M04-027 a TC-M04-032 | ✅ `test_avaliacao.py` |
| RF-019 | TC-M04-033 a TC-M04-034 | ✅ `test_compensacao_banco.py` |
| RF-020 | TC-M04-035 a TC-M04-036 | ✅ `test_compensacao_banco.py` |
| RF-021 | TC-M05-001 a TC-M05-005 | ✅ `test_sync.py` · `test_conformidade.py` |
| RF-022 | TC-M05-006 a TC-M05-007 | ✅ `test_sync.py` |
| RF-023 | TC-M05-008 a TC-M05-009 | ✅ `test_sync.py` |
| RF-024 | TC-M05-010 a TC-M05-012 | ⏳ TC-011/012 ✅ `test_conformidade.py`; TC-010 ❌ |
| RF-025 | TC-M06-001 a TC-M06-007 | ⏳ TC-001/002 ✅ `test_auth_router.py`; 003-005 ❌ |
| RF-026 | TC-M06-008 a TC-M06-013 | ✅ `test_permissions.py` · `test_multitenant.py` |
| RF-027 | TC-M07-001 a TC-M07-004 | ✅ `test_auditoria.py` |
| RF-028 | TC-M07-005 a TC-M07-009 | ⏳ 005/006/007/008 ✅ `test_relatorios.py`; TC-009 ❌ |
| RF-029 | TC-M08-001 a TC-M08-008 | ✅ `test_notificacoes.py` |
| RF-030 | TC-M09-001 a TC-M09-002 | ✅ `test_multitenant.py` (TC-MT-001 a TC-MT-007) |
| RF-031 | TC-M09-003 a TC-M09-005 | ✅ `test_gestao_rh.py` |
| RF-032 | TC-M02-026 a TC-M02-027 | ✅ `test_gestao_rh.py` |
| RF-033 | TC-M02-028 a TC-M02-029 | ✅ `test_gestao_rh.py` |
| RF-034 | TC-M10-001 a TC-M10-002 | ⏳ TC-001 ✅ `test_gestao_rh.py`; TC-002 ❌ |
| RF-035 | TC-M10-003 a TC-M10-006 | ⏳ TC-003/004 ✅ `test_gestao_rh.py`; TC-005/006 ❌ |
| RF-036 | TC-M10-007 a TC-M10-008 | ❌ Pendente |
| RF-037 | TC-M10-009 a TC-M10-013 | ❌ Pendente |
| **Transversais** | TC-TX-001 a TC-TX-004 | ⏳ TX-001/002/003 ✅; TX-004 ✅ `test_multitenant.py` |
| **Multi-tenant** | TC-MT-001 a TC-MT-007 | ✅ `test_multitenant.py` |
| **Sprint 2.2** | TC-S22-001 a TC-S22-008 | ✅ `test_conformidade.py` |

**Total de casos de teste:** 113 (+ 4 transversais + 7 TC-MT + 8 TC-S22 = **132**)

---

### Prioridade de implementação TDD

Os casos `P1` devem existir como testes falhando antes de qualquer linha de código de produção. A sequência natural de escrita dos testes segue as dependências do domínio:

```
1. TC-TX (transversais — auth, audit, RBAC)
2. TC-M06 (autenticação e papéis)
3. TC-M01 (gestão institucional — base de tudo)
4. TC-M02 (participantes e TCR)
5. TC-M03 (plano de entregas)
6. TC-M04 (plano de trabalho e avaliação)
7. TC-M05 (integração API Central)
8. TC-M07 (auditoria e relatórios)
9. TC-M08 (notificações)
10. TC-M09 (configuração)
11. TC-M10 (gestão de pessoas)
```

---

## TC-JU — Jornadas de Usuário (E2E)

Testes de jornada cobrem fluxos completos do ponto de vista de um ator específico. Cruzam múltiplos módulos, usam banco de dados real e verificam estado persistido + notificações + audit log como efeitos colaterais de cada etapa. Cada jornada define o **fixture de estado** que a inicia e verifica o **estado final** do sistema após todos os passos.

> Cada jornada corresponde a uma fixture de banco de dados pré-populada (factory) mais uma sequência de chamadas GraphQL/HTTP. Falha em qualquer passo interrompe a jornada e o teste falha com indicação da etapa.

---

### JU-01 — Configuração inicial do PGD por novo órgão `[E]` P1

**Ator:** Administrador  
**Pré-condição:** instalação limpa; nenhum dado de órgão existe.

**Passos:**
1. Admin faz login via Google OAuth → recebe cookie.
2. Admin registra `UnidadeAutorizadora` (Ministério X, SIAPE).
3. Admin registra ato de autorização → `pgd_autorizado = true`.
4. Admin registra `UnidadeInstituidora` (Secretaria Y) vinculada ao Ministério X, com: modalidades autorizadas (presencial + TT parcial + TT integral), percentuais de vagas, prazo mínimo de convocação = 5 dias, conteúdo mínimo do TCR.
5. Admin registra `UnidadeExecucao` (Coordenação Z), atribui `chefia_user_id` e `nivel_superior_user_id`.
6. Admin cria usuários: chefia (papel `chefe_imediato`), nível superior (papel `gestor_unidade`), gestor RH (papel `gestor_unidade`).

**Estado final esperado:**
- `UnidadeAutorizadora.pgd_autorizado = true`.
- `UnidadeInstituidora.status = em_vigor`.
- `UnidadeExecucao` com FK para instituidora.
- 3 usuários criados com papéis corretos.
- 6 registros em `AuditLog` (um por operação de escrita).

---

### JU-02 — Onboarding de participante do zero até TCR ativo `[E]` P1

**Ator:** Gestor RH → Chefia → Participante  
**Pré-condição:** estado final de JU-01 (órgão configurado).

**Passos:**
1. Gestor RH cadastra participante (CPF válido, matrícula 7 dígitos, modalidade = TT integral, `cumpriu_estagio_probatorio = true`).
2. Sistema valida CPF, matrícula e elegibilidade → participante criado com `situacao = 1`.
3. Chefia abre TCR para o participante preenchendo todos os campos obrigatórios.
4. Chefia confirma assinatura → `data_assinatura_chefia` preenchida.
5. Participante confirma assinatura → `data_assinatura_participante` preenchida; `TCR.status = ativo`.

**Estado final esperado:**
- `Participante.situacao = 1` com FK para `UnidadeExecucao`.
- `TCR.status = ativo` com datas de assinatura de ambas as partes.
- Participante disponível para plano de trabalho (`tcr_ativo = true`).
- 2 registros em `AuditLog` (criação participante + criação TCR).

---

### JU-03 — Ciclo completo de um período: da elaboração do plano à avaliação `[E]` P1

**Ator:** Chefia → Nível Superior → Participante → Chefia  
**Pré-condição:** estado final de JU-02 (1 participante com TCR ativo); unidade de execução configurada.

**Passos:**
1. Chefia elabora `PlanoEntregas` com 3 entregas, período de 90 dias → `status = 2` (Aprovado).
2. Nível superior aprova o plano → `status = 2`, `aprovado_por_user_id` preenchido.
3. Chefia inicia execução → `status = 3` (Em Execução).
4. Chefia elabora `PlanoTrabalho` para o participante, com 2 contribuições (tipo 1 = 70%, tipo 2 = 30%, soma = 100%).
5. Participante confirma o plano → `status = 2` (Aprovado).
6. Chefia inicia execução do plano de trabalho → `status = 3`.
7. Participante registra execução do 1º mês (até o 10º dia do mês seguinte).
8. Chefia avalia o 1º período com nota 3 (Adequado) → participante notificado.
9. Participante registra execução do 2º mês.
10. Chefia avalia o 2º período com nota 3 → participante notificado.
11. Participante registra execução do 3º mês.
12. Chefia avalia o 3º período com nota 3 → participante notificado.
13. Chefia transiciona plano de trabalho para Concluído (4).
14. Chefia transiciona plano de entregas para Concluído (4).
15. Nível superior avalia plano de entregas com nota 3 → `status = 5` (Avaliado).

**Estado final esperado:**
- `PlanoEntregas.status = 5`, `avaliacao = 3`.
- `PlanoTrabalho.status = 4` (Concluído).
- 3 `AvaliacaoRegistrosExecucao` com `avaliacao = 3`.
- 3 notificações enviadas ao participante (uma por avaliação).
- `PlanoEntregas.api_sincronizado_em` preenchido após execução do worker de sync.
- `PlanoTrabalho.api_sincronizado_em` preenchido após execução do worker de sync.
- Trilha de auditoria completa: ≥ 12 registros em `AuditLog`.

---

### JU-04 — Ciclo com avaliação negativa, recurso e compensação `[E]` P1

**Ator:** Chefia → Participante → Chefia → Chefia (próximo período)  
**Pré-condição:** plano de trabalho Em Execução (3), 1 período de registro vencido.

**Passos:**
1. Participante registra execução do período.
2. Chefia avalia com nota 5 (Não executado) e justificativa → participante notificado com prazo de recurso de 10 dias.
3. Participante submete recurso dentro do prazo com justificativa.
4. Sistema notifica chefia com prazo de 10 dias para resposta.
5. Chefia não acata o recurso com fundamentação → participante notificado.
6. Sistema sinaliza: ações de melhoria obrigatórias no próximo TCR + compensação no próximo plano + possível desconto em folha.
7. Chefia conclui plano de trabalho.
8. Chefia pactuaria novo TCR: tenta sem `acoes_melhoria` → sistema rejeita.
9. Chefia pactuaria novo TCR com `acoes_melhoria` preenchido → aceito.
10. Chefia cria próximo plano de trabalho: sistema pré-preenche carga de compensação; soma de percentuais = 120% é aceita.

**Estado final esperado:**
- Recurso com `acatado = false` e `fundamentacao` persistidos.
- Novo TCR com `acoes_melhoria` e `carga_horaria_compensacao` preenchidos.
- Novo plano de trabalho com soma de contribuições > 100% aceita.
- Sinalizações de desconto em folha registradas para a gestão de pessoas.
- Log de auditoria com todas as etapas rastreadas.

---

### JU-05 — Seleção de participantes com excesso de candidatos `[E]` P1

**Ator:** Chefia  
**Pré-condição:** unidade com 2 vagas de teletrabalho integral; 5 candidatos registrados.

**Candidatos:**
- A: pessoa com deficiência.
- B: responsável por dependente com deficiência.
- C: mobilidade reduzida (sem prioridade adicional).
- D: sem prioridade especial.
- E: sem prioridade especial.

**Passos:**
1. Chefia registra os 5 candidatos com seus atributos de prioridade.
2. Chefia executa processo de seleção.
3. Sistema apresenta candidatos ordenados por prioridade: A (1º), B (2º), C (3º), D (4º), E (5º).
4. Chefia confirma seleção de A e B com critério técnico preenchido.
5. A e B recebem TCR; C, D, E ficam na fila ou descartados.

**Estado final esperado:**
- A e B com `situacao = 1` e TCR iniciado.
- C, D, E sem TCR ativo.
- Log de auditoria com critérios técnicos registrados.
- Percentual de vagas ocupadas atualizado para a unidade instituidora.

---

### JU-06 — Suspensão do PGD e retorno dos participantes `[E]` P1

**Ator:** Administrador  
**Pré-condição:** 10 participantes ativos, 5 com planos de trabalho Em Execução.

**Passos:**
1. Admin registra suspensão do PGD da `UnidadeInstituidora` com justificativa.
2. Sistema: `UnidadeInstituidora.status = suspenso`.
3. Sistema: 5 planos de trabalho em execução → `Cancelado (1)`.
4. Sistema: plano de entregas em execução → `Cancelado (1)`.
5. Sistema: 10 notificações de suspensão enviadas (uma por participante ativo).
6. Cada participante recebe prazo de 30 dias para retorno (ou 2 meses se no exterior).

**Estado final esperado:**
- `UnidadeInstituidora.status = suspenso`.
- 5 planos de trabalho com `status = 1`.
- 10 notificações enviadas.
- Log de auditoria: 1 entrada para a instituidora + 5 para cada plano cancelado.

**Variante — reativação:**
7. Admin registra reativação com novo ato de instituição.
8. `UnidadeInstituidora.status = em_vigor`.
9. Novos planos de trabalho e TCRs podem ser criados.

---

### JU-07 — Envio à API PGD Central com falha e reprocessamento `[E]` P2

**Ator:** Sistema (worker) → Administrador  
**Pré-condição:** plano de entregas com `status = 3` e `api_sincronizado_em = null`.

**Passos:**
1. Worker de sync executa e tenta enviar o plano à API Central.
2. API Central retorna HTTP 503 (1ª tentativa).
3. Worker agenda retentativa após 1 minuto → 503 novamente.
4. Worker agenda retentativa após 5 minutos → 503 novamente.
5. Worker agenda última retentativa após 30 minutos → 503 novamente.
6. Após 3 falhas: `RegistroEnvioAPI.status = erro_permanente`; alerta ao administrador.
7. Admin acessa painel de conformidade: plano aparece em "Erro de envio".
8. API Central volta ao ar. Admin aciona reprocessamento manual.
9. Worker envia com sucesso → `api_sincronizado_em = now()`.
10. Plano sai da lista de erros e aparece em "Enviados com sucesso".

**Estado final esperado:**
- `RegistroEnvioAPI` com histórico de 4 tentativas e resultado final = sucesso.
- `PlanoEntregas.api_sincronizado_em` preenchido.
- Admin recebeu 1 alerta de erro (não 4).

---

### JU-08 — Delegação de competências e exercício pelo delegado `[E]` P1

**Ator:** Chefia da unidade → Chefia imediata (delegado) → Participante  
**Pré-condição:** participante ativo com TCR e plano de trabalho em execução.

**Passos:**
1. Chefia da unidade registra delegação para chefia imediata: competências "avaliar períodos" e "registrar convocações"; prazo = 30 dias.
2. Chefia imediata (delegado) avalia período do participante com nota 2 → aceito.
3. Sistema registra a avaliação com `avaliador_user_id = chefia_imediata_id`.
4. Chefia da unidade tenta delegar a competência "elaborar plano de entregas" → sistema rejeita.
5. Após 31 dias: delegado tenta avaliar novo período → FORBIDDEN (delegação expirada).
6. Chefia revoga a delegação antes do prazo → acesso removido imediatamente.

**Estado final esperado:**
- Delegação registrada com prazo e competências.
- Avaliação feita pelo delegado rastreável no audit log.
- Tentativa de delegar "elaborar plano de entregas" registrada como rejeição.
- Delegação revogada: `status = revogada` com `data_revogacao`.

---

### JU-09 — Participante registra execução e recebe alertas de prazo `[E]` P1

**Ator:** Participante (visão do servidor no dia a dia)  
**Pré-condição:** plano de trabalho Em Execução, período de 60 dias, prazo de registro = 10 dias do mês seguinte.

**Passos:**
1. Worker de lembretes roda em D-3 do prazo → notificação de "prazo iminente" enviada ao participante.
2. Participante faz login, acessa seu plano, registra atividades do período (descrição dos trabalhos, ocorrências).
3. Registro salvo com `data_hora_registro` e vinculado ao plano.
4. Chefia recebe notificação de que registro foi submetido para avaliação.
5. Worker de lembretes roda em D-3 do prazo de avaliação (20 dias) → notificação enviada à chefia.
6. Chefia avalia com nota 3 → participante notificado.
7. Participante acessa o sistema, visualiza a avaliação recebida.

**Estado final esperado:**
- 2 notificações ao participante (alerta de prazo + resultado da avaliação).
- 1 notificação à chefia (alerta de prazo de avaliação).
- `AvaliacaoRegistrosExecucao` com `avaliacao = 3` e `data_avaliacao` preenchidos.

---

### JU-10 — Jornada multi-tenant: dois órgãos na mesma instalação `[E]` P1

**Ator:** Admin Órgão A + Admin Órgão B  
**Pré-condição:** instalação limpa.

**Passos:**
1. Admin A configura Órgão A (SIAPE, cod=10000): unidade instituidora, participante A1, plano de entregas A-PE1.
2. Admin B configura Órgão B (SIAPE, cod=20000): unidade instituidora, participante B1, plano de entregas B-PE1.
3. Admin A consulta todos os planos de entregas → retorna apenas A-PE1.
4. Admin A tenta consultar B-PE1 pelo ID → retorna "não encontrado" (não FORBIDDEN, para não vazar existência).
5. Admin B consulta todos os participantes → retorna apenas B1.
6. Worker de sync do Órgão A envia apenas dados do Órgão A à API Central.

**Estado final esperado:**
- Isolamento completo: nenhuma query retorna dados entre órgãos.
- Payloads de sync contêm apenas `(origem_unidade, cod_unidade_autorizadora)` do órgão correto.

---

### JU-11 — Escala customizada do início ao envio `[E]` P2

**Ator:** Admin → Nível Superior → Worker  
**Pré-condição:** unidade instituidora configurada.

**Passos:**
1. Admin configura escala customizada: `Excelente=1, Muito Bom=2, Bom=3, Regular=4, Insuficiente=5`.
2. Nível superior avalia plano de entregas com valor "Muito Bom" (equivale a 2).
3. `PlanoEntregas.avaliacao = 2`; `avaliacao_customizada = "Muito Bom"` preservados.
4. Worker de sync executa: payload enviado à API Central tem `avaliacao = 2` (nunca "Muito Bom").
5. API Central aceita → `api_sincronizado_em` preenchido.

**Estado final esperado:**
- Valor customizado armazenado e exibível na UI.
- Valor padrão enviado à API Central.
- Mapeamento auditável (old_values/new_values preservam ambos os valores).

---

---

## TC-MT — Multi-tenant (isolamento por unidade)

> Todos os testes em `tests/test_multitenant.py`. Implementam TC-TX-004 e TC-M09-001/002.

### TC-MT-001 — Gestor vê apenas participantes da própria unidade `[I]` P1

**Dado** que existem participantes em duas unidades autorizadoras distintas,  
**Quando** um gestor com `cod_unidade_autorizadora=100` consulta `listarParticipantes`,  
**Então** retorna apenas os participantes da unidade 100.

---

### TC-MT-002 — Admin vê participantes de todas as unidades `[I]` P1

**Dado** que existem participantes em duas unidades,  
**Quando** um usuário com papel `admin` consulta `listarParticipantes`,  
**Então** retorna participantes de ambas as unidades.

---

### TC-MT-003 — Gestor não acessa participante de outra unidade por ID `[I]` P1

**Dado** que o participante X pertence à unidade 202,  
**Quando** um gestor da unidade 102 consulta `participante(id: X)`,  
**Então** retorna `null` (sem FORBIDDEN — não vaza a existência).

---

### TC-MT-004 — Gestor acessa participante da própria unidade por ID `[I]` P1

**Dado** que o participante X pertence à unidade 103,  
**Quando** um gestor da unidade 103 consulta `participante(id: X)`,  
**Então** retorna o participante com os dados corretos.

---

### TC-MT-005 — Gestor vê apenas planos de entregas da própria unidade `[I]` P1

Análogo ao TC-MT-001 para `listarPlanosEntregas`.

---

### TC-MT-006 — Admin vê planos de entregas de todas as unidades `[I]` P1

Análogo ao TC-MT-002 para `listarPlanosEntregas`.

---

### TC-MT-007 — Chefe imediato também fica limitado à própria unidade `[I]` P1

**Dado** que existe participante em unidade 206,  
**Quando** um usuário com papel `chefe_imediato` da unidade 106 consulta `listarParticipantes`,  
**Então** retorna apenas os participantes da unidade 106.

---

## TC-S22 — Sprint 2.2: RegistroEnvioAPI e Conformidade

> Todos os testes em `tests/test_conformidade.py`. Cobrem RF-021/022/023/024.

### TC-S22-001 — Envio com sucesso cria RegistroEnvioAPI com sucesso=True `[I]` P1

**Dado** que existe participante com `api_sincronizado_em = null`,  
**Quando** o worker de sync executa com sucesso,  
**Então** é criado um `RegistroEnvioAPI` com `sucesso=True`, `tentativa=1`, `http_status=null`.

---

### TC-S22-002 — Falha cria RegistroEnvioAPI com sucesso=False e mensagem `[I]` P1

**Dado** que o envio lança exceção,  
**Quando** o worker executa,  
**Então** é criado `RegistroEnvioAPI` com `sucesso=False`, `tentativa=1`, `erro_mensagem` preenchida.

---

### TC-S22-003 — Entidade com falha recente não é retentada (backoff) `[I]` P1

**Dado** que existe registro de falha com `tentativa=1` feito agora mesmo (< 60s),  
**Quando** o worker executa,  
**Então** a entidade **não** é enviada novamente (backoff não expirou).

---

### TC-S22-004 — Entidade com falha antiga É retentada `[I]` P1

**Dado** que existe registro de falha com `tentativa=1` feito há mais de `RETRY_DELAYS[0] + 10s`,  
**Quando** o worker executa,  
**Então** a entidade é enviada novamente.

---

### TC-S22-005 — Entidade que esgotou tentativas (MAX_TENTATIVAS) é ignorada `[I]` P1

**Dado** que existe registro com `tentativa = MAX_TENTATIVAS` (= 3) e backoff expirado,  
**Quando** o worker executa,  
**Então** a entidade **não** é enviada (esgotou — requer `reprocessarEnvio` manual).

---

### TC-S22-006 — Retry incrementa tentativa corretamente `[I]` P1

**Dado** que existe registro com `tentativa=1` e backoff expirado,  
**Quando** o worker tenta e falha novamente,  
**Então** o novo `RegistroEnvioAPI` tem `tentativa=2`.

---

### TC-S22-007 — Painel de conformidade retorna contagens corretas `[E]` P2

**Dado** que existem 3 participantes: 1 enviado, 1 pendente sem tentativa, 1 com falha,  
**Quando** o admin consulta `painelConformidade`,  
**Então** retorna `{ total: 3, enviados: 1, pendentes: 2, comErro: 1 }` para participantes.

---

### TC-S22-008 — reprocessarEnvio remove registros de falha `[I]` P2

**Dado** que um participante esgotou as `MAX_TENTATIVAS` tentativas,  
**Quando** o admin executa `reprocessarEnvio(tipoEntidade: "participante", entidadeId: X)`,  
**Então** os registros de falha são removidos e o participante fica elegível para retry imediato.

---

## Resumo executivo dos casos de teste

| Categoria | Qtd | Prioridade P1 | Prioridade P2/P3 | Status |
|-----------|-----|--------------|-----------------|--------|
| Transversais (TX) | 4 | 4 | 0 | ⏳ 3/4 ✅ |
| M01 — Gestão Institucional | 15 | 12 | 3 | ⏳ 13/15 ✅ |
| M02 — Gestão de Participantes | 29 | 26 | 3 | ✅ 29/29 |
| M03 — Plano de Entregas | 19 | 17 | 2 | ✅ 19/19 |
| M04 — Plano de Trabalho | 36 | 34 | 2 | ✅ 36/36 |
| M05 — Integração API Central | 12 | 8 | 4 | ⏳ 9/12 ✅ |
| M06 — Autenticação / RBAC | 13 | 13 | 0 | ⏳ 8/13 ✅ |
| M07 — Auditoria / Relatórios | 9 | 7 | 2 | ⏳ 8/9 ✅ |
| M08 — Notificações | 8 | 8 | 0 | ✅ 8/8 |
| M09 — Configuração | 5 | 3 | 2 | ✅ 5/5 |
| M10 — Gestão de Pessoas / RH | 13 | 11 | 2 | ⏳ 4/13 ✅ |
| MT — Multi-tenant | 7 | 7 | 0 | ✅ 7/7 |
| S22 — Conformidade/Retry | 8 | 6 | 2 | ✅ 8/8 |
| **JU — Jornadas de Usuário** | **11** | **9** | **2** | ❌ 0/11 |
| **TOTAL** | **189** | **168** | **21** | **⏳ 157/189** |
