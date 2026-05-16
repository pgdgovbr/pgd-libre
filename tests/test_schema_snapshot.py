"""Snapshot do schema GraphQL.

Se o arquivo de snapshot NÃO existir → é criado e o teste passa (primeira execução).
Se o arquivo JÁ EXISTIR → o schema atual é comparado ao snapshot; diff ≠ falha explícita.

Isso garante que mudanças no schema (adição/remoção de campos, types, mutations) sejam
detectadas e revisadas explicitamente.

Para aceitar um diff intencional:
    rm tests/snapshots/schema.graphql
    pytest tests/test_schema_snapshot.py  # recria o snapshot
"""

import difflib
from pathlib import Path

import pytest

# Caminho do arquivo de snapshot
SNAPSHOT_FILE = Path(__file__).parent / "snapshots" / "schema.graphql"


def _get_schema_sdl() -> str:
    """Retorna o SDL atual do schema Strawberry."""
    from src.graphql.schema import schema

    return schema.as_str()


def test_schema_snapshot() -> None:
    """Compara o schema atual com o snapshot em tests/snapshots/schema.graphql.

    - Se o snapshot não existir: cria o arquivo e passa.
    - Se existir: compara linha a linha; falha se houver diferença.
    """
    current_sdl = _get_schema_sdl()

    # Garantir que o diretório existe
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not SNAPSHOT_FILE.exists():
        # Primeira execução: criar snapshot
        SNAPSHOT_FILE.write_text(current_sdl, encoding="utf-8")
        pytest.skip(f"Snapshot criado em {SNAPSHOT_FILE}. Execute o teste novamente para validar.")

    stored_sdl = SNAPSHOT_FILE.read_text(encoding="utf-8")

    if current_sdl == stored_sdl:
        return  # Sem mudanças — tudo certo

    # Gerar diff legível
    diff_lines = list(
        difflib.unified_diff(
            stored_sdl.splitlines(keepends=True),
            current_sdl.splitlines(keepends=True),
            fromfile="tests/snapshots/schema.graphql (snapshot)",
            tofile="schema atual",
            lineterm="",
        )
    )
    diff_text = "".join(diff_lines)

    pytest.fail(
        "Schema GraphQL mudou em relação ao snapshot!\n\n"
        "Se a mudança for intencional, atualize o snapshot com:\n"
        "    rm tests/snapshots/schema.graphql\n"
        "    pytest tests/test_schema_snapshot.py\n\n"
        f"Diff:\n{diff_text}"
    )


def test_schema_sdl_nao_vazio() -> None:
    """Sanity check: o schema SDL deve conter pelo menos as palavras-chave básicas."""
    sdl = _get_schema_sdl()
    assert "type Query" in sdl, "SDL não contém 'type Query'"
    assert "type Mutation" in sdl, "SDL não contém 'type Mutation'"
    assert "me" in sdl, "SDL não contém a query 'me'"


def test_schema_contem_mutations_criticas() -> None:
    """Garante que mutations críticas do sistema estão presentes no schema."""
    sdl = _get_schema_sdl()
    mutations_criticas = [
        "criarUnidadeAutorizadora",
        "registrarExecucao",
        "avaliarRegistrosExecucao",
        "abrirRecurso",
        "decidirRecurso",
        "criarPlanoTrabalho",
        "iniciarExecucaoPlanoTrabalho",
        "confirmarSelecao",
        "aprovarPlanoEntregas",
    ]
    ausentes = [m for m in mutations_criticas if m not in sdl]
    assert not ausentes, f"Mutations críticas ausentes do schema: {ausentes}"


def test_schema_contem_queries_criticas() -> None:
    """Garante que queries críticas estão no schema."""
    sdl = _get_schema_sdl()
    queries_criticas = [
        "listarParticipantes",
        "listarPlanosTrabalho",
        "listarPlanosEntregas",
        "painelConformidade",
        "resultadosPublicos",
    ]
    ausentes = [q for q in queries_criticas if q not in sdl]
    assert not ausentes, f"Queries críticas ausentes do schema: {ausentes}"
