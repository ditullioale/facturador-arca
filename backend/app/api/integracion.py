"""Integración con sistemas externos (gestor de alquileres finart-alquileres).

Cuando el gestor genera una liquidación al propietario, llama a este endpoint para
emitir la factura de honorarios (comisión de la inmobiliaria) al propietario.
La operación es idempotente por `referencia_externa`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Emisor, Factura
from app.schemas import FacturaLiquidacionIn, FacturaOut, ResultadoFacturacion
from app.services.arca.wsaa import ErrorArca
from app.services.emisores import emisor_actual
from app.services.facturacion import (
    EmisorInvalidoError,
    RequiereConfirmacionError,
    emitir_factura_directa,
)

router = APIRouter(prefix="/api/integracion", tags=["integracion"])


@router.post("/liquidacion", response_model=ResultadoFacturacion)
def facturar_liquidacion(
    datos: FacturaLiquidacionIn,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> ResultadoFacturacion:
    try:
        factura = emitir_factura_directa(
            db,
            emisor,
            receptor_cuit=datos.receptor_cuit,
            importe=datos.importe,
            fecha=datos.fecha,
            referencia_externa=datos.referencia_externa,
            emisor_cuit=datos.emisor_cuit,
            concepto_descripcion=datos.concepto_descripcion,
            razon_social=datos.razon_social,
            domicilio=datos.domicilio,
            condicion_iva_receptor=datos.condicion_iva_receptor,
            confirmar_bajo_minimo=datos.confirmar_bajo_minimo,
        )
    except RequiereConfirmacionError as exc:
        # No es un error: el gestor debe preguntar al usuario si factura igual.
        return ResultadoFacturacion(estado="requiere_confirmacion", mensaje=str(exc))
    except (EmisorInvalidoError, ErrorArca, ValueError) as exc:
        return ResultadoFacturacion(estado="error", mensaje=str(exc))

    return ResultadoFacturacion(
        estado=factura.estado,
        mensaje=factura.error,
        factura=FacturaOut.model_validate(factura),
    )


@router.get("/liquidacion", response_model=ResultadoFacturacion)
def consultar_liquidacion(
    referencia_externa: str,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> ResultadoFacturacion:
    """Reconciliación (Fase 6.3): devuelve el comprobante de esa referencia externa
    (del emisor del token), sin tener que traer todo el listado de facturas. Útil para
    resolver liquidaciones que en el gestor quedaron pendientes por un timeout pero que
    en realidad ya se emitieron. 404 si no existe ninguna para esa referencia."""
    factura = db.scalar(
        select(Factura).where(
            Factura.referencia_externa == referencia_externa,
            Factura.emisor_id == emisor.id,
        )
    )
    if factura is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No hay ningún comprobante para esa referencia externa.",
        )
    return ResultadoFacturacion(
        estado=factura.estado,
        mensaje=factura.error,
        factura=FacturaOut.model_validate(factura),
    )
