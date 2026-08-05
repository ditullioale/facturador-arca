from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lote, Transferencia
from app.schemas import LoteOut, ResultadoImportacion, TransferenciaOut
from app.services.resumen_parser import ErrorDeParseo, parsear_resumen

router = APIRouter(prefix="/api/lotes", tags=["lotes"])

EXTENSIONES = (".xlsx", ".xlsm", ".xls", ".csv", ".pdf")


@router.post("", response_model=ResultadoImportacion, status_code=status.HTTP_201_CREATED)
async def importar_resumen(
    archivo: UploadFile = File(...), db: Session = Depends(get_db)
) -> ResultadoImportacion:
    nombre = archivo.filename or "resumen.xlsx"
    if not nombre.lower().endswith(EXTENSIONES):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Formato no soportado. Se aceptan: {', '.join(EXTENSIONES)}",
        )
    contenido = await archivo.read()
    try:
        resultado = parsear_resumen(contenido, nombre)
    except ErrorDeParseo as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    lote = Lote(
        nombre_archivo=nombre,
        banco=resultado.banco,
        cantidad_filas=resultado.cantidad_filas,
        cantidad_transferencias=len(resultado.movimientos),
        archivo=contenido,
        content_type=archivo.content_type,
    )
    db.add(lote)
    db.flush()

    existentes = set(
        db.scalars(
            select(Transferencia.huella).where(
                Transferencia.huella.in_([m.huella for m in resultado.movimientos] or [""])
            )
        )
    )
    nuevas: list[Transferencia] = []
    duplicadas = 0
    for movimiento in resultado.movimientos:
        if movimiento.huella in existentes:
            duplicadas += 1
            continue
        existentes.add(movimiento.huella)
        nuevas.append(
            Transferencia(
                lote_id=lote.id,
                banco=resultado.banco,
                fecha=movimiento.fecha,
                cuit=movimiento.cuit,
                importe=movimiento.importe,
                descripcion=movimiento.descripcion,
                huella=movimiento.huella,
            )
        )
    db.add_all(nuevas)
    db.commit()
    db.refresh(lote)

    return ResultadoImportacion(
        lote=LoteOut.model_validate(lote),
        nuevas=len(nuevas),
        duplicadas=duplicadas,
        sin_cuit=sum(1 for t in nuevas if not t.cuit),
        transferencias=[TransferenciaOut.model_validate(t) for t in nuevas],
    )


@router.get("", response_model=list[LoteOut])
def listar_lotes(
    limit: int = 50, offset: int = 0, db: Session = Depends(get_db)
) -> list[LoteOut]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    lotes = db.scalars(
        select(Lote).order_by(Lote.id.desc()).limit(limit).offset(offset)
    ).all()
    return [LoteOut.model_validate(lote) for lote in lotes]
