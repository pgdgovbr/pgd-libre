# Frontend Briefing — PGD Libre

**Para:** Claude Design  
**Data:** 2026-05-15  
**Stack:** SvelteKit + GraphQL (Strawberry, code-first) + graphql-codegen  
**Idioma:** PT-BR em toda a interface

---

## 1. O que é o PGD Libre

Sistema de gestão do **Programa de Gestão e Desempenho (PGD)** para órgãos do governo federal brasileiro. O PGD é a modalidade oficial que permite o teletrabalho de servidores públicos — cada servidor precisa ter um **Plano de Trabalho** ativo descrevendo suas contribuições, registrar mensalmente o que fez, e receber avaliação da chefia.

O sistema substitui planilhas e e-mails. É instalado no órgão (self-hosted) e envia dados automaticamente para a API PGD Central do Ministério da Gestão (MGI), que é obrigatória por lei.

**Usuários:** servidores e chefias de um órgão federal. Não é um portal público — acesso via login corporativo (Google OAuth / Gov.br).

---

## 2. Papéis e Personas

O sistema tem 4 papéis com hierarquia. Cada tela deve adaptar conteúdo e ações ao papel do usuário logado.

### 2.1 Servidor (`servidor`)
> Ana, 34 anos, analista em teletrabalho integral. Acessa o sistema mensalmente para registrar o que fez. Não tem paciência para formulários longos. Quer saber: "o que preciso fazer hoje?"

**Necessidades principais:**
- Ver seu Plano de Trabalho ativo
- Registrar execução mensal sem errar o prazo
- Receber feedback da avaliação da chefia
- Abrir recurso se discordar da avaliação

**Frustrações comuns:** prazo de registro passou sem perceber, não sabe qual nota recebeu.

---

### 2.2 Chefia Imediata (`chefe_imediato`)
> Carlos, 48 anos, chefe de seção. Responsável por 12 servidores. Acessa o sistema semanalmente. Quer visibilidade da equipe sem ter que abrir um por um.

**Necessidades principais:**
- Visão geral do status do time (quem está em dia, quem está atrasado)
- Avaliar registros de execução de cada servidor
- Criar e gerenciar Planos de Trabalho da equipe
- Convocar presencialmente com registro formal
- Aprovar Plano de Entregas

**Frustrações comuns:** ter que lembrar de avaliar dentro do prazo de 20 dias, ver avaliações pendentes espalhadas.

---

### 2.3 Gestor de Unidade (`gestor_unidade`)
> Beatriz, 52 anos, diretora de área. Acessa mensalmente para acompanhar conformidade. Foco em números e relatórios.

**Necessidades principais:**
- Painel de conformidade: quantos planos enviados à API Central
- Relatórios de planos sem avaliação, registros em atraso
- Visão consolidada da unidade

---

### 2.4 Administrador (`admin`)
> Pedro, 41 anos, responsável pela TI/RH do órgão. Configura o sistema no início e faz manutenção.

**Necessidades principais:**
- Cadastrar participantes
- Configurar unidades autorizadoras e instituidoras
- Monitorar sincronização com API PGD Central
- Reprocessar envios com falha

---

## 3. Arquitetura de Informação

```
/ (dashboard — varia por papel)
│
├── /meu-plano          # Servidor: plano de trabalho ativo
│   └── /registrar      # Formulário de execução mensal
│
├── /equipe             # Chefia: lista de participantes e planos
│   ├── /participantes
│   │   └── /[id]       # Perfil do participante + TCR + afastamentos
│   ├── /planos-trabalho
│   │   └── /[id]       # Detalhe + avaliações
│   └── /planos-entregas
│       └── /[id]
│
├── /conformidade       # Gestor/Admin: painel de API Central + relatórios
│
├── /admin              # Admin only
│   ├── /participantes/novo
│   └── /institucional  # Unidades, atos
│
└── /notificacoes
```

---

## 4. Telas Prioritizadas

### P0 — Deve existir no MVP

| # | Tela | Papel principal | Frequência de uso |
|---|------|----------------|-------------------|
| 1 | **Dashboard / Home** | Todos | Diária |
| 2 | **Meu Plano de Trabalho** | Servidor | Mensal |
| 3 | **Registrar Execução** | Servidor | Mensal |
| 4 | **Lista da Equipe (Chefia)** | Chefia | Semanal |
| 5 | **Detalhe do Plano de Trabalho** | Chefia | Semanal |
| 6 | **Avaliar Registro de Execução** | Chefia | Mensal |
| 7 | **Lista de Participantes** | Chefia/Admin | Eventual |

### P1 — Core, mas não bloqueia o MVP

| # | Tela | Papel principal |
|---|------|----------------|
| 8 | **Criar/Editar Plano de Entregas** | Chefia |
| 9 | **Cadastrar Participante** | Admin |
| 10 | **Painel de Conformidade** | Admin/Gestor |
| 11 | **Relatórios** | Gestor/Admin |

### P2 — Completa o sistema

| # | Tela | Papel principal |
|---|------|----------------|
| 12 | **Recurso de Avaliação** | Servidor |
| 13 | **Gestão Institucional** | Admin |
| 14 | **Notificações** | Todos |
| 15 | **Perfil do Participante** | Chefia/Admin |

---

## 5. Fluxos Críticos (golden paths)

### Fluxo A — Servidor registra execução mensal

```
Dashboard → alerta "Registro de execução pendente (vence em X dias)"
  → Meu Plano de Trabalho → botão "Registrar execução do mês"
  → Formulário: data início/fim do período + campo texto livre "O que fiz"
    + campo "Ocorrências" (opcional: licenças, impedimentos)
  → Enviar → confirmação → voltar ao plano com status atualizado
```

**Regra de prazo:**
- Plano ≤ 30 dias → registrar em até 10 dias após encerramento
- Plano > 30 dias → registrar mensalmente, até dia 10 do mês seguinte

---

### Fluxo B — Chefia avalia registro do servidor

```
Dashboard → alerta "X avaliações pendentes"
  → Lista de avaliações pendentes → selecionar servidor
  → Ver descrição de execução do servidor
  → Selecionar nota (1–5) + justificativa se nota 1, 4 ou 5
  → Confirmar → servidor recebe notificação
```

**Notas:** 1=Excepcional, 2=Alto, 3=Adequado, 4=Inadequado, 5=Não executado  
**Regra:** Notas 1, 4 e 5 exigem justificativa obrigatória.

---

### Fluxo C — Servidor abre recurso (se nota for 4 ou 5)

```
Meu Plano → ver avaliação recebida (nota 4 ou 5)
  → botão "Contestar avaliação" (visível por 10 dias)
  → Formulário: texto com justificativa
  → Enviar → chefia recebe notificação → prazo 10 dias para resposta
```

---

### Fluxo D — Chefia cria Plano de Trabalho para servidor

```
Lista de Participantes → selecionar participante com TCR ativo
  → botão "Criar Plano de Trabalho"
  → Preencher: período (máx. 1 ano), carga horária disponível, critérios de avaliação
  → Adicionar contribuições (ao menos 1):
    - Tipo 1: vinculada a entrega do Plano de Entregas da unidade
    - Tipo 2: não vinculada (ex.: gestão de equipe, capacitação)
    - Tipo 3: vinculada a entrega de outra unidade
    - Soma dos percentuais deve ser 100%
  → Salvar → iniciar execução
```

---

## 6. Conteúdo por Tela

### Tela 1 — Dashboard

Adapta-se ao papel:

**Servidor vê:**
- Plano de Trabalho ativo: status badge + período + % contribuições
- Alertas de prazo (registro pendente, avaliação recebida)
- Últimas notificações (máx. 5)

**Chefia vê:**
- Contadores: X participantes ativos / X avaliações pendentes / X planos em execução
- Lista de ações urgentes: avaliações com prazo próximo
- Status do Plano de Entregas da unidade

**Admin vê:**
- Painel de conformidade resumido (enviados/pendentes/erro para API Central)
- Alertas de sincronização com falha

---

### Tela 2 — Meu Plano de Trabalho (Servidor)

**Dados exibidos:**
- Período: `data_inicio` → `data_termino`
- Status badge (ver seção 7)
- Carga horária disponível
- Critérios de avaliação definidos pela chefia
- Lista de contribuições:
  - Tipo (1/2/3), descrição, % da carga horária
  - Se tipo 1: nome da entrega vinculada
- Histórico de avaliações por período:
  - Período, nota, data avaliação, justificativa
  - Status do recurso, se houver

**Ações possíveis (dependem do status):**
- Em Execução → "Registrar execução do período"
- Avaliação recebida 4 ou 5 → "Contestar avaliação" (dentro do prazo)

---

### Tela 3 — Registrar Execução (Servidor)

**Formulário:**
- Período avaliativo: data início + data fim (pré-preenchido com o mês atual)
- **Descrição da execução:** textarea longo — "Descreva os trabalhos realizados no período"
- **Ocorrências** (opcional): textarea — "Licenças, afastamentos ou impedimentos que impactaram o plano"

**Validação:** período não pode sobrepor registro anterior.

---

### Tela 4 — Lista da Equipe / Planos de Trabalho (Chefia)

**Tabela de participantes ativos com colunas:**
- Nome, matrícula SIAPE, modalidade (Presencial / TT Parcial / TT Integral / Exterior)
- Status do plano de trabalho ativo
- Próximo prazo de registro
- Próxima avaliação pendente

**Filtros:** por status do plano, por modalidade, por plano de entregas vinculado.

**Ações rápidas:** Avaliar (quando há avaliação pendente), Ver detalhe.

---

### Tela 5 — Detalhe do Plano de Trabalho (Chefia)

**Seções:**
1. Cabeçalho: participante, período, status, carga horária
2. Contribuições: tabela com tipo, descrição, %
3. Histórico de avaliações:
   - Cada período: data, nota, justificativa, status do recurso
   - Botão "Avaliar" (quando pendente e dentro do prazo)
4. Timeline de status do plano

---

### Tela 6 — Avaliar Registro de Execução (Chefia)

**Contexto visível (read-only):**
- Nome do servidor
- Período avaliativo
- Descrição de execução submetida pelo servidor
- Ocorrências registradas

**Formulário de avaliação:**
- **Nota:** seletor visual de 1 a 5 (ver escala na seção 7)
- **Justificativa:** campo obrigatório se nota for 1, 4 ou 5
- **Data da avaliação:** date picker (pré-preenchido com hoje)

---

### Tela 10 — Painel de Conformidade (Admin)

**Três cards lado a lado:**
- Participantes: total / enviados / pendentes / com erro
- Planos de Entregas: idem
- Planos de Trabalho: idem

**Tabela de erros:**
- Entidade, tipo, última tentativa, mensagem de erro, botão "Reprocessar"

---

## 7. Sistema Visual

### 7.1 Design System de Referência

Seguir o **GOV.BR Design System** (https://www.gov.br/ds). É o padrão obrigatório para sistemas do governo federal brasileiro. Principais referências:
- Tipografia: Rawline (ou Raleway como fallback)
- Cores institucionais: azul `#1351B4` (primária), verde `#168821` (sucesso)
- Grid: 12 colunas, breakpoints padrão
- Componentes: botões, tabelas, formulários, alertas, breadcrumbs

### 7.2 Cores de Status — Plano de Trabalho e Plano de Entregas

| Código | Rótulo | Cor |
|--------|--------|-----|
| 1 | Cancelado | Cinza `#888` |
| 2 | Aprovado | Azul `#1351B4` |
| 3 | Em Execução | Verde `#168821` |
| 4 | Concluído | Verde-escuro `#0C4A1A` |
| 5 | Avaliado | Roxo `#5C2D91` |

### 7.3 Escala de Avaliação (notas 1–5)

| Nota | Descrição | Cor do badge |
|------|-----------|-------------|
| 1 | Excepcional | Verde-escuro |
| 2 | Alto desempenho | Verde |
| 3 | Adequado | Azul |
| 4 | Inadequado | Laranja |
| 5 | Não executado | Vermelho |

### 7.4 Modalidades de Execução

| Código | Rótulo curto |
|--------|-------------|
| 1 | Presencial |
| 2 | Teletrabalho Parcial |
| 3 | Teletrabalho Integral |
| 4 | Teletrabalho Exterior (art. 12 VIII) |
| 5 | Teletrabalho Exterior (art. 12 §7º) |

### 7.5 Princípios de UX para este domínio

- **Desktop-first:** servidores usam computador no trabalho. Mobile é secundário.
- **Ações com prazo em destaque:** o sistema tem muitos prazos legais (10, 20, 30 dias). Datas de vencimento devem aparecer com cor de urgência: verde > 7 dias, amarelo ≤ 7 dias, vermelho vencido.
- **Sem termos técnicos na UI:** o usuário final não sabe o que é "PUT /organizacao/..." — traduzir tudo para linguagem de gestão de pessoas.
- **Confirmação em ações irreversíveis:** avaliar, desligar participante, cancelar plano — pedir confirmação com modal.
- **Formulários longos em steps:** TCR e Plano de Trabalho têm muitos campos — dividir em etapas (wizard).
- **Acessibilidade obrigatória:** WCAG 2.1 AA (exigência legal para sistemas do governo federal). Contraste mínimo 4.5:1, labels em todos os inputs, foco visível via teclado.

---

## 8. Constraints Técnicas

### Autenticação
- O usuário já está logado quando chega ao frontend (Google OAuth / Gov.br via backend)
- O backend emite um cookie `access_token` (httpOnly, SameSite=Lax) — o SvelteKit o recebe automaticamente
- Para saber quem está logado: `GET /auth/me` ou `query { me { id email name role } }`
- Não há tela de login no SvelteKit — redirecionar para `/auth/login/google` quando não autenticado

### API
- GraphQL endpoint: `POST /graphql`
- Base URL em produção: `https://pgd-libre-klvx64dufq-rj.a.run.app`
- Usar `graphql-codegen` para gerar tipos TypeScript a partir do SDL:
  ```bash
  strawberry export-schema src.main:app > schema.graphql
  ```

### Queries GraphQL disponíveis (simplificado)

```graphql
query {
  me { id email name role }
  listarParticipantes { id nome matriculaSimpe situacao modalidadeExecucao ... }
  listarPlanosTrabalho { id status dataInicio dataTermino contribuicoes { ... } avaliacoes { ... } }
  listarPlanosEntregas { id status dataInicio dataTermino entregas { ... } }
  minhasNotificacoes { id mensagem lida criadoEm }
  painelConformidade { participantes { total enviados pendentes comErro } ... }
  relatorioSemPlanoTrabalho { ... }
  relatorioAvaliacoesPendentes(referencia: Date!) { ... }
}

mutation {
  registrarExecucao(planoTrabalhoId: ID!, input: RegistrarExecucaoInput!) { ... }
  avaliarRegistrosExecucao(avaliacaoId: ID!, nota: Int!, dataAvaliacao: Date!, justificativa: String) { ... }
  abrirRecurso(avaliacaoId: ID!, texto: String!) { ... }
  criarPlanoTrabalho(participanteId: ID!, input: CriarPlanoTrabalhoInput!) { ... }
  adicionarContribuicao(planoTrabalhoId: ID!, input: AdicionarContribuicaoInput!) { ... }
  iniciarExecucaoPlanoTrabalho(planoId: ID!) { ... }
}
```

### Variáveis de ambiente do SvelteKit
```
PUBLIC_GRAPHQL_URL=https://pgd-libre-klvx64dufq-rj.a.run.app/graphql
PUBLIC_AUTH_URL=https://pgd-libre-klvx64dufq-rj.a.run.app/auth
```

---

## 9. Glossário (domínio → UI)

| Termo técnico | Rótulo na interface |
|---------------|---------------------|
| `PlanoTrabalho` | Plano de Trabalho |
| `PlanoEntregas` | Plano de Entregas |
| `AvaliacaoRegistrosExecucao` | Avaliação do período / Registro de execução |
| `Contribuicao` | Contribuição ao plano |
| `TCR` | Termo de Ciência e Responsabilidade |
| `Participante` | Servidor participante do PGD |
| `UnidadeAutorizadora` | Órgão / unidade autorizadora |
| `UnidadeInstituidora` | Unidade instituidora do PGD |
| `RegistroEnvioAPI` | Envio à API PGD Central |
| `api_sincronizado_em` | Enviado à API em |
| `cod_unidade_autorizadora` | Código da unidade autorizadora (SIAPE/SIORG) |
| `matricula_siape` | Matrícula SIAPE |
| `modalidade_execucao: 3` | Teletrabalho integral |
| `situacao: 1` | Ativo no PGD |
| `situacao: 0` | Desligado do PGD |
| `UserRole.admin` | Administrador |
| `UserRole.gestor_unidade` | Gestor de unidade |
| `UserRole.chefe_imediato` | Chefia imediata |
| `UserRole.servidor` | Servidor |

---

## 10. O que NÃO fazer

- **Não criar tela de login** — o backend cuida disso; o SvelteKit só redireciona para `/auth/login/google`
- **Não criar CRUD de usuários** — está fora do MVP (RF-025 parcial)
- **Não implementar notificações por e-mail** — o backend já cuida; o frontend só exibe o inbox de notificações
- **Não expor IDs internos (UUID)** ao usuário — usar nome, matrícula, período como identificadores visíveis
- **Não usar inglês** em nenhum label, mensagem, ou rótulo de navegação
- **Não mostrar o `/docs` do Swagger** para usuários finais — é só para developers

---

## 11. Sequência de Build Recomendada

1. **Setup SvelteKit** + graphql-codegen + cliente GraphQL (urql ou HOUDINI)
2. **Layout base** com sidebar de navegação adaptada ao papel (`me.role`)
3. **Tela 2 (Meu Plano)** — leitura simples, sem formulário → valida integração GraphQL
4. **Tela 3 (Registrar Execução)** — primeiro formulário → valida mutation
5. **Tela 4 (Lista Equipe)** → Tela 5 (Detalhe) → Tela 6 (Avaliar)
6. **Tela 1 (Dashboard)** — depois das demais, porque agrega dados de todas
7. **P1 e P2** na sequência
