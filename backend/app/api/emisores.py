"""Alta y gestión de emisores (multiempresa). Protegido por FACTURADOR_ADMIN_TOKEN.

Lo llama el gestor (server-to-server) cuando una inmobiliaria carga su certificado.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Emisor
from app.schemas import EmisorAltaIn, EmisorOut, EmisorTokenOut
from app.services.cuit import es_cuit_valido, solo_digitos
from app.services.emisores import b64_a_bytes, registrar_emisor

router = APIRouter(prefix="/api/emisores", tags=["emisores"])


def _requiere_admin(x_admin_token: str | None = Header(default=None)) -> None:
    esperado = get_settings().facturador_admin_token
    if not esperado or x_admin_token != esperado:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de administrador inválido.")


@router.post("", response_model=EmisorTokenOut, dependencies=[Depends(_requiere_admin)])
def alta_emisor(datos: EmisorAltaIn, db: Session = Depends(get_db)) -> EmisorTokenOut:
    cuit = solo_digitos(datos.cuit)
    if not es_cuit_valido(cuit):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CUIT inválido")
    if datos.arca_mode not in ("mock", "homologacion", "produccion"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "arca_mode inválido")
    emisor, token = registrar_emisor(
        db,
        cuit=cuit,
        cert_bytes=b64_a_bytes(datos.cert_b64),
        key_bytes=b64_a_bytes(datos.key_b64),
        punto_venta=datos.punto_venta,
        tipo_comprobante=datos.tipo_comprobante,
        arca_mode=datos.arca_mode,
        razon_social=datos.razon_social,
        consultar_padron=datos.consultar_padron,
    )
    return EmisorTokenOut(emisor=EmisorOut.model_validate(emisor), token=token)


@router.get("", response_model=list[EmisorOut], dependencies=[Depends(_requiere_admin)])
def listar_emisores(db: Session = Depends(get_db)) -> list[EmisorOut]:
    emisores = db.scalars(select(Emisor).order_by(Emisor.id.desc())).all()
    return [EmisorOut.model_validate(e) for e in emisores]
