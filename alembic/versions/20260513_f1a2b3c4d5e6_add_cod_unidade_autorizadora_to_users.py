"""add_cod_unidade_autorizadora_to_users

Revision ID: f1a2b3c4d5e6
Revises: c92a18ac4ca9
Create Date: 2026-05-13 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "c92a18ac4ca9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("cod_unidade_autorizadora", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "cod_unidade_autorizadora")
