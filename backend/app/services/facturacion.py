"""Orquesta la emisión de facturas en ARCA a partir de transferencias recibidas."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Factura, Transferencia
from app.services.arca import get_facturador, get_padron
from app.services.arca.padron import DatosPadron
from app.services.arca.wsaa import ErrorArca
from app.services.arca.wsfe import SolicitudFactura


class SinCuitError(ValueError):
    pass


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


def emitir_factura(db: Session, transferencia: Transferencia) -> Factura:
    """Emite (una sola vez) la factura de una transferencia y persiste el resultado."""
    settings = get_settings()
    if transferencia.factura is not None and transferencia.factura.estado == "emitida":
        return transferencia.factura
    if not transferencia.cuit:
        raise SinCuitError(
            "La transferencia no tiene CUIT del emisor: complételo antes de facturar."
        )

    factura = transferencia.factura or Factura(
        transferencia_id=transferencia.id,
        cuit_receptor=transferencia.cuit,
        concepto_descripcion=settings.arca_concepto_descripcion,
        tipo_comprobante=settings.arca_tipo_comprobante,
        punto_venta=settings.arca_punto_venta,
        importe=transferencia.importe,
        fecha_comprobante=transferencia.fecha,
    )
    factura.cuit_receptor = transferencia.cuit

    try:
        datos, _ = consultar_padron(transferencia.cuit)
        factura.razon_social = datos.razon_social
        factura.domicilio = datos.domicilio
        transferencia.razon_social = datos.razon_social
        transferencia.domicilio = datos.domicilio

        resultado = get_facturador().emitir(
            SolicitudFactura(
                cuit_receptor=transferencia.cuit,
                importe=transferencia.importe,
                fecha=transferencia.fecha,
                punto_venta=settings.arca_punto_venta,
                tipo_comprobante=settings.arca_tipo_comprobante,
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
    transferencia.estado = "facturada"
    db.add(factura)
    db.commit()
    db.refresh(factura)
    return factura
