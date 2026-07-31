"""Integración con sistemas externos (gestor de alquileres finart-alquileres).

Cuando el gestor genera una liquidación al propietario, llama a este endpoint para
emitir la factura de honorarios (comisión de la inmobiliaria) al propietario.
La operación es idempotente por `referencia_externa`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import FacturaLiquidacionIn, FacturaOut, ResultadoFacturacion
from app.services.arca.wsaa import ErrorArca
from app.services.facturacion import (
    EmisorInvalidoError,
    RequiereConfirmacionError,
    emitir_factura_directa,
)

router = APIRouter(prefix="/api/integracion", tags=["integracion"])


@router.post("/liquidacion", response_model=ResultadoFacturacion)
def facturar_liquidacion(
    datos: FacturaLiquidacionIn, db: Session = Depends(get_db)
) -> ResultadoFacturacion:
    try:
        factura = emitir_factura_directa(
            db,
            receptor_cuit=datos.receptor_cuit,
            importe=datos.importe,
            fecha=datos.fecha,
            referencia_externa=datos.referencia_externa,
            emisor_cuit=datos.emisor_cuit,
            concepto_descripcion=datos.concepto_descripcion,
            razon_social=datos.razon_social,
            domicilio=datos.domicilio,
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
