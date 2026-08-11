"""Alta y gestión de emisores (multiempresa). Protegido por FACTURADOR_ADMIN_TOKEN.

Lo llama el gestor (server-to-server) cuando una inmobiliaria carga su certificado.
"""
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Emisor, Factura
from app.schemas import (
    DiagnosticoEmisor,
    DiagnosticoOut,
    EmisorAltaIn,
    EmisorOut,
    EmisorTokenOut,
)
from app.services.cuit import es_cuit_valido, solo_digitos
from app.services.emisores import b64_a_bytes, registrar_emisor, vencimiento_certificado

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


DIAS_DE_AVISO_VENCIMIENTO = 30


@router.get("/diagnostico", response_model=DiagnosticoOut, dependencies=[Depends(_requiere_admin)])
def diagnostico(db: Session = Depends(get_db)) -> DiagnosticoOut:
    """Estado operativo del facturador, para monitoreo.

    Contesta las dos preguntas que hoy sólo se responden cuando algo ya falló:
    ¿algún certificado de ARCA está por vencer? ¿quedó alguna factura sin reconciliar?
    """
    ajustes = get_settings()
    hoy = date.today()
    a_reconciliar = dict(
        db.execute(
            select(Factura.emisor_id, func.count(Factura.id))
            .where(Factura.estado == "revisar")
            .group_by(Factura.emisor_id)
        ).all()
    )

    filas, advertencias = [], []
    for emisor in db.scalars(select(Emisor).order_by(Emisor.id)).all():
        vence = vencimiento_certificado(emisor) if emisor.arca_mode != "mock" else None
        dias = (vence - hoy).days if vence else None
        pendientes = a_reconciliar.get(emisor.id, 0)
        filas.append(
            DiagnosticoEmisor(
                cuit=emisor.cuit,
                razon_social=emisor.razon_social,
                arca_mode=emisor.arca_mode,
                activo=emisor.activo,
                tiene_certificado=emisor.tiene_certificado or emisor.por_defecto,
                tiene_token=bool(emisor.token_hash),
                certificado_vence=vence,
                dias_para_vencer=dias,
                certificado_vencido=bool(dias is not None and dias < 0),
                facturas_a_reconciliar=pendientes,
            )
        )
        if dias is not None and dias < 0:
            advertencias.append(f"El certificado de {emisor.cuit} venció el {vence}.")
        elif dias is not None and dias <= DIAS_DE_AVISO_VENCIMIENTO:
            advertencias.append(
                f"El certificado de {emisor.cuit} vence en {dias} días ({vence}): renovalo "
                "en ARCA antes de que corte la facturación."
            )
        if pendientes:
            advertencias.append(
                f"{emisor.cuit} tiene {pendientes} factura(s) esperando reconciliación "
                "(POST /api/facturas/reconciliar)."
            )

    return DiagnosticoOut(
        arca_mode=ajustes.arca_mode,
        docs_publicas=ajustes.facturador_docs,
        autenticacion_obligatoria=bool(ajustes.facturador_integracion_token.strip()),
        secreto_de_cifrado_configurado=ajustes.secreto_de_cifrado_configurado,
        emisores=filas,
        advertencias=advertencias,
    )
