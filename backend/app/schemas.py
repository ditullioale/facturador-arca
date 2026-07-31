from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.services.cuit import es_cuit_valido, solo_digitos


class FacturaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transferencia_id: int | None
    origen: str
    emisor_cuit: str | None
    referencia_externa: str | None
    cuit_receptor: str
    razon_social: str | None
    domicilio: str | None
    concepto_descripcion: str
    tipo_comprobante: int
    punto_venta: int
    numero: int | None
    importe: Decimal
    fecha_comprobante: date
    cae: str | None
    cae_vencimiento: date | None
    estado: str
    error: str | None
    creado_en: datetime | None


class TransferenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lote_id: int
    banco: str
    fecha: date
    cuit: str | None
    importe: Decimal
    descripcion: str
    razon_social: str | None
    domicilio: str | None
    estado: str
    factura: FacturaOut | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supera_minimo(self) -> bool:
        from app.services.facturacion import supera_minimo

        return supera_minimo(self.importe)


class LoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_archivo: str
    banco: str
    cantidad_filas: int
    cantidad_transferencias: int
    creado_en: datetime | None


class ResultadoImportacion(BaseModel):
    lote: LoteOut
    nuevas: int
    duplicadas: int
    sin_cuit: int
    transferencias: list[TransferenciaOut]


class TransferenciaUpdate(BaseModel):
    cuit: str | None = None
    estado: str | None = None

    @field_validator("cuit")
    @classmethod
    def validar_cuit(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        digitos = solo_digitos(valor)
        if not es_cuit_valido(digitos):
            raise ValueError("CUIT inválido")
        return digitos

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, valor: str | None) -> str | None:
        if valor is not None and valor not in {"pendiente", "ignorada"}:
            raise ValueError("Estado inválido: use 'pendiente' o 'ignorada'")
        return valor


class EmisionLoteIn(BaseModel):
    transferencia_ids: list[int]
    confirmar_bajo_minimo: bool = False


class DatosPadronOut(BaseModel):
    cuit: str
    razon_social: str | None
    domicilio: str | None
    domicilio_autocompletado: bool


class ConfigOut(BaseModel):
    arca_mode: str
    arca_cuit: str
    punto_venta: int
    tipo_comprobante: int
    concepto_descripcion: str
    importe_minimo: Decimal
    domicilio_default: str


class FacturaLiquidacionIn(BaseModel):
    """Pedido de factura desde el gestor de alquileres (liquidación al propietario)."""

    receptor_cuit: str
    importe: Decimal
    fecha: date
    referencia_externa: str
    emisor_cuit: str | None = None
    concepto_descripcion: str | None = None
    razon_social: str | None = None
    domicilio: str | None = None
    condicion_iva_receptor: int | None = None
    confirmar_bajo_minimo: bool = False

    @field_validator("receptor_cuit", "emisor_cuit")
    @classmethod
    def validar_cuit(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        digitos = solo_digitos(valor)
        if not es_cuit_valido(digitos):
            raise ValueError("CUIT inválido")
        return digitos


class ResultadoFacturacion(BaseModel):
    """Respuesta de la integración: permite al gestor preguntar si factura o no."""

    estado: str  # emitida | error | requiere_confirmacion
    mensaje: str | None = None
    factura: FacturaOut | None = None
