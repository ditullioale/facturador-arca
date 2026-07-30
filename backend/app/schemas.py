from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.cuit import es_cuit_valido, solo_digitos


class FacturaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transferencia_id: int
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
    domicilio_default: str
