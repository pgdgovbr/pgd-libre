"""add_api_sincronizado_em_to_participante

Revision ID: c92a18ac4ca9
Revises: d348a38ef5f2
Create Date: 2026-05-13 17:43:43.048692

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c92a18ac4ca9"
down_revision: Union[str, None] = "d348a38ef5f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "participantes",
        sa.Column("api_sincronizado_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("participantes", "api_sincronizado_em")
