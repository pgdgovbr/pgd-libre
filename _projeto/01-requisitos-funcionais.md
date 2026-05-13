# Requisitos Funcionais — PGD Libre (Plataforma na Ponta)

**Versão:** 0.4 — 2026-05-13  
**Contexto normativo:** Decreto nº 11.072/2022 · IN Conjunta SEGES-SGPRT/MGI nº 24/2023 · IN Conjunta SGP-SRT-SEGES/MGI nº 52/2023  
**Contrato de dados:** API PGD Central (api-pgd, referência de código aberto do MGI)

---

## Convenções

| Rótulo | Significado |
|--------|-------------|
| `[D11]` | Decreto 11.072/2022 |
| `[IN24]` | IN Conjunta SEGES-SGPRT/MGI nº 24/2023 |
| `[IN52]` | IN Conjunta SGP-SRT-SEGES/MGI nº 52/2023 |
| `[API]` | Contrato da API PGD Central |
| **Obrigatório** | Requisito imposto diretamente pela legislação |
| **Derivado** | Requisito necessário para suportar o obrigatório |

Critérios de aceitação seguem a notação **Dado / Quando / Então**.

---

## Módulo 1 — Gestão Institucional

### RF-001 — Registro do Ato de Autorização

**Origem:** `[D11]` Art. 3º / `[IN24]` Art. 5º  
**Prioridade:** Obrigatório  
**Papel:** Gestor de RH / Administrador do sistema

O sistema deve permitir registrar e consultar o ato de autorização para instituição do PGD no órgão, contendo:

- Autoridade autorizadora (Ministro de Estado, dirigente máximo ou autoridade máxima)
- Data de publicação
- Número e referência do ato
- Status: Ativo / Suspenso / Revogado

**Critério de aceitação:**  
Dado que o administrador preenche todos os campos obrigatórios do ato de autorização,  
Quando confirma o registro,  
Então o sistema persiste o ato e disponibiliza para consulta; o sistema registra em log de auditoria o evento com usuário, data e hora.

---

### RF-002 — Registro do Ato de Instituição do PGD

**Origem:** `[D11]` Art. 4º / `[IN24]` Art. 6º  
**Prioridade:** Obrigatório  
**Papel:** Gestor de RH / Administrador

O sistema deve permitir registrar o ato de instituição do PGD por unidade instituidora (nível mínimo de Secretaria ou equivalente), contendo:

- Unidade instituidora (código SIAPE/SIORG)
- Tipos de atividades permitidas no PGD
- Modalidades e regimes de execução autorizados
- Quantitativo de vagas por modalidade (expresso em % em relação ao total de agentes públicos da unidade instituidora)
- Eventual nível de produtividade adicional exigido para o teletrabalho `[D11]` Art. 4º inciso IV
- Vedações à participação, se houver
- Conteúdo mínimo do TCR
- Prazo mínimo de antecedência para convocações presenciais
- Procedimento de registro de comparecimento (para auxílio transporte, se aplicável) `[IN24]` Art. 6º §5º
- Status: Em vigor / Suspenso / Revogado

**Critério de aceitação:**  
Dado que o ato de autorização (RF-001) está ativo,  
Quando o administrador registra o ato de instituição com todos os campos obrigatórios,  
Então o sistema vincula o ato à unidade instituidora, registra a data de vigência e disponibiliza para consulta e para geração dos TCRs associados.

---

### RF-003 — Suspensão e Revogação do PGD

**Origem:** `[D11]` Art. 3º §3º / `[IN24]` Art. 6º §4º  
**Prioridade:** Obrigatório  
**Papel:** Administrador

O sistema deve permitir suspender ou revogar o PGD de uma unidade instituidora, exigindo fundamentação. Ao suspender ou revogar:

- Os participantes em teletrabalho são notificados e têm prazo de 30 dias para retorno presencial (redutível mediante justificativa)
- Os participantes no exterior têm prazo de 2 meses
- Planos de trabalho ativos passam ao status "Cancelado"

**Critério de aceitação:**  
Dado que existe um PGD ativo para uma unidade,  
Quando o administrador registra a suspensão/revogação com justificativa,  
Então o sistema atualiza o status do PGD, notifica os participantes afetados (ver RF-029) e encerra o ciclo pendente.

---

### RF-004 — Publicidade do Ato de Instituição e dos Resultados

**Origem:** `[D11]` Art. 4º §3º / `[IN24]` Art. 23 incisos I e V  
**Prioridade:** Obrigatório  
**Papel:** Sistema (automático) / Administrador

O sistema deve:

1. Gerar e expor para download o ato de instituição do PGD de cada unidade instituidora, para divulgação no sítio eletrônico oficial do órgão.
2. Expor os resultados do PGD (consolidado por unidade) de forma pública, com atualização ao menos anual.
3. Registrar o endereço do sítio eletrônico onde o ato e os resultados estão publicados, para manutenção junto ao CPGD conforme `[IN24]` Art. 23 inciso V.

A autoridade máxima é responsável pela divulgação no sítio eletrônico oficial.

**Critério de aceitação:**  
Dado que o ato de instituição foi registrado (RF-002) ou o ciclo do PGD de um período foi avaliado,  
Quando o administrador acessa a funcionalidade de publicidade,  
Então o sistema disponibiliza: (a) o documento do ato de instituição para download/publicação e (b) um endpoint público (sem autenticação) com os resultados consolidados por unidade de execução, atualizados ao menos anualmente.

---

## Módulo 2 — Gestão de Participantes

### RF-005 — Cadastro de Participante

**Origem:** `[D11]` Art. 2º §1º / `[IN24]` Art. 13 / `[API]` `/organizacao/.../participante/`  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução / Gestão de RH

O sistema deve permitir cadastrar agentes públicos como participantes do PGD, registrando:

- CPF (11 dígitos, validado)
- Matrícula SIAPE (7 dígitos)
- Unidade de lotação (código SIAPE/SIORG)
- Unidade autorizadora
- Unidade instituidora
- Modalidade e regime de execução:
  - 1 = Presencial
  - 2 = Teletrabalho parcial
  - 3 = Teletrabalho integral
  - 4 = Teletrabalho com residência no exterior (art. 12, inciso VIII do D11)
  - 5 = Teletrabalho com residência no exterior (art. 12, §7º do D11)
- Situação: Ativo (1) / Inativo (0)
- Data de assinatura do TCR

Tipos de agente público suportados: servidor efetivo, servidor comissionado, empregado público, contratado temporário, estagiário.

**Regras de validação:**
- Só pode ingressar em teletrabalho quem tiver cumprido 1 ano de estágio probatório `[IN24]` Art. 10 §2º
- Participante em presencial ou sujeito a controle de frequência em outro órgão só pode aderir ao teletrabalho 6 meses após movimentação `[IN24]` Art. 10 §3º
- Teletrabalho no exterior: requisitos do art. 12 do D11; limite de 2% do total de participantes em PGD do órgão para a hipótese do §7º `[IN24]` Art. 12 §único
- Empregados de empresas públicas ou sociedades de economia mista em exercício na administração federal precisam de autorização da entidade de origem para alterar para teletrabalho `[D11]` Art. 9º §4º
- Para estagiários, a adesão ao teletrabalho se dá por acordo entre instituição de ensino, parte concedente e estagiário (e seu representante legal, quando menor), devendo constar do Termo de Compromisso de Estágio (TCE) `[D11]` Art. 9º §§2º–3º / `[IN52]` Art. 20

**Critério de aceitação:**  
Dado que o participante atende aos critérios de elegibilidade,  
Quando a chefia registra o participante com todos os dados obrigatórios e o TCR é assinado,  
Então o sistema cria o registro do participante com status Ativo e disponibiliza para inclusão em planos de trabalho.

---

### RF-006 — Seleção de Participantes com Critérios de Prioridade

**Origem:** `[D11]` Art. 7º / `[IN24]` Arts. 13–14  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução

Quando o número de interessados superar o de vagas disponíveis, o sistema deve suportar o processo de seleção com prioridade para:

1. Pessoas com deficiência ou responsáveis por dependentes nessa condição
2. Pessoas com mobilidade reduzida (Lei 10.098/2000)
3. Pessoas com horário especial (art. 98 §§2º e 3º da Lei 8.112/1990)
4. Outros critérios definidos pela unidade instituidora

Em qualquer caso, a seleção deve ocorrer de forma impessoal, com base nas atividades a serem desempenhadas e na experiência dos interessados `[D11]` Art. 7º. A autoridade instituidora pode definir a ordem de prioridade dos critérios e deve estabelecer e divulgar os critérios técnicos de adesão `[D11]` Art. 7º §2º.

**Critério de aceitação:**  
Dado que há mais interessados do que vagas,  
Quando a chefia executa o processo de seleção,  
Então o sistema ordena os candidatos pelas prioridades configuradas, registra os critérios técnicos utilizados e permite à chefia confirmar ou ajustar a seleção, registrando a justificativa em log de auditoria.

---

### RF-007 — Pactuação do TCR

**Origem:** `[D11]` Art. 11 / `[IN24]` Art. 15 / `[IN52]` Art. 3º  
**Prioridade:** Obrigatório  
**Papel:** Chefia e Participante

O sistema deve suportar a geração, assinatura e armazenamento do Termo de Ciência e Responsabilidade (TCR), contendo no mínimo:

- Responsabilidades do participante
- Modalidade e regime de execução
- Prazo de antecedência para convocação presencial
- Canais de comunicação da equipe
- Manifestação de ciência sobre: ergonomia/segurança, não configuração de direito adquirido, custeio da estrutura pelo participante
- Ações de melhoria (quando plano anterior avaliado como inadequado por execução abaixo do esperado) `[IN52]` Art. 3º
- Prazo de compensação de carga horária, quando houver inexecução parcial ou total `[IN52]` Art. 4º §único
- Carga de banco de horas a compensar ou usufruir, se houver saldo na entrada no PGD `[IN52]` Art. 18 §1º

**Regra especial para estagiários:** o TCR e o plano de atividades do estagiário devem constar no Termo de Compromisso de Estágio (TCE); eventuais ajustes no TCR incorporam-se ao TCE por meio de aditivos `[IN52]` Arts. 20–21. O sistema deve suportar o registro do TCE como instrumento substituto do TCR para estagiários.

Alterações nas condições do TCR exigem a pactuação de novo termo.

**Critério de aceitação:**  
Dado que participante e chefia concordam com os termos,  
Quando ambos confirmam o TCR no sistema (assinatura digital),  
Então o sistema registra o TCR com data de assinatura, vincula ao participante e impede que planos de trabalho sejam criados sem TCR ativo.

---

### RF-008 — Desligamento de Participante

**Origem:** `[IN24]` Art. 27  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução / Participante

O sistema deve registrar o desligamento do participante nas hipóteses:

1. A pedido (qualquer momento, exceto PGD obrigatório)
2. No interesse da administração (com justificativa)
3. Por alteração da unidade de exercício
4. Por suspensão ou revogação do PGD

Prazos de retorno ao controle de frequência:
- A pedido: prazo definido pelo órgão
- Demais hipóteses: 30 dias (ou 2 meses para participantes no exterior)

O participante mantém execução do plano de trabalho até o retorno efetivo.

**Critério de aceitação:**  
Dado que a chefia registra o desligamento com hipótese e justificativa,  
Quando o desligamento é confirmado,  
Então o sistema atualiza o status do participante para Inativo, registra a data prevista de retorno e notifica o participante.

---

### RF-009 — Convocação Presencial

**Origem:** `[D11]` Art. 9º inciso V / `[IN24]` Art. 11  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução

O sistema deve permitir registrar convocações presenciais para participantes em teletrabalho, contendo:
- Canal de comunicação (conforme TCR)
- Horário e local
- Período de atuação presencial
- Observância do prazo mínimo definido no TCR

**Critério de aceitação:**  
Dado que o participante está em teletrabalho,  
Quando a chefia registra uma convocação com antecedência igual ou superior ao mínimo definido no TCR,  
Então o sistema notifica o participante pelo canal definido no TCR e registra o evento.

---

### RF-032 — Retirada de Equipamentos pelo Participante em Teletrabalho

**Origem:** `[IN24]` Art. 16  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução / Administrador

Quando o órgão autorizar a retirada de equipamentos por participantes em teletrabalho integral, o sistema deve:

- Registrar a autorização de retirada vinculada ao participante e ao TCR
- Gerar ou registrar o Termo de Guarda e Responsabilidade firmado entre o participante e o órgão

A retirada não pode gerar aumento de despesa para a administração (inclusive seguros ou transporte de bens) `[IN24]` Art. 16 §1º.

**Critério de aceitação:**  
Dado que o participante está em teletrabalho integral e o órgão autoriza a retirada,  
Quando a chefia registra a autorização e o Termo de Guarda e Responsabilidade é firmado,  
Então o sistema vincula o registro ao TCR do participante e disponibiliza o termo para consulta e auditoria.

---

### RF-033 — Acumulação de Cargos, Empregos e Funções Públicas

**Origem:** `[IN52]` Art. 19  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução / Participante

Nas hipóteses em que a Constituição admite acumulação de cargos públicos, o participante deve declarar, no ato de pactuação do plano de trabalho, a ausência de prejuízo:

- No cumprimento integral do plano de trabalho
- Na disponibilidade para comparecer a local determinado pela administração
- Na disponibilidade para manter contato com a chefia e terceiros
- Na disponibilidade para realizar atividades síncronas

**Critério de aceitação:**  
Dado que o participante acumula cargos públicos,  
Quando o plano de trabalho é pactuado,  
Então o sistema exige declaração de ausência de prejuízo para os itens acima; a declaração é registrada e rastreável.

---

## Módulo 3 — Plano de Entregas da Unidade

### RF-010 — Elaboração do Plano de Entregas

**Origem:** `[IN24]` Art. 18 / `[API]` `plano_entregas`  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução

O sistema deve permitir a elaboração do plano de entregas da unidade, contendo:

- Unidade executora (código SIAPE/SIORG)
- Unidade instituidora
- Unidade autorizadora
- Identificador único do plano (gerado pelo sistema)
- Data de início e de término (duração máxima de 1 ano)
- Lista de entregas, cada uma com:
  - Nome/título da entrega
  - Meta (quantidade e tipo: `unidade` ou `percentual`)
  - Data prevista da entrega
  - Nome da unidade demandante
  - Nome da unidade destinatária
- Status inicial: Aprovado (2)

**Regras:**
- Não podem existir dois planos de entregas ativos (status 3, 4 ou 5) para a mesma unidade executora em período sobreposto `[API]`
- Duração máxima de 1 ano `[IN24]` Art. 18 §1º / `[API]`
- O plano deve ter ao menos uma entrega (exceto se status = Cancelado) `[API]`
- Entregas dentro do mesmo plano devem ter identificadores únicos `[API]`

**Critério de aceitação:**  
Dado que a chefia preenche o plano com pelo menos uma entrega,  
Quando submete para aprovação,  
Então o sistema valida as datas (máximo 1 ano), verifica sobreposição de períodos para a mesma unidade executora e cria o plano com status Aprovado (2).

---

### RF-011 — Aprovação do Plano de Entregas pelo Nível Hierárquico Superior

**Origem:** `[IN24]` Art. 18 §1º  
**Prioridade:** Obrigatório  
**Papel:** Nível hierárquico superior à chefia da unidade de execução

O sistema deve suportar o fluxo de aprovação do plano de entregas pelo nível hierárquico superior, incluindo:
- Aprovação com ou sem ajustes
- Comunicação sobre ajustes à chefia

Exceção: unidades instituidoras não precisam de aprovação hierárquica superior.

**Critério de aceitação:**  
Dado que o plano de entregas foi submetido,  
Quando o nível superior aprova,  
Então o sistema atualiza o status para Aprovado (2) e notifica a chefia; se houver ajustes, os planos de trabalho afetados são sinalizados para repactuação.

---

### RF-012 — Execução e Monitoramento do Plano de Entregas

**Origem:** `[IN24]` Art. 17 / `[API]` status=3  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução

O sistema deve permitir transicionar o plano de entregas para o status Em Execução (3) e suportar ajustes durante a execução. Ajustes devem ser comunicados ao nível hierárquico superior e podem desencadear repactuação dos planos de trabalho afetados.

**Critério de aceitação:**  
Dado que o plano está Aprovado,  
Quando a chefia inicia a execução,  
Então o status muda para Em Execução; ajustes nas entregas ficam registrados com data e justificativa.

---

### RF-013 — Avaliação do Plano de Entregas

**Origem:** `[IN24]` Art. 22 / `[API]` status=5, avaliacao=1–5  
**Prioridade:** Obrigatório  
**Papel:** Nível hierárquico superior à chefia da unidade de execução

Em até 30 dias após o término do plano, o nível superior deve avaliar o cumprimento do plano de entregas na escala:

| Código | Descrição |
|--------|-----------|
| 1 | Excepcional — desempenho muito acima do esperado |
| 2 | Alto desempenho — acima do esperado |
| 3 | Adequado — dentro do esperado |
| 4 | Inadequado — abaixo do esperado |
| 5 | Não executado |

A avaliação deve considerar: qualidade das entregas, alcance das metas, cumprimento de prazos, justificativas de descumprimento.

Avaliação não se aplica a unidades instituidoras.

**Critério de aceitação:**  
Dado que o plano de entregas está Concluído (4),  
Quando o nível superior registra a avaliação com nota e data,  
Então o status muda para Avaliado (5) e os dados ficam disponíveis para submissão à API PGD Central.

---

## Módulo 4 — Plano de Trabalho do Participante

### RF-014 — Elaboração e Pactuação do Plano de Trabalho

**Origem:** `[D11]` Art. 11 / `[IN24]` Art. 19 / `[API]` `plano_trabalho`  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução e Participante

O sistema deve permitir elaborar e pactuar o plano de trabalho do participante, contendo:

- Identificador único do plano
- Participante (CPF + matrícula SIAPE)
- Unidade executora, unidade de lotação, unidade autorizadora
- Data de início e de término
- Carga horária disponível no período (excluindo férias, licenças, afastamentos)
- Contribuições planejadas, cada uma com:
  - Tipo:
    - 1 = Vinculada a entrega da própria unidade (requer `id_plano_entregas` + `id_entrega`)
    - 2 = Não vinculada (suporte administrativo, gestão de equipe)
    - 3 = Vinculada a entrega de outra unidade/órgão
  - Percentual da carga horária (0–100)
  - Referência ao plano de entregas e entrega (quando tipo = 1 ou 3)
- Critérios de avaliação que serão utilizados pela chefia
- Status inicial: Aprovado (2)

**Regras:**
- Soma dos percentuais de contribuição = 100% da carga horária disponível (pode superar 100% apenas em caso de compensação de horas `[IN52]` Arts. 4–5; pode ser inferior a 100% em caso de usufruto de saldo de banco de horas `[IN52]` Art. 18 §2º)
- Participante com TCR ativo é pré-condição
- Não podem existir dois planos ativos (status 3 ou 4) para o mesmo participante em período sobreposto `[API]`
- Duração máxima de 1 ano `[API]`
- `data_inicio` do plano de trabalho deve ser igual ou posterior à `data_inicio` do plano de entregas vinculado `[API]`
- A lista de contribuições não pode estar vazia (exceto se status = Cancelado) `[API]`
- Contribuição tipo 3 (vinculada a outra unidade) não configura mudança de exercício; trabalhos realizados devem ser reportados à chefia `[IN24]` Art. 19 §2º
- Composição de times volantes é suportada via tipo 3 `[IN24]` Art. 19 §2º inciso III
- Para estagiários, o plano de atividades constante no TCE corresponde ao plano de trabalho `[IN52]` Art. 21

**Critério de aceitação:**  
Dado que existe TCR ativo e plano de entregas aprovado ou em execução,  
Quando chefia e participante pactuam o plano de trabalho com contribuições somando 100%,  
Então o sistema cria o plano com status Aprovado (2).

---

### RF-015 — Registro de Execução (Registros de Atividade)

**Origem:** `[IN24]` Art. 20 / `[API]` `avaliacoes_registros_execucao`  
**Prioridade:** Obrigatório  
**Papel:** Participante

O sistema deve permitir que o participante registre, ao longo da execução do plano de trabalho:

- Descrição dos trabalhos realizados
- Ocorrências que possam impactar o que foi pactuado (afastamentos, licenças, impedimentos, dificuldades)

**Prazos:**
- Plano de duração ≤ 30 dias: registrar em até 10 dias após o encerramento
- Plano de duração > 30 dias: registrar mensalmente, até o 10º dia do mês subsequente

O sistema deve alertar o participante sobre o prazo de registro iminente.

O monitoramento pela chefia permite ajustes e repactuação a qualquer momento durante a execução `[IN24]` Art. 20 §2º. A critério da chefia, o TCR poderá ser ajustado para atender às condições necessárias `[IN24]` Art. 20 §3º.

**Critério de aceitação:**  
Dado que o plano de trabalho está Em Execução (3),  
Quando o participante registra os trabalhos realizados,  
Então o sistema armazena o registro com data/hora e disponibiliza para avaliação pela chefia; quando o prazo de registro expira, o sistema notifica o participante e a chefia.  
Dado que a chefia identifica necessidade de ajuste no plano ou no TCR,  
Quando a chefia registra o ajuste com justificativa,  
Então o sistema registra a alteração e notifica o participante.

---

### RF-016 — Transição de Status do Plano de Trabalho

**Origem:** `[IN24]` Art. 17 / `[API]` StatusPlanoTrabalhoEnum  
**Prioridade:** Obrigatório  
**Papel:** Chefia / Sistema

O sistema deve suportar as seguintes transições de status:

```
Aprovado (2) → Em Execução (3) → Concluído (4)
Qualquer → Cancelado (1)
```

- Em Execução: ativado quando a chefia confirma início; participante pode registrar atividades
- Concluído: quando os registros de execução do período foram inseridos e encaminhados para avaliação
- Cancelado: encerramento sem conclusão

**Critério de aceitação:**  
Dado que o plano está Em Execução,  
Quando o participante finaliza o registro de execução do último período,  
Então a chefia pode transicionar o plano para Concluído.

---

### RF-017 — Avaliação do Plano de Trabalho pelo Período Avaliativo

**Origem:** `[IN24]` Art. 21 / `[IN52]` Arts. 2–6 / `[API]` `avaliacoes_registros_execucao`  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução

Em até 20 dias após o prazo de registro do participante, a chefia deve avaliar cada período avaliativo do plano de trabalho na escala:

| Código | Descrição |
|--------|-----------|
| 1 | Excepcional — muito acima do esperado |
| 2 | Alto desempenho — acima do esperado |
| 3 | Adequado — dentro do esperado |
| 4 | Inadequado — abaixo do esperado ou parcialmente executado |
| 5 | Não executado — integralmente não executado |

**Regras:**
- Avaliações com código 1, 4 e 5 devem ser obrigatoriamente justificadas
- O participante deve ser notificado da avaliação recebida
- Avaliação pode subsidiar processos de gestão de desempenho do órgão `[IN52]` Art. 2º

**Consequências por tipo de avaliação negativa:**

| Avaliação | Causa | Consequência |
|-----------|-------|--------------|
| Código 4 — Inadequado (abaixo do esperado, mas não por inexecução) | Execução abaixo do esperado | Registro obrigatório de ações de melhoria no TCR `[IN52]` Art. 3º |
| Código 4 — Inadequado (por inexecução parcial) | Inexecução parcial | Ações de melhoria no TCR + compensação de carga horária no próximo plano `[IN52]` Arts. 3–4 |
| Código 5 — Não executado | Inexecução total | Ações de melhoria no TCR + compensação de carga horária no próximo plano `[IN52]` Arts. 3–4 |
| Códigos 4 ou 5 | Inexecução sem justificativa apresentada ou não acatada | Desconto em folha de pagamento proporcional às horas não executadas `[IN52]` Art. 6º inciso I |
| Códigos 4 ou 5 | Compensação de horas prevista não realizada parcial ou integralmente | Desconto em folha de pagamento `[IN52]` Art. 6º inciso II |

A chefia deve encaminhar à gestão de pessoas todas as informações necessárias ao desconto em folha `[IN52]` Art. 6º §2º.

Independentemente do resultado da avaliação, a chefia deve estimular o aprimoramento do desempenho do participante, realizando acompanhamento periódico e propondo ações de desenvolvimento `[IN24]` Art. 21 §7º.

**Critério de aceitação:**  
Dado que o participante finalizou o registro de execução do período,  
Quando a chefia avalia com código e (se aplicável) justificativa,  
Então o sistema registra a avaliação com data, notifica o participante e:  
— se código = 4 por execução abaixo do esperado (sem inexecução): sinaliza necessidade de ações de melhoria no TCR;  
— se código = 4 por inexecução parcial ou código = 5: sinaliza necessidade de ações de melhoria no TCR e de compensação de carga horária no próximo plano;  
— se código = 1, 4 ou 5: exige justificativa obrigatória da chefia.

---

### RF-018 — Recurso de Avaliação pelo Participante

**Origem:** `[IN24]` Art. 21 §§4–6  
**Prioridade:** Obrigatório  
**Papel:** Participante / Chefia

Quando a avaliação for Inadequado (4) ou Não Executado (5), o participante pode recorrer:

1. Participante envia justificativas em até 10 dias da notificação
2. Chefia responde em até 10 dias:
   - Acata: ajusta a avaliação
   - Não acata: manifesta-se com fundamentação

Todas as ações devem ser registradas no sistema.

**Critério de aceitação:**  
Dado que o participante foi notificado de avaliação 4 ou 5,  
Quando o participante submete justificativa dentro do prazo,  
Então o sistema registra o recurso, notifica a chefia e abre prazo de 10 dias para resposta; a decisão final fica registrada e rastreável.

---

### RF-019 — Compensação de Carga Horária

**Origem:** `[IN52]` Arts. 4–5  
**Prioridade:** Obrigatório  
**Papel:** Chefia / Sistema

Quando um plano for avaliado como Inadequado por inexecução parcial ou Não Executado, o plano de trabalho do período subsequente deve prever a compensação da carga horária não executada. A soma dos percentuais pode superar 100% da carga ordinária (observados os limites de jornada).

**Critério de aceitação:**  
Dado que um plano foi avaliado como 4 ou 5 por inexecução,  
Quando a chefia cria o próximo plano de trabalho,  
Então o sistema pré-preenche a carga de compensação e exige registro do prazo de compensação no TCR.

---

### RF-020 — Banco de Horas (Vedação e Transição)

**Origem:** `[IN52]` Art. 18  
**Prioridade:** Obrigatório  
**Papel:** Sistema

Participantes do PGD não podem aderir ao banco de horas. O sistema deve:
- Bloquear nova adesão ao banco de horas para participantes do PGD
- Na entrada no PGD, registrar eventual saldo (crédito ou débito) existente no TCR
- Permitir compensação/usufruto do saldo em até 6 meses

**Critério de aceitação:**  
Dado que um novo participante tem saldo em banco de horas,  
Quando o TCR é pactuado,  
Então o sistema registra o saldo no TCR e sinaliza prazo de 6 meses para compensação/usufruto.

---

## Módulo 5 — Integração com a API PGD Central

### RF-021 — Envio de Participantes à API PGD Central

**Origem:** `[D11]` Art. 4º §5º / `[IN24]` Art. 29 / `[API]` `PUT /organizacao/{origem_unidade}/{cod_unidade_autorizadora}/{cod_unidade_lotacao}/participante/{matricula_siape}`  
**Prioridade:** Obrigatório  
**Papel:** Sistema (automático/agendado)

O sistema deve enviar os dados de participantes à API PGD Central, mapeando os campos obrigatórios:

```
origem_unidade, cod_unidade_autorizadora, cod_unidade_lotacao,
matricula_siape, cod_unidade_instituidora, cpf, situacao,
modalidade_execucao, data_assinatura_tcr
```

Nota: o endpoint inclui `cod_unidade_lotacao` como parâmetro de rota, além de `matricula_siape`, diferenciando participantes com mesma matrícula em unidades distintas.

A indisponibilidade eventual do sistema local não dispensa o envio posterior `[IN24]` Art. 29 §único.

**Critério de aceitação:**  
Dado que o participante foi cadastrado ou seu status foi alterado,  
Quando o processo de envio é executado,  
Então o sistema envia os dados via API PGD Central com tratamento de retentativas em caso de falha, registrando o resultado (sucesso/erro) no log.

---

### RF-022 — Envio de Planos de Entregas à API PGD Central

**Origem:** `[IN24]` Art. 29 / `[API]` `PUT /organizacao/.../plano_entregas/{id}`  
**Prioridade:** Obrigatório  
**Papel:** Sistema (automático/agendado)

O sistema deve enviar os planos de entregas nos status 3 (Em Execução), 4 (Concluído) e 5 (Avaliado) à API PGD Central. Planos nos status 1 e 2 não precisam ser obrigatoriamente enviados.

Campos mapeados: todos os campos do `PlanoEntregasSchema` da API PGD Central (origem_unidade, cod_unidade_autorizadora, cod_unidade_instituidora, cod_unidade_executora, id_plano_entregas, status, data_inicio, data_termino, avaliacao, data_avaliacao, lista de entregas).

**Critério de aceitação:**  
Dado que um plano de entregas transitou para status 3, 4 ou 5,  
Quando o processo de envio é executado,  
Então o sistema envia o plano com todos os campos obrigatórios, tratando conflitos de período e registrando o resultado no log.

---

### RF-023 — Envio de Planos de Trabalho à API PGD Central

**Origem:** `[IN24]` Art. 29 / `[API]` `PUT /organizacao/.../plano_trabalho/{id}`  
**Prioridade:** Obrigatório  
**Papel:** Sistema (automático/agendado)

O sistema deve enviar os planos de trabalho nos status 3 (Em Execução) e 4 (Concluído) à API PGD Central.

Campos mapeados: todos os campos do `PlanoTrabalhoSchema` da API PGD Central, incluindo a lista de contribuições e avaliações de registros de execução.

**Critério de aceitação:**  
Dado que um plano de trabalho está em status 3 ou 4,  
Quando o processo de envio é executado,  
Então o sistema envia o plano com contribuições e avaliações corretamente mapeadas, tratando erros de validação e registrando resultado no log.

---

### RF-024 — Agendamento e Monitoramento do Envio à API PGD Central

**Origem:** `[IN24]` Art. 29  
**Prioridade:** Derivado  
**Papel:** Administrador / Sistema

O sistema deve permitir:
- Configurar a periodicidade do envio automático (diário/semanal/mensal)
- Executar envio manual sob demanda
- Exibir histórico de envios com status (sucesso, erro parcial, erro total)
- Reprocessar envios com falha
- Exibir painel de conformidade: quais planos/participantes ainda não foram enviados

**Critério de aceitação:**  
Dado que o envio automático está configurado,  
Quando o prazo é atingido,  
Então o sistema executa o envio de todos os registros pendentes e disponibiliza relatório de resultado para o administrador.

---

## Módulo 6 — Autenticação e Controle de Acesso (RBAC)

### RF-025 — Gestão de Usuários do Sistema

**Origem:** `[D11]` Art. 4º §4º / `[API]` `/user/` endpoints  
**Prioridade:** Derivado  
**Papel:** Administrador

O sistema deve suportar criação, edição, ativação e desativação de usuários, com:
- E-mail único por usuário
- Senha (hash bcrypt)
- Perfil: Administrador / Gestor de RH / Chefia de Unidade / Participante / Somente Leitura
- Vinculação à unidade autorizadora

Recuperação de senha via e-mail deve ser suportada.

**Critério de aceitação:**  
Dado que um administrador cria um novo usuário,  
Quando o usuário recebe as credenciais por e-mail e faz o primeiro login,  
Então o sistema exige alteração de senha e vincula o usuário ao perfil e unidade configurados.

---

### RF-026 — Controle de Acesso por Papel (RBAC)

**Origem:** `[D11]` Art. 3º / `[IN24]` Arts. 23–26  
**Prioridade:** Derivado  
**Papel:** Sistema

| Papel | Permissões principais |
|-------|-----------------------|
| Administrador | Gestão de usuários, configuração do PGD, visualização de todos os dados, envio à API Central |
| Gestor de RH | Cadastro de participantes, TCRs, relatórios de conformidade |
| Chefia Instituidora | Gerenciar planos de entregas de unidades subordinadas |
| Chefia de Execução | Elaborar planos de entregas, pactuar planos de trabalho, avaliar participantes |
| Participante | Visualizar seu plano, registrar execução, submeter recursos |
| Nível Hierárquico Superior | Aprovar/avaliar planos de entregas |
| Somente Leitura | Consultar dados públicos da sua unidade |

**Critério de aceitação:**  
Dado que um usuário está autenticado,  
Quando tenta acessar um recurso,  
Então o sistema verifica o papel e a unidade do usuário; acesso negado resulta em HTTP 403 com mensagem descritiva.

---

## Módulo 7 — Auditoria e Rastreabilidade

### RF-027 — Log de Auditoria

**Origem:** `[IN24]` Art. 21 §6º / `[D11]` Art. 4º §4º  
**Prioridade:** Obrigatório (implícito em sistema informatizado)  
**Papel:** Sistema

O sistema deve registrar automaticamente um log de auditoria para todos os eventos críticos, contendo: entidade afetada, ação realizada, usuário responsável, data/hora, valor anterior e posterior.

Eventos críticos: criação/alteração de participantes, pactuação de TCR, criação/alteração/avaliação de planos, envio à API Central, desligamento, suspensão/revogação do PGD.

**Critério de aceitação:**  
Dado que qualquer evento crítico ocorre,  
Quando o sistema processa a operação com sucesso,  
Então um registro de auditoria é criado imutavelmente (sem possibilidade de exclusão pelo usuário comum).

---

### RF-028 — Relatórios de Conformidade

**Origem:** `[IN24]` Art. 23 inciso I / `[D11]` Art. 4º §5º  
**Prioridade:** Derivado  
**Papel:** Administrador / Gestor de RH

O sistema deve gerar relatórios de conformidade, incluindo:
- Participantes sem plano de trabalho ativo
- Planos de trabalho com registros de execução em atraso
- Planos de trabalho com avaliação pendente (chefia)
- Planos de entregas com avaliação pendente
- Registros não enviados à API PGD Central
- Histórico de avaliações por unidade e período
- Participantes com compensação de carga horária pendente (avaliação 4 ou 5 por inexecução sem plano subsequente com compensação registrada)
- Participantes com ações de melhoria registradas no TCR (subsídio para acompanhamento da chefia)
- Participantes cujos descontos em folha foram sinalizados mas não comunicados à gestão de pessoas

**Critério de aceitação:**  
Dado que o administrador ou gestor de RH acessa o módulo de relatórios,  
Quando seleciona um relatório e o período,  
Então o sistema exibe os dados filtrados com possibilidade de exportação em formato aberto (CSV ou XLSX).

---

## Módulo 8 — Notificações e Alertas

### RF-029 — Sistema de Notificações

**Origem:** `[IN24]` Art. 21 §§2,4,5  
**Prioridade:** Obrigatório (para os eventos listados) / Derivado (para alertas gerais)  
**Papel:** Sistema

O sistema deve enviar notificações aos usuários nos seguintes eventos obrigatórios:

| Evento | Destinatário | Prazo de envio |
|--------|-------------|----------------|
| Avaliação do plano de trabalho realizada | Participante | Imediato |
| Plano avaliado como 4 ou 5 (para recurso) | Participante | Imediato, com prazo de 10 dias |
| Recurso submetido (para resposta) | Chefia | Imediato, com prazo de 10 dias |
| Prazo de registro de execução se aproxima | Participante | 3 dias antes do vencimento |
| Prazo de avaliação se aproxima | Chefia | 3 dias antes do vencimento |
| Convocação presencial | Participante | Imediato |
| Desligamento do PGD | Participante | Imediato, com prazo de retorno |
| Suspensão/Revogação do PGD | Todos os participantes ativos | Imediato |

Canal padrão: e-mail + notificação no sistema. Suporte a canais adicionais (webhook) para integração com ferramentas do órgão.

---

## Módulo 9 — Configuração e Administração

### RF-030 — Configuração Multi-Órgão (Multi-Tenant)

**Origem:** `[D11]` Art. 4º / `[API]` `origem_unidade` + `cod_unidade_autorizadora`  
**Prioridade:** Derivado (para instalação centralizada)  
**Papel:** Administrador

O sistema deve suportar múltiplas unidades autorizadoras em uma única instalação, com isolamento de dados por `origem_unidade` + `cod_unidade_autorizadora`. Cada órgão gerencia apenas seus próprios dados.

---

### RF-031 — Configuração de Escalas de Avaliação Customizadas

**Origem:** `[IN24]` Art. 30  
**Prioridade:** Obrigatório  
**Papel:** Administrador

O sistema deve permitir que unidades instituidoras utilizem escalas próprias de avaliação, desde que o sistema converta automaticamente os valores para a escala padrão (1–5) antes do envio à API PGD Central.

**Critério de aceitação:**  
Dado que uma unidade configura escala customizada (ex.: A/B/C/D/E),  
Quando um plano é avaliado com essa escala,  
Então o sistema armazena o valor original e calcula o equivalente na escala padrão para o envio à API.

---

## Módulo 10 — Gestão de Pessoas e Operações de RH

### RF-034 — Ações de Desenvolvimento em Serviço no Plano de Trabalho

**Origem:** `[IN52]` Art. 17  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução / Participante

Quando o participante realiza ações de desenvolvimento (capacitação, treinamento, curso) durante a jornada de trabalho, sem afastamento formal, essas ações devem constar no plano de trabalho como "ação de desenvolvimento em serviço", com:

- Descrição da ação de desenvolvimento
- Período de realização
- Carga horária correspondente (alocada no percentual de contribuição tipo 2 — não vinculada diretamente a entrega)

**Critério de aceitação:**  
Dado que o participante possui ação de desenvolvimento prevista na jornada de trabalho,  
Quando a chefia ou o participante elabora o plano de trabalho,  
Então o sistema permite registrar a ação como contribuição tipo 2 com rótulo "ação de desenvolvimento em serviço", e essa informação é preservada na exportação e no envio à API PGD Central.

---

### RF-035 — Controle de Adicionais Ocupacionais e Noturno

**Origem:** `[IN52]` Arts. 8º e 9º / `[D11]` Arts. 14–15  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução / Gestão de RH

O sistema deve suportar o controle dos adicionais para participantes do PGD:

1. **Adicionais de insalubridade, periculosidade ou irradiação ionizante:** devidos a participantes em modalidade presencial ou teletrabalho parcial, quando expostos às condições que os justificam por período igual ou superior à metade da carga horária da jornada pactuada.
   - Nesses casos, o plano de trabalho deve ser obrigatoriamente estabelecido em **período mensal** `[IN52]` Art. 8º §2º.
   - A chefia registra no sistema de controle de frequência os dias de exposição presencial `[IN52]` Art. 8º §3º.
   - Teletrabalho integral: vedado o pagamento desses adicionais `[D11]` Art. 15.

2. **Adicional noturno** (atividades entre 22h e 5h): somente devido quando houver:
   - Autorização prévia e justificada da chefia com necessidade comprovada da administração `[D11]` Art. 14 §único / `[IN52]` Art. 9º
   - Documentação encaminhada à gestão de pessoas: autorização e justificativa, período/horário de realização, relação nominal dos participantes autorizados `[IN52]` Art. 9º §1º
   - Declaração da chefia atestando a realização da atividade `[IN52]` Art. 9º §2º

**Critério de aceitação:**  
Dado que o participante está em modalidade presencial ou teletrabalho parcial e sujeito a adicional ocupacional,  
Quando a chefia cria o plano de trabalho,  
Então o sistema exige periodicidade mensal do plano e exibe alerta sobre a obrigação de registro no sistema de controle de frequência.  
Dado que a chefia solicita autorização de atividade noturna,  
Quando registra a autorização com justificativa, período, horário e relação nominal,  
Então o sistema registra a autorização e gera documento para encaminhamento à gestão de pessoas.

---

### RF-036 — Registro de Códigos de Participação no PGD (Frequência)

**Origem:** `[IN24]` Art. 25 inciso V  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução

O sistema deve suportar o registro — ou a geração de relatório para registro externo — dos códigos de participação em PGD e dos casos de licenças e afastamentos relativos aos participantes da unidade, para fins de lançamento no sistema de controle de frequência do órgão (ex.: SIAPE Frequência).

O sistema deve identificar participantes com licenças ou afastamentos registrados no plano de trabalho para facilitar esse lançamento diferenciado.

**Critério de aceitação:**  
Dado que a chefia acessa o módulo de frequência,  
Quando seleciona a unidade e o período,  
Então o sistema exibe a relação de participantes com o código de participação em PGD a ser lançado, destacando aqueles com licenças ou afastamentos registrados no período.

---

### RF-037 — Delegação de Competências da Chefia

**Origem:** `[D11]` Art. 3º §4º / `[IN24]` Art. 25 §único / `[IN52]` Art. 22  
**Prioridade:** Obrigatório  
**Papel:** Chefia da unidade de execução / Administrador

O sistema deve suportar a delegação das competências da chefia da unidade de execução à chefia imediata do participante, com as seguintes restrições:
- A competência de elaborar e monitorar o plano de entregas **não pode** ser delegada `[IN24]` Art. 25 §único.
- Para estagiários, as atribuições do supervisor de estágio seguem as mesmas regras `[IN52]` Art. 22.

As delegações devem ser registradas com prazo de vigência e podem ser revogadas a qualquer momento.

**Critério de aceitação:**  
Dado que a chefia da unidade de execução registra uma delegação,  
Quando informa o delegado, as competências delegadas e o prazo,  
Então o sistema concede ao delegado acesso às funcionalidades correspondentes, bloqueia a delegação da competência de elaboração do plano de entregas, e registra o ato em log de auditoria.

---

## Resumo dos Requisitos

| Módulo | RFs | Obrigatórios | Derivados |
|--------|-----|-------------|-----------|
| 1 — Gestão Institucional | RF-001 a RF-004 | 4 | 0 |
| 2 — Gestão de Participantes | RF-005 a RF-009, RF-032, RF-033 | 7 | 0 |
| 3 — Plano de Entregas | RF-010 a RF-013 | 4 | 0 |
| 4 — Plano de Trabalho | RF-014 a RF-020 | 7 | 0 |
| 5 — Integração API Central | RF-021 a RF-024 | 3 | 1 |
| 6 — Autenticação / RBAC | RF-025 a RF-026 | 0 | 2 |
| 7 — Auditoria | RF-027 a RF-028 | 1 | 1 |
| 8 — Notificações | RF-029 | 1 | 0 |
| 9 — Configuração | RF-030 a RF-031 | 1 | 1 |
| 10 — Gestão de Pessoas e RH | RF-034 a RF-037 | 4 | 0 |
| **Total** | **37** | **32** | **5** |

---

## Notas da Revisão (v0.2 — 2026-05-13)

### Correções em RFs existentes

| RF | Problema | Correção |
|----|----------|----------|
| RF-002 | Ausência do campo "nível de produtividade adicional exigido para teletrabalho" (`[D11]` Art. 4º inciso IV) | Campo adicionado à lista de conteúdo obrigatório do ato de instituição; redação do percentual de vagas alinhada ao texto literal da IN24 ("em relação ao total de agentes públicos") |
| RF-003 | Referência a "RF-031" para notificações, mas RF-031 é sobre escalas customizadas | Corrigido para "RF-029" (módulo de notificações) |
| RF-004 | Cobria apenas os resultados do PGD; o `[D11]` Art. 4º §3º inciso I e o `[IN24]` Art. 23 inciso V exigem também a publicidade do *ato de instituição* e o registro do endereço do sítio eletrônico junto ao CPGD | Título e escopo ampliados; dois novos sub-requisitos adicionados (publicidade do ato + registro do endereço) |
| RF-005 | Ausência das regras especiais para empregados de empresas públicas (`[D11]` Art. 9º §4º) e para estagiários (`[D11]` Art. 9º §§2º–3º / `[IN52]` Art. 20) | Duas novas regras de validação adicionadas |
| RF-006 | Não mencionava o caráter impessoal da seleção nem a obrigação de estabelecer e divulgar critérios técnicos (`[D11]` Arts. 7º e 7º §2º); critério de aceitação não incluía o registro dos critérios utilizados | Parágrafo adicional inserido; critério de aceitação reforçado com rastreabilidade |
| RF-007 | TCR não incluía o "prazo de compensação" como item obrigatório (`[IN52]` Art. 4º §único); a regra especial dos estagiários (TCR no TCE) estava ausente (`[IN52]` Arts. 20–21); ações de melhoria corretamente atribuídas mas sem distinção entre "abaixo do esperado" e "inexecução" | Prazo de compensação adicionado; regra para estagiários adicionada; distinção de causalidade clarificada |
| RF-010 | Regras de validação da API estavam incompletas (lista vazia de entregas e unicidade de `id_entrega`) | Duas regras adicionadas (`[API]`) |
| RF-014 | Descrição das regras de soma dos percentuais estava incompleta (não mencionava os casos em que pode ser < 100% por usufruto de banco de horas); tipo 2 chamado erroneamente de "vinculada a outra unidade" (é o tipo 3); faltava a regra de `data_inicio` posterior à do plano de entregas e a regra de lista vazia (`[API]`) | Regras de percentual, tipagem das contribuições, restrição de data e lista vazia corrigidas/completadas |
| RF-015 | Não mencionava a possibilidade de ajustes e repactuação do plano de trabalho pela chefia a qualquer momento (`[IN24]` Art. 20 §2º–3º) | Parágrafo e critério de aceitação adicionados |
| RF-017 | Tabela de consequências mesclava dois regimes distintos da IN52 (código 4 por "abaixo do esperado" vs. código 4 por "inexecução parcial"); ausência da obrigação da chefia de encaminhar dados para desconto em folha e de estimular desenvolvimento do participante (`[IN24]` Art. 21 §7º) | Tabela de consequências reestruturada; dois parágrafos adicionados; critério de aceitação detalhado por tipo de avaliação |
| RF-021 | Endpoint incorreto: a URL real inclui `{cod_unidade_lotacao}` como parâmetro de rota, conforme `api.py` | Endpoint corrigido; nota explicativa adicionada |
| RF-028 | Relatórios de conformidade não cobriam compensações de carga horária pendentes, ações de melhoria abertas e descontos em folha não comunicados | Três novos itens de relatório adicionados; critério de aceitação com exportação inserido |

### RFs novos adicionados

| RF | Origem | Justificativa |
|----|--------|---------------|
| RF-032 — Retirada de Equipamentos | `[IN24]` Art. 16 | O órgão pode autorizar retirada de equipamentos por participantes em teletrabalho integral; obriga firmamento de Termo de Guarda e Responsabilidade, que o sistema deve registrar |
| RF-033 — Acumulação de Cargos | `[IN52]` Art. 19 | Participantes que acumulam cargos devem declarar ausência de prejuízo ao plano de trabalho; declaração deve ser registrada e rastreável |
| RF-034 — Ações de Desenvolvimento em Serviço | `[IN52]` Art. 17 | Ações de capacitação realizadas durante a jornada devem constar no plano de trabalho como contribuição tipo 2; requisito funcional direto e testável |
| RF-035 — Adicionais Ocupacionais e Noturno | `[IN52]` Arts. 8–9 / `[D11]` Arts. 14–15 | Participantes em presencial/parcial sujeitos a adicionais exigem plano mensal e registro de frequência diferenciado; atividade noturna exige autorização formal prévia com documentação encaminhada à gestão de pessoas |
| RF-036 — Registro de Frequência/Códigos PGD | `[IN24]` Art. 25 inciso V | A chefia é obrigada a registrar códigos de participação em PGD e afastamentos no sistema de controle de frequência; a plataforma deve subsidiar esse processo |
| RF-037 — Delegação de Competências | `[D11]` Art. 3º §4º / `[IN24]` Art. 25 §único / `[IN52]` Art. 22 | O sistema deve implementar o mecanismo de delegação previsto em lei, incluindo a restrição de que a elaboração do plano de entregas não pode ser delegada |

### Rastreabilidade e consistência

- A referência cruzada RF-003 → RF-031 foi corrigida para RF-003 → RF-029.
- O RF-014 trazia "contribuição tipo 2" descrita como "vinculada a outra unidade", mas o tipo 2 na API e na lei é "não vinculada diretamente a entregas". O tipo 3 é o vinculado a entregas de outra unidade. Corrigido.
- A tabela de resumo foi atualizada: 37 RFs totais (32 obrigatórios, 5 derivados).

---

## Notas da Revisão (v0.3 — 2026-05-13)

### Status de implementação por RF

| RF | Status | Arquivo de teste |
|----|--------|-----------------|
| RF-001 | ✅ Implementado | `test_institucional.py` |
| RF-002 | ✅ Implementado | `test_institucional.py` |
| RF-003 | ✅ Implementado | `test_institucional.py` |
| RF-004 | ✅ Implementado | `test_public.py` |
| RF-005 | ✅ Implementado | `test_participante.py` |
| RF-006 | ✅ Implementado | `test_selecao.py` |
| RF-007 | ✅ Implementado | `test_participante.py` |
| RF-008 | ✅ Implementado | `test_participante.py` |
| RF-009 | ✅ Implementado | `test_participante.py` |
| RF-010 | ✅ Implementado | `test_plano_entregas.py` |
| RF-011 | ✅ Implementado | `test_aprovacao_pe.py` |
| RF-012 | ✅ Implementado | `test_plano_entregas.py` |
| RF-013 | ✅ Implementado | `test_plano_entregas.py` |
| RF-014 | ✅ Implementado | `test_plano_trabalho.py` |
| RF-015 | ✅ Implementado | `test_plano_trabalho.py` |
| RF-016 | ✅ Implementado | `test_plano_trabalho.py` |
| RF-017 | ✅ Implementado | `test_avaliacao.py` |
| RF-018 | ✅ Implementado | `test_avaliacao.py` |
| RF-019 | ✅ Implementado | `test_compensacao_banco.py` |
| RF-020 | ✅ Implementado | `test_compensacao_banco.py` |
| RF-021 | ✅ Implementado | `test_sync.py` · `test_conformidade.py` |
| RF-022 | ✅ Implementado | `test_sync.py` |
| RF-023 | ✅ Implementado | `test_sync.py` |
| RF-024 | ⏳ Parcial | `test_conformidade.py` — painel e reprocessamento ✅; agendamento Cloud Scheduler ❌ |
| RF-025 | ⏳ Parcial | `test_auth_router.py` — OAuth ✅; gestão CRUD de usuários ❌ |
| RF-026 | ✅ Implementado | `test_permissions.py` · `test_multitenant.py` |
| RF-027 | ✅ Implementado | `test_auditoria.py` |
| RF-028 | ⏳ Parcial | `test_relatorios.py` — TC-M07-005/006/007/008 ✅; TC-M07-009 (PE pendentes) ❌ |
| RF-029 | ✅ Implementado | `test_notificacoes.py` |
| RF-030 | ✅ Implementado | `test_multitenant.py` — `User.cod_unidade_autorizadora`; filtro por unidade em todas as queries GraphQL |
| RF-031 | ✅ Implementado | `test_gestao_rh.py` |
| RF-032 | ✅ Implementado | `test_gestao_rh.py` |
| RF-033 | ✅ Implementado | `test_gestao_rh.py` |
| RF-034 | ⏳ Parcial | `test_gestao_rh.py` — TC-M10-001 ✅; TC-M10-002 (payload API) ❌ |
| RF-035 | ⏳ Parcial | `test_gestao_rh.py` — TC-M10-003/004 ✅; TC-M10-005/006 (adicional noturno) ❌ |
| RF-036 | ❌ Pendente | — |
| RF-037 | ❌ Pendente | — |

### Detalhes de implementação (RF-021 a RF-024)

**RegistroEnvioAPI** (`src/models/sync_log.py`) — modelo que guarda o histórico de tentativas de envio:
- `tipo_entidade`: `participante` | `plano_entregas` | `plano_trabalho`
- `entidade_id`: UUID da entidade enviada
- `tentativa`: número ordinal da tentativa (1, 2, 3)
- `sucesso`: bool
- `http_status`: código HTTP da resposta da API Central (quando disponível)
- `erro_mensagem`: texto do erro

**Backoff** (`src/integration/sync.py`):
- `RETRY_DELAYS = [60, 300, 1800]` segundos (1 min → 5 min → 30 min)
- `MAX_TENTATIVAS = 3`
- Entidade esgotada (tentativa ≥ 3) exige `reprocessarEnvio` manual pelo admin

**Isolamento multi-tenant** (`src/models/user.py`, `src/graphql/schema.py`):
- `User.cod_unidade_autorizadora` (BigInteger nullable) — `null` significa ADMIN sem restrição de unidade
- Migração: `f1a2b3c4d5e6`
- Todas as queries de listagem (`listarParticipantes`, `listarPlanosEntregas`, `listarPlanosTrabalho`) e de busca por ID filtram por unidade para roles não-admin

---

## Notas da Revisão (v0.4 — 2026-05-13)

### RFs implementados nesta revisão

| RF | TCs novos | Arquivo de teste |
|----|-----------|-----------------|
| RF-006 — Seleção com prioridades | TC-M02-012/013/014 | `test_selecao.py` |
| RF-011 — Aprovação hierárquica do PE | TC-M03-009/010/011 | `test_aprovacao_pe.py` |
| RF-019 — Compensação de carga horária | TC-M04-033/034 + variantes TCR | `test_compensacao_banco.py` |
| RF-020 — Banco de horas | TC-M04-035/036 | `test_compensacao_banco.py` |
| RF-028 — Relatórios de conformidade (parcial) | TC-M07-005/006/007/008 | `test_relatorios.py` |
| RF-031 — Escalas customizadas | TC-M09-003/004/005 | `test_gestao_rh.py` |
| RF-032 — Retirada de equipamentos | TC-M02-026/027 | `test_gestao_rh.py` |
| RF-033 — Acumulação de cargos | TC-M02-028/029 | `test_gestao_rh.py` |
| RF-034 — Ações de desenvolvimento (parcial) | TC-M10-001 | `test_gestao_rh.py` |
| RF-035 — Adicionais ocupacionais (parcial) | TC-M10-003/004 | `test_gestao_rh.py` |

**Total de testes após esta revisão:** 251 passando (+ 8 skipped).

### Pendências após v0.4

| Item | Descrição |
|------|-----------|
| RF-028 TC-M07-009 | Relatório de planos de entregas com avaliação pendente |
| RF-034 TC-M10-002 | Ação de desenvolvimento incluída no payload da API Central |
| RF-035 TC-M10-005/006 | Autorização de atividade noturna com documentação formal |
| RF-036 | Registro de códigos de participação (frequência) |
| RF-037 | Delegação de competências da chefia |
| RF-024 TC-M05-010 | Agendamento automático de envio (Cloud Scheduler) |
| RF-025 TC-M06-003/004/005 | CRUD de usuários e recuperação de senha |

---

## Requisitos Não Funcionais (RNF) de Referência

Estes requisitos devem ser detalhados no plano de implementação:

- **RNF-001 — Disponibilidade:** O sistema deve ter disponibilidade mínima de 99,5% durante horário útil (07h–21h em dias úteis).
- **RNF-002 — Auditabilidade:** Todos os dados devem ser rastreáveis; registros de auditoria não podem ser excluídos.
- **RNF-003 — Segurança:** Autenticação com JWT; senhas em bcrypt; HTTPS obrigatório; proteção contra OWASP Top 10.
- **RNF-004 — Interoperabilidade:** Compatibilidade total com o contrato da API PGD Central vigente.
- **RNF-005 — Implantabilidade:** A aplicação deve ser distribuída como imagem Docker com `docker-compose` para instalação simplificada pelo órgão.
- **RNF-006 — Acessibilidade:** Interface web em conformidade com WCAG 2.1 AA (obrigatório para sistemas do governo federal).
- **RNF-007 — Privacidade:** Tratamento de dados pessoais (CPF, matrícula) em conformidade com a LGPD.
