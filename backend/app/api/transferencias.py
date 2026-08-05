from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Emisor, Transferencia
from app.schemas import (
    EmisionLoteIn,
    FacturaOut,
    ResultadoTransferencia,
    TransferenciaOut,
    TransferenciaUpdate,
)
from app.services.emisores import emisor_actual
from app.services.facturacion import (
    RequiereConfirmacionError,
    SinCuitError,
    emitir_factura,
)

router = APIRouter(prefix="/api/transferencias", tags=["transferencias"])


def _obtener(db: Session, transferencia_id: int, emisor: Emisor) -> Transferencia:
    transferencia = db.get(Transferencia, transferencia_id)
    if transferencia is None or transferencia.emisor_id != emisor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transferencia no encontrada")
    return transferencia


@router.get("", response_model=list[TransferenciaOut])
def listar(
    estado: str | None = None,
    lote_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> list[TransferenciaOut]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    consulta = (
        select(Transferencia)
        .where(Transferencia.emisor_id == emisor.id)
        .order_by(Transferencia.fecha.desc(), Transferencia.id.desc())
    )
    if estado:
        consulta = consulta.where(Transferencia.estado == estado)
    if lote_id:
        consulta = consulta.where(Transferencia.lote_id == lote_id)
    consulta = consulta.limit(limit).offset(offset)
    return [TransferenciaOut.model_validate(t) for t in db.scalars(consulta).all()]


@router.patch("/{transferencia_id}", response_model=TransferenciaOut)
def actualizar(
    transferencia_id: int,
    datos: TransferenciaUpdate,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> TransferenciaOut:
    transferencia = _obtener(db, transferencia_id, emisor)
    if transferencia.estado == "facturada":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La transferencia ya fue facturada y no puede modificarse"
        )
    if datos.cuit is not None:
        transferencia.cuit = datos.cuit
    if datos.estado is not None:
        transferencia.estado = datos.estado
    db.commit()
    db.refresh(transferencia)
    return TransferenciaOut.model_validate(transferencia)


@router.post("/{transferencia_id}/facturar", response_model=FacturaOut)
def facturar(
    transferencia_id: int,
    confirmar: bool = False,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> FacturaOut:
    transferencia = _obtener(db, transferencia_id, emisor)
    try:
        factura = emitir_factura(db, transferencia, emisor, confirmar_bajo_minimo=confirmar)
    except SinCuitError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except RequiereConfirmacionError as exc:
        # 409: el importe no supera el mínimo; reintentar con ?confirmar=true para facturar igual.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return FacturaOut.model_validate(factura)


@router.post("/facturar", response_model=list[ResultadoTransferencia])
def facturar_lote(
    datos: EmisionLoteIn,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> list[ResultadoTransferencia]:
    """Emite un lote y devuelve el resultado de CADA transferencia (no oculta lo omitido)."""
    resultados: list[ResultadoTransferencia] = []
    for tid in datos.transferencia_ids:
        transferencia = _obtener(db, tid, emisor)
        try:
            factura = emitir_factura(
                db, transferencia, emisor, confirmar_bajo_minimo=datos.confirmar_bajo_minimo
            )
        except SinCuitError as exc:
            resultados.append(
                ResultadoTransferencia(transferencia_id=tid, estado="sin_cuit", mensaje=str(exc))
            )
            continue
        except RequiereConfirmacionError as exc:
            resultados.append(
                ResultadoTransferencia(
                    transferencia_id=tid, estado="requiere_confirmacion", mensaje=str(exc)
                )
            )
            continue
        resultados.append(
            ResultadoTransferencia(
                transferencia_id=tid,
                estado=factura.estado,
                mensaje=factura.error,
                factura=FacturaOut.model_validate(factura),
            )
        )
    return resultados
