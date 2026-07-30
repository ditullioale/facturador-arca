from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Factura
from app.schemas import ConfigOut, DatosPadronOut, FacturaOut
from app.services.arca.wsaa import ErrorArca
from app.services.cuit import es_cuit_valido, solo_digitos
from app.services.facturacion import consultar_padron

router = APIRouter(prefix="/api", tags=["facturas"])


@router.get("/facturas", response_model=list[FacturaOut])
def listar_facturas(estado: str | None = None, db: Session = Depends(get_db)) -> list[FacturaOut]:
    consulta = select(Factura).order_by(Factura.id.desc())
    if estado:
        consulta = consulta.where(Factura.estado == estado)
    return [FacturaOut.model_validate(f) for f in db.scalars(consulta).all()]


@router.get("/padron/{cuit}", response_model=DatosPadronOut)
def consultar(cuit: str) -> DatosPadronOut:
    digitos = solo_digitos(cuit)
    if not es_cuit_valido(digitos):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CUIT inválido")
    try:
        datos, autocompletado = consultar_padron(digitos)
    except ErrorArca as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return DatosPadronOut(
        cuit=datos.cuit,
        razon_social=datos.razon_social,
        domicilio=datos.domicilio,
        domicilio_autocompletado=autocompletado,
    )


@router.get("/config", response_model=ConfigOut)
def configuracion() -> ConfigOut:
    s = get_settings()
    return ConfigOut(
        arca_mode=s.arca_mode,
        arca_cuit=s.arca_cuit,
        punto_venta=s.arca_punto_venta,
        tipo_comprobante=s.arca_tipo_comprobante,
        concepto_descripcion=s.arca_concepto_descripcion,
        domicilio_default=s.domicilio_default,
    )
