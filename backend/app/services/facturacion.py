"""Orquesta la emisión de facturas en ARCA.

Dos orígenes posibles:

- **Resumen bancario:** una `Transferencia` recibida se factura como honorarios.
- **Gestor de alquileres:** una liquidación al propietario dispara la factura de la
  comisión de la inmobiliaria (emisión directa, sin transferencia asociada).

Regla de negocio común: solo se emite cuando el importe **supera** el mínimo
configurado (`ARCA_IMPORTE_MINIMO`, $50.000 por defecto). Por debajo, la app pide
confirmación explícita ("¿se factura o no?") mediante `confirmar_bajo_minimo=True`.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Factura, Transferencia
from app.services.arca import get_facturador, get_padron
from app.services.arca.padron import DatosPadron
from app.services.arca.wsaa import ErrorArca
from app.services.arca.wsfe import SolicitudFactura


class SinCuitError(ValueError):
    pass


class RequiereConfirmacionError(ValueError):
    """El importe no supera el mínimo: hay que confirmar si se factura igual."""


class EmisorInvalidoError(ValueError):
    """El CUIT emisor pedido no coincide con las credenciales configuradas."""


def supera_minimo(importe: Decimal) -> bool:
    """True si el importe supera estrictamente el mínimo para facturar."""
    return Decimal(importe) > get_settings().arca_importe_minimo


def _validar_minimo(importe: Decimal, confirmar_bajo_minimo: bool) -> None:
    if not confirmar_bajo_minimo and not supera_minimo(importe):
        minimo = get_settings().arca_importe_minimo
        raise RequiereConfirmacionError(
            f"El importe ${importe} no supera el mínimo de ${minimo}. "
            "Confirmá si querés facturarlo igual."
        )


def consultar_padron(cuit: str) -> tuple[DatosPadron, bool]:
    """Consulta el padrón y completa el domicilio por defecto si ARCA no lo informa."""
    settings = get_settings()
    datos = get_padron().consultar(cuit)
    autocompletado = not (datos.domicilio or "").strip()
    if autocompletado:
        datos = DatosPadron(
            cuit=datos.cuit,
            razon_social=datos.razon_social,
            domicilio=settings.domicilio_default,
        )
    return datos, autocompletado


def _emitir_en_arca(db: Session, factura: Factura) -> Factura:
    """Pide el CAE a ARCA para una `Factura` ya armada y persiste el resultado."""
    try:
        resultado = get_facturador().emitir(
            SolicitudFactura(
                cuit_receptor=factura.cuit_receptor,
                importe=factura.importe,
                fecha=factura.fecha_comprobante,
                punto_venta=factura.punto_venta,
                tipo_comprobante=factura.tipo_comprobante,
            )
        )
    except (ErrorArca, ValueError) as exc:
        factura.estado = "error"
        factura.error = str(exc)[:1000]
        db.add(factura)
        db.commit()
        db.refresh(factura)
        return factura

    factura.numero = resultado.numero
    factura.cae = resultado.cae
    factura.cae_vencimiento = resultado.cae_vencimiento
    factura.estado = "emitida"
    factura.error = None
    db.add(factura)
    db.commit()
    db.refresh(factura)
    return factura


def emitir_factura(
    db: Session, transferencia: Transferencia, confirmar_bajo_minimo: bool = False
) -> Factura:
    """Emite (una sola vez) la factura de una transferencia y persiste el resultado."""
    settings = get_settings()
    if transferencia.factura is not None and transferencia.factura.estado == "emitida":
        return transferencia.factura
    if not transferencia.cuit:
        raise SinCuitError(
            "La transferencia no tiene CUIT del emisor: complételo antes de facturar."
        )
    _validar_minimo(transferencia.importe, confirmar_bajo_minimo)

    factura = transferencia.factura or Factura(
        transferencia_id=transferencia.id,
        origen="resumen_bancario",
        emisor_cuit=settings.arca_cuit or None,
        cuit_receptor=transferencia.cuit,
        concepto_descripcion=settings.arca_concepto_descripcion,
        tipo_comprobante=settings.arca_tipo_comprobante,
        punto_venta=settings.arca_punto_venta,
        importe=transferencia.importe,
        fecha_comprobante=transferencia.fecha,
    )
    factura.cuit_receptor = transferencia.cuit

    datos, _ = consultar_padron(transferencia.cuit)
    factura.razon_social = datos.razon_social
    factura.domicilio = datos.domicilio
    transferencia.razon_social = datos.razon_social
    transferencia.domicilio = datos.domicilio

    factura = _emitir_en_arca(db, factura)
    if factura.estado == "emitida":
        transferencia.estado = "facturada"
        db.add(transferencia)
        db.commit()
        db.refresh(factura)
    return factura


def emitir_factura_directa(
    db: Session,
    *,
    receptor_cuit: str,
    importe: Decimal,
    fecha,
    referencia_externa: str,
    emisor_cuit: str | None = None,
    concepto_descripcion: str | None = None,
    razon_social: str | None = None,
    domicilio: str | None = None,
    confirmar_bajo_minimo: bool = False,
    origen: str = "gestor_alquileres",
) -> Factura:
    """Emite una factura a partir de datos explícitos (integración con el gestor).

    Idempotente por `referencia_externa`: si ya existe una factura emitida con esa
    referencia se devuelve la misma, sin volver a pedir CAE.
    """
    settings = get_settings()

    existente = db.scalar(
        select(Factura).where(Factura.referencia_externa == referencia_externa)
    )
    if existente is not None and existente.estado == "emitida":
        return existente

    _validar_emisor(emisor_cuit)
    _validar_minimo(importe, confirmar_bajo_minimo)

    if not razon_social or not domicilio:
        datos, _ = consultar_padron(receptor_cuit)
        razon_social = razon_social or datos.razon_social
        domicilio = domicilio or datos.domicilio

    factura = existente or Factura(
        transferencia_id=None,
        origen=origen,
        referencia_externa=referencia_externa,
    )
    factura.emisor_cuit = emisor_cuit or settings.arca_cuit or None
    factura.cuit_receptor = receptor_cuit
    factura.razon_social = razon_social
    factura.domicilio = domicilio
    factura.concepto_descripcion = concepto_descripcion or settings.arca_concepto_descripcion
    factura.tipo_comprobante = settings.arca_tipo_comprobante
    factura.punto_venta = settings.arca_punto_venta
    factura.importe = Decimal(importe)
    factura.fecha_comprobante = fecha

    return _emitir_en_arca(db, factura)


def _validar_emisor(emisor_cuit: str | None) -> None:
    """En modo real el emisor pedido debe coincidir con las credenciales cargadas."""
    settings = get_settings()
    if settings.arca_mode == "mock" or not emisor_cuit:
        return
    if settings.arca_cuit and emisor_cuit != settings.arca_cuit:
        raise EmisorInvalidoError(
            f"El emisor {emisor_cuit} no coincide con el CUIT configurado "
            f"({settings.arca_cuit}). Esta instancia factura para un único emisor."
        )
