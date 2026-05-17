"""Lista canônica de personas de demonstração.

Fonte de verdade para a tela /login do portal em modo demo.
Espelha as 10 personas do bundle de design v2 (handoff-landing-v2.md §5).

Grupos:
- `recomendados`: 4 personas com estados mais ricos para começar (servidor sem plano,
  servidor com plano em execução, chefia com pendência, gestor)
- `servidor`: outros 4 servidores com estados específicos (rascunho, aguardando
  assinatura, avaliação pendente, nota 2 + afastamento)
- `chefia`: chefia secundária com plano aguardando assinatura
- `outros`: admin com erros de sync

Em produção real (`ENVIRONMENT=production`) o endpoint /auth/personas-demo retorna
404 — esta lista nunca é exposta.
"""

PERSONAS_DEMO: list[dict] = [
    # ── Recomendados (Comece por aqui) ───────────────────────────────────────
    {
        "email": "servidor7@pgd-demo.gov.br",
        "name": "Marta Silva",
        "role": "servidor",
        "role_label": "Servidora",
        "ctx": "Sem plano — pode criar do zero",
        "grupo": "recomendados",
    },
    {
        "email": "servidor1@pgd-demo.gov.br",
        "name": "Ana Silva",
        "role": "servidor",
        "role_label": "Servidor",
        "ctx": "Plano em execução; tem plano anterior para clonar",
        "grupo": "recomendados",
    },
    {
        "email": "chefe1@pgd-demo.gov.br",
        "name": "Carlos Souza",
        "role": "chefe_imediato",
        "role_label": "Chefia",
        "ctx": "Tem recurso pendente para responder",
        "grupo": "recomendados",
    },
    {
        "email": "gestor@pgd-demo.gov.br",
        "name": "Maria Fernanda",
        "role": "gestor_unidade",
        "role_label": "Gestor",
        "ctx": "Aprova Plano de Entregas; vê conformidade",
        "grupo": "recomendados",
    },
    # ── Servidores (mais personas) ───────────────────────────────────────────
    {
        "email": "servidor4@pgd-demo.gov.br",
        "name": "Lucas Ramos",
        "role": "servidor",
        "role_label": "Servidor",
        "ctx": "Plano em rascunho (ainda editando)",
        "grupo": "servidor",
    },
    {
        "email": "servidor6@pgd-demo.gov.br",
        "name": "Felipe Costa",
        "role": "servidor",
        "role_label": "Servidor",
        "ctx": "Chefia ajustou — aguarda assinatura dele",
        "grupo": "servidor",
    },
    {
        "email": "servidor2@pgd-demo.gov.br",
        "name": "João Santos",
        "role": "servidor",
        "role_label": "Servidor",
        "ctx": "Avaliação aguardando + convocação pendente",
        "grupo": "servidor",
    },
    {
        "email": "servidor3@pgd-demo.gov.br",
        "name": "Carla Mendes",
        "role": "servidor",
        "role_label": "Servidora",
        "ctx": "Avaliação nota 2; afastamento encerrado",
        "grupo": "servidor",
    },
    # ── Chefia ───────────────────────────────────────────────────────────────
    {
        "email": "chefe2@pgd-demo.gov.br",
        "name": "Beatriz Lima",
        "role": "chefe_imediato",
        "role_label": "Chefia",
        "ctx": "Plano do Pedro aguardando assinatura dela",
        "grupo": "chefia",
    },
    # ── Outros ───────────────────────────────────────────────────────────────
    {
        "email": "admin@pgd-demo.gov.br",
        "name": "Roberto Admin",
        "role": "admin",
        "role_label": "Admin",
        "ctx": "Vê todos os erros de sync com API Central",
        "grupo": "outros",
    },
]
