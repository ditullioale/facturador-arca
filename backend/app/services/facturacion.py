"""Orquesta la emisión de facturas en ARCA (multiempresa: cada emisor con su certificado).

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
from app.models import Emisor, Factura, Transferencia
from app.services.arca.factory import get_facturador_para, get_padron_para
from app.services.arca.padron import DatosPadron
from app.services.arca.wsaa import ErrorArca
from app.services.arca.wsfe import ResultadoDesconocido, SolicitudFactura


class SinCuitError(ValueError):
    pass


class RequiereConfirmacionError(ValueError):
    """El importe no supera el mínimo: hay que confirmar si se factura igual."""


class EmisorInvalidoError(ValueError):
    """El CUIT emisor pedido no coincide con el del token/credenciales."""


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


def consultar_padron(cuit: str, emisor: Emisor) -> tuple[DatosPadron, bool]:
    """Consulta el padrón (con el certificado del emisor) y completa el domicilio por defecto."""
    settings = get_settings()
    datos = get_padron_para(emisor).consultar(cuit)
    autocompletado = not (datos.domicilio or "").strip()
    if autocompletado:
        datos = DatosPadron(
            cuit=datos.cuit,
            razon_social=datos.razon_social,
            domicilio=settings.domicilio_default,
        )
    return datos, autocompletado


def _padron_seguro(cuit: str, emisor: Emisor) -> tuple[str | None, str | None]:
    """Consulta el padrón sin frenar la emisión: si falla (típico en homologación),
    devuelve datos vacíos con el domicilio por defecto. El domicilio no se envía a
    ARCA (solo se usa en la representación impresa), así que no es crítico."""
    settings = get_settings()
    if not emisor.consultar_padron:
        return None, settings.domicilio_default
    try:
        datos, _ = consultar_padron(cuit, emisor)
        return datos.razon_social, datos.domicilio
    except Exception:  # noqa: BLE001 - el padrón NUNCA debe frenar la emisión
        # Típico en producción si no se autorizó el web service de padrón (solo wsfe),
        # o en homologación donde suele estar caído. El domicilio no se envía a ARCA.
        return None, settings.domicilio_default


def _auditar(db: Session, factura: Factura, emisor: Emisor, operacion: str, resultado: str) -> None:
    from app.models import AuditoriaArca

    db.add(
        AuditoriaArca(
            factura_id=factura.id,
            emisor_id=emisor.id,
            operacion=operacion,
            modo=emisor.arca_mode,
            emisor_cuit=emisor.cuit,
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


def _finalizar(
    db: Session, factura: Factura, emisor: Emisor, operacion: str, resultado: str
) -> Factura:
    db.add(factura)
    db.flush()  # asegura factura.id para la auditoría
    _auditar(db, factura, emisor, operacion, resultado)
    db.commit()
    db.refresh(factura)
    return factura


def _emitir_en_arca(
    db: Session, factura: Factura, emisor: Emisor, condicion_iva_receptor: int
) -> Factura:
    """Pide el CAE a ARCA (con el certificado del emisor) y persiste el resultado.

    Idempotencia anti-duplicado: si un intento anterior quedó con resultado desconocido
    (timeout), antes de reintentar se consulta a ARCA (FECompConsultar) si ese número ya
    fue autorizado; si lo fue, se adopta el CAE en vez de emitir de nuevo.
    """
    facturador = get_facturador_para(emisor)

    if factura.numero_intentado:
        try:
            recon = facturador.consultar(
                factura.punto_venta, factura.tipo_comprobante, factura.numero_intentado
            )
        except ErrorArca:
            factura.estado = "revisar"
            return _finalizar(db, factura, emisor, "reconciliar", "revisar")
        if recon is not None:
            factura.numero = recon.numero
            factura.cae = recon.cae
            factura.cae_vencimiento = recon.cae_vencimiento
            factura.estado = "emitida"
            factura.error = None
            factura.numero_intentado = None
            return _finalizar(db, factura, emisor, "reconciliar", "reconciliada")
        factura.numero_intentado = None  # no existía en ARCA: reintentar es seguro

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
        return _finalizar(db, factura, emisor, "emitir", "revisar")
    except (ErrorArca, ValueError) as exc:
        factura.estado = "error"
        factura.error = str(exc)[:1000]
        factura.numero_intentado = None
        return _finalizar(db, factura, emisor, "emitir", "error")

    factura.numero = resultado.numero
    factura.cae = resultado.cae
    factura.cae_vencimiento = resultado.cae_vencimiento
    factura.estado = "emitida"
    factura.error = None
    factura.numero_intentado = None
    return _finalizar(db, factura, emisor, "emitir", "emitida")


def emitir_factura(
    db: Session,
    transferencia: Transferencia,
    emisor: Emisor,
    confirmar_bajo_minimo: bool = False,
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
        emisor_id=emisor.id,
        origen="resumen_bancario",
        emisor_cuit=emisor.cuit,
        cuit_receptor=transferencia.cuit,
        concepto_descripcion=settings.arca_concepto_descripcion,
        tipo_comprobante=emisor.tipo_comprobante,
        punto_venta=emisor.punto_venta,
        importe=transferencia.importe,
        fecha_comprobante=transferencia.fecha,
    )
    factura.emisor_id = emisor.id
    factura.emisor_cuit = emisor.cuit
    factura.cuit_receptor = transferencia.cuit

    razon_social, domicilio = _padron_seguro(transferencia.cuit, emisor)
    factura.razon_social = razon_social
    factura.domicilio = domicilio
    transferencia.razon_social = razon_social
    transferencia.domicilio = domicilio

    factura = _emitir_en_arca(db, factura, emisor, settings.arca_cond_iva_receptor)
    if factura.estado == "emitida":
        transferencia.estado = "facturada"
        db.add(transferencia)
        db.commit()
        db.refresh(factura)
    return factura


def emitir_factura_directa(
    db: Session,
    emisor: Emisor,
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
    referencia (del mismo emisor) se devuelve la misma, sin volver a pedir CAE.
    """
    settings = get_settings()

    existente = db.scalar(
        select(Factura).where(
            Factura.referencia_externa == referencia_externa,
            Factura.emisor_id == emisor.id,
        )
    )
    if existente is not None and existente.estado == "emitida":
        return existente

    if emisor_cuit and emisor_cuit != emisor.cuit:
        raise EmisorInvalidoError(
            f"El emisor {emisor_cuit} no coincide con el del token ({emisor.cuit})."
        )
    _validar_minimo(importe, confirmar_bajo_minimo)

    if not razon_social or not domicilio:
        p_razon, p_dom = _padron_seguro(receptor_cuit, emisor)
        razon_social = razon_social or p_razon
        domicilio = domicilio or p_dom

    factura = existente or Factura(
        transferencia_id=None,
        emisor_id=emisor.id,
        origen=origen,
        referencia_externa=referencia_externa,
    )
    factura.emisor_id = emisor.id
    factura.emisor_cuit = emisor.cuit
    factura.cuit_receptor = receptor_cuit
    factura.razon_social = razon_social
    factura.domicilio = domicilio
    factura.concepto_descripcion = concepto_descripcion or settings.arca_concepto_descripcion
    factura.tipo_comprobante = emisor.tipo_comprobante
    factura.punto_venta = emisor.punto_venta
    factura.importe = Decimal(importe)
    factura.fecha_comprobante = fecha

    condicion = condicion_iva_receptor or settings.arca_cond_iva_receptor
    return _emitir_en_arca(db, factura, emisor, condicion)


def reconciliar_pendientes(db: Session, emisor: Emisor, limite: int = 50) -> list[Factura]:
    """Resuelve las facturas que quedaron en "revisar" por un timeout de ARCA.

    Una factura en "revisar" guarda el `numero_intentado`: ARCA pudo haberla autorizado
    sin que llegara la respuesta. Hasta que alguien la retome queda colgada — el
    comprobante puede existir allá y no acá. Esto la retoma: `_emitir_en_arca` consulta
    primero con FECompConsultar y adopta el CAE si ya existía; sólo emite de nuevo cuando
    confirmó que ese número NO fue autorizado, así que no puede duplicar.

    Pensado para llamarse desde un cron. Devuelve las facturas procesadas con su estado
    ya actualizado (las que siguen en "revisar" no se pudieron resolver todavía).
    """
    condicion = get_settings().arca_cond_iva_receptor
    pendientes = list(
        db.scalars(
            select(Factura)
            .where(Factura.emisor_id == emisor.id, Factura.estado == "revisar")
            .order_by(Factura.id)
            .limit(limite)
        )
    )
    resueltas = []
    for factura in pendientes:
        procesada = _emitir_en_arca(db, factura, emisor, condicion)
        if procesada.estado == "emitida" and procesada.transferencia is not None:
            procesada.transferencia.estado = "facturada"
            db.commit()
            db.refresh(procesada)
        resueltas.append(procesada)
    return resueltas
