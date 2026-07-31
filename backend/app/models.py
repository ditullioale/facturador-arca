from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Lote(Base):
    """Un archivo de resumen bancario importado."""

    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_archivo: Mapped[str] = mapped_column(String(255))
    banco: Mapped[str] = mapped_column(String(32))
    cantidad_filas: Mapped[int] = mapped_column(default=0)
    cantidad_transferencias: Mapped[int] = mapped_column(default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transferencias: Mapped[list["Transferencia"]] = relationship(back_populates="lote")


class Transferencia(Base):
    """Transferencia recibida detectada en el resumen bancario."""

    __tablename__ = "transferencias"
    __table_args__ = (UniqueConstraint("huella", name="uq_transferencias_huella"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"))
    banco: Mapped[str] = mapped_column(String(32))
    fecha: Mapped[date]
    cuit: Mapped[str | None] = mapped_column(String(11), index=True)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    descripcion: Mapped[str] = mapped_column(String(500), default="")
    # Huella de deduplicación: evita facturar dos veces la misma transferencia
    # si se vuelve a importar el mismo resumen.
    huella: Mapped[str] = mapped_column(String(64))
    razon_social: Mapped[str | None] = mapped_column(String(255))
    domicilio: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[str] = mapped_column(String(16), default="pendiente")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lote: Mapped[Lote] = relationship(back_populates="transferencias")
    factura: Mapped["Factura | None"] = relationship(back_populates="transferencia")


class Factura(Base):
    """Comprobante emitido en ARCA para una transferencia."""

    __tablename__ = "facturas"
    __table_args__ = (
        UniqueConstraint("transferencia_id", name="uq_facturas_transferencia"),
        UniqueConstraint("referencia_externa", name="uq_facturas_referencia_externa"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # La factura puede originarse en una transferencia bancaria (resumen) o en una
    # liquidación del gestor de alquileres; por eso transferencia_id es opcional.
    transferencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("transferencias.id"), nullable=True
    )
    # "resumen_bancario" | "gestor_alquileres"
    origen: Mapped[str] = mapped_column(String(32), default="resumen_bancario")
    # CUIT del emisor (para integraciones multiempresa: cada inmobiliaria factura con el suyo).
    emisor_cuit: Mapped[str | None] = mapped_column(String(11))
    # Clave externa para idempotencia (ej. "gestor:<inmobiliaria>:<nro_liquidacion>").
    referencia_externa: Mapped[str | None] = mapped_column(String(120), index=True)
    cuit_receptor: Mapped[str] = mapped_column(String(11))
    razon_social: Mapped[str | None] = mapped_column(String(255))
    domicilio: Mapped[str | None] = mapped_column(String(255))
    concepto_descripcion: Mapped[str] = mapped_column(String(255))
    tipo_comprobante: Mapped[int]
    punto_venta: Mapped[int]
    numero: Mapped[int | None]
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    fecha_comprobante: Mapped[date]
    cae: Mapped[str | None] = mapped_column(String(32))
    cae_vencimiento: Mapped[date | None]
    estado: Mapped[str] = mapped_column(String(16), default="pendiente")
    error: Mapped[str | None] = mapped_column(String(1000))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transferencia: Mapped[Transferencia | None] = relationship(back_populates="factura")
