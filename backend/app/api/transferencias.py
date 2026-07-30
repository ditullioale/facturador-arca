from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Transferencia
from app.schemas import (
    EmisionLoteIn,
    FacturaOut,
    TransferenciaOut,
    TransferenciaUpdate,
)
from app.services.facturacion import SinCuitError, emitir_factura

router = APIRouter(prefix="/api/transferencias", tags=["transferencias"])


def _obtener(db: Session, transferencia_id: int) -> Transferencia:
    transferencia = db.get(Transferencia, transferencia_id)
    if transferencia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transferencia no encontrada")
    return transferencia


@router.get("", response_model=list[TransferenciaOut])
def listar(
    estado: str | None = None,
    lote_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[TransferenciaOut]:
    consulta = select(Transferencia).order_by(Transferencia.fecha.desc(), Transferencia.id.desc())
    if estado:
        consulta = consulta.where(Transferencia.estado == estado)
    if lote_id:
        consulta = consulta.where(Transferencia.lote_id == lote_id)
    return [TransferenciaOut.model_validate(t) for t in db.scalars(consulta).all()]


@router.patch("/{transferencia_id}", response_model=TransferenciaOut)
def actualizar(
    transferencia_id: int, datos: TransferenciaUpdate, db: Session = Depends(get_db)
) -> TransferenciaOut:
    transferencia = _obtener(db, transferencia_id)
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
def facturar(transferencia_id: int, db: Session = Depends(get_db)) -> FacturaOut:
    transferencia = _obtener(db, transferencia_id)
    try:
        factura = emitir_factura(db, transferencia)
    except SinCuitError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return FacturaOut.model_validate(factura)


@router.post("/facturar", response_model=list[FacturaOut])
def facturar_lote(datos: EmisionLoteIn, db: Session = Depends(get_db)) -> list[FacturaOut]:
    facturas: list[FacturaOut] = []
    for transferencia_id in datos.transferencia_ids:
        transferencia = _obtener(db, transferencia_id)
        try:
            facturas.append(FacturaOut.model_validate(emitir_factura(db, transferencia)))
        except SinCuitError:
            continue
    return facturas
