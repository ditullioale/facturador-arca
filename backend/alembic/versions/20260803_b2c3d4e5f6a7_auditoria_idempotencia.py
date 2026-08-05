"""auditoría, idempotencia (numero_intentado) y archivo original del lote

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-03 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("facturas", sa.Column("numero_intentado", sa.Integer(), nullable=True))
    op.add_column("lotes", sa.Column("archivo", sa.LargeBinary(), nullable=True))
    op.add_column("lotes", sa.Column("content_type", sa.String(length=120), nullable=True))
    op.create_table(
        "auditoria_arca",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factura_id", sa.Integer(), nullable=True),
        sa.Column("operacion", sa.String(length=32), nullable=False),
        sa.Column("modo", sa.String(length=16), nullable=False),
        sa.Column("emisor_cuit", sa.String(length=11), nullable=True),
        sa.Column("receptor_cuit", sa.String(length=11), nullable=True),
        sa.Column("punto_venta", sa.Integer(), nullable=True),
        sa.Column("tipo_comprobante", sa.Integer(), nullable=True),
        sa.Column("numero", sa.Integer(), nullable=True),
        sa.Column("importe", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("resultado", sa.String(length=24), nullable=False),
        sa.Column("cae", sa.String(length=32), nullable=True),
        sa.Column("mensaje", sa.Text(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["factura_id"], ["facturas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("auditoria_arca")
    op.drop_column("lotes", "content_type")
    op.drop_column("lotes", "archivo")
    op.drop_column("facturas", "numero_intentado")
