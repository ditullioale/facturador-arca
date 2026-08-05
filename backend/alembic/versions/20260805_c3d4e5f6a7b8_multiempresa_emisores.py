"""multiempresa: tabla emisores y emisor_id en las tablas de datos

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-05 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "emisores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cuit", sa.String(length=11), nullable=False),
        sa.Column("razon_social", sa.String(length=255), nullable=True),
        sa.Column("punto_venta", sa.Integer(), nullable=False),
        sa.Column("tipo_comprobante", sa.Integer(), nullable=False),
        sa.Column("arca_mode", sa.String(length=16), nullable=False),
        sa.Column("consultar_padron", sa.Boolean(), nullable=False),
        sa.Column("cert_cifrado", sa.Text(), nullable=True),
        sa.Column("key_cifrado", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("por_defecto", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cuit", name="uq_emisores_cuit"),
        sa.UniqueConstraint("token_hash", name="uq_emisores_token_hash"),
    )
    op.create_index("ix_emisores_cuit", "emisores", ["cuit"])
    for tabla in ("lotes", "transferencias", "facturas", "auditoria_arca"):
        op.add_column(tabla, sa.Column("emisor_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{tabla}_emisor_id", tabla, ["emisor_id"])
        op.create_foreign_key(
            f"fk_{tabla}_emisor", tabla, "emisores", ["emisor_id"], ["id"]
        )


def downgrade() -> None:
    for tabla in ("auditoria_arca", "facturas", "transferencias", "lotes"):
        op.drop_constraint(f"fk_{tabla}_emisor", tabla, type_="foreignkey")
        op.drop_index(f"ix_{tabla}_emisor_id", table_name=tabla)
        op.drop_column(tabla, "emisor_id")
    op.drop_index("ix_emisores_cuit", table_name="emisores")
    op.drop_table("emisores")
