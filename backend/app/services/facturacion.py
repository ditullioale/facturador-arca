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
from app.services.arca.wsfe import ResultadoDesconocido, SolicitudFactura


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


def _auditar(db: Session, factura: Factura, operacion: str, resultado: str) -> None:
    from app.models import AuditoriaArca

    s = get_settings()
    db.add(
        AuditoriaArca(
            factura_id=factura.id,
            operacion=operacion,
            modo=s.arca_mode,
            emisor_cuit=factura.emisor_cuit or (s.arca_cuit or None),
            receptor_cuit=factura.cuit_receptor,
            punto_venta=factura.punto_venta,
            tipo_comprobante=factura.tipo_comprobante,
            numero=factura.numero or factura.numero_intentado,
            importe=factura.importe,
            resultado=resultado,
            cae=factura.cae,
            mensaje=(factura.error or None),
        )
    )


def _finalizar(db: Session, factura: Factura, operacion: str, resultado: str) -> Factura:
    db.add(factura)
    db.flush()  # asegura factura.id para la auditoría
    _auditar(db, factura, operacion, resultado)
    db.commit()
    db.refresh(factura)
    return factura


def _emitir_en_arca(
    db: Session, factura: Factura, condicion_iva_receptor: int
) -> Factura:
    """Pide el CAE a ARCA para una `Factura` ya armada y persiste el resultado.

    Idempotencia anti-duplicado: si un intento anterior quedó con resultado desconocido
    (timeout), antes de reintentar se consulta a ARCA (FECompConsultar) si ese número ya
    fue autorizado; si lo fue, se adopta el CAE en vez de emitir de nuevo.
    """
    facturador = get_facturador()

    if factura.numero_intentado:
        try:
            recon = facturador.consultar(
                factura.punto_venta, factura.tipo_comprobante, factura.numero_intentado
            )
        except ErrorArca:
            # No se pudo verificar: se mantiene en "revisar" (no se reintenta a ciegas).
            factura.estado = "revisar"
            return _finalizar(db, factura, "reconciliar", "revisar")
        if recon is not None:
            factura.numero = recon.numero
            factura.cae = recon.cae
            factura.cae_vencimiento = recon.cae_vencimiento
            factura.estado = "emitida"
            factura.error = None
            factura.numero_intentado = None
            return _finalizar(db, factura, "reconciliar", "reconciliada")
        # No existía en ARCA: es seguro reintentar.
        factura.numero_intentado = None

    try:
        resultado = facturador.emitir(
            SolicitudFactura(
                cuit_receptor=factura.cuit_receptor,
                importe=factura.importe,
                fecha=factura.fecha_comprobante,
                punto_venta=factura.punto_venta,
                tipo_comprobante=factura.tipo_comprobante,
                condicion_iva_receptor=condicion_iva_receptor,
            )
        )
    except ResultadoDesconocido as exc:
        factura.estado = "revisar"
        factura.numero_intentado = exc.numero
        factura.error = (
            "Resultado desconocido (timeout de ARCA): se reconciliará con FECompConsultar "
            "antes de reintentar para no duplicar."
        )
        return _finalizar(db, factura, "emitir", "revisar")
    except (ErrorArca, ValueError) as exc:
        factura.estado = "error"
        factura.error = str(exc)[:1000]
        factura.numero_intentado = None
        return _finalizar(db, factura, "emitir", "error")

    factura.numero = resultado.numero
    factura.cae = resultado.cae
    factura.cae_vencimiento = resultado.cae_vencimiento
    factura.estado = "emitida"
    factura.error = None
    factura.numero_intentado = None
    return _finalizar(db, factura, "emitir", "emitida")


def _padron_seguro(cuit: str) -> tuple[str | None, str | None]:
    """Consulta el padrón sin frenar la emisión: si falla (típico en homologación),
    devuelve datos vacíos con el domicilio por defecto. El domicilio no se envía a
    ARCA (solo se usa en la representación impresa), así que no es crítico."""
    settings = get_settings()
    if not settings.arca_consultar_padron:
        return None, settings.domicilio_default
    try:
        datos, _ = consultar_padron(cuit)
        return datos.razon_social, datos.domicilio
    except ErrorArca:
        return None, settings.domicilio_default


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

    razon_social, domicilio = _padron_seguro(transferencia.cuit)
    factura.razon_social = razon_social
    factura.domicilio = domicilio
    transferencia.razon_social = razon_social
    transferencia.domicilio = domicilio

    factura = _emitir_en_arca(db, factura, settings.arca_cond_iva_receptor)
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
    condicion_iva_receptor: int | None = None,
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
        p_razon, p_dom = _padron_seguro(receptor_cuit)
        razon_social = razon_social or p_razon
        domicilio = domicilio or p_dom

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

    condicion = condicion_iva_receptor or settings.arca_cond_iva_receptor
    return _emitir_en_arca(db, factura, condicion)


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
