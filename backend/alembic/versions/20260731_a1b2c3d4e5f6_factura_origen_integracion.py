"""factura: origen, emisor y referencia externa (integración gestor)

Revision ID: a1b2c3d4e5f6
Revises: c08feca0ce74
Create Date: 2026-07-31 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c08feca0ce74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "facturas",
        sa.Column("origen", sa.String(length=32), nullable=False, server_default="resumen_bancario"),
    )
    op.add_column("facturas", sa.Column("emisor_cuit", sa.String(length=11), nullable=True))
    op.add_column(
        "facturas", sa.Column("referencia_externa", sa.String(length=120), nullable=True)
    )
    # La factura ahora puede no tener transferencia (facturas de liquidación).
    op.alter_column("facturas", "transferencia_id", existing_type=sa.Integer(), nullable=True)
    op.create_index(
        "ix_facturas_referencia_externa", "facturas", ["referencia_externa"], unique=False
    )
    op.create_unique_constraint(
        "uq_facturas_referencia_externa", "facturas", ["referencia_externa"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_facturas_referencia_externa", "facturas", type_="unique")
    op.drop_index("ix_facturas_referencia_externa", table_name="facturas")
    op.alter_column("facturas", "transferencia_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("facturas", "referencia_externa")
    op.drop_column("facturas", "emisor_cuit")
    op.drop_column("facturas", "origen")
