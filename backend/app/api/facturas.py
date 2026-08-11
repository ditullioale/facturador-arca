from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditoriaArca, Emisor, Factura
from app.schemas import AuditoriaOut, ConfigOut, DatosPadronOut, FacturaOut
from app.services.arca.wsaa import ErrorArca
from app.services.cuit import es_cuit_valido, solo_digitos
from app.services.emisores import emisor_actual
from app.services.facturacion import consultar_padron, reconciliar_pendientes
from app.services.representacion import generar_pdf

router = APIRouter(prefix="/api", tags=["facturas"])


@router.get("/facturas", response_model=list[FacturaOut])
def listar_facturas(
    estado: str | None = None,
    limit: int = 50,
    offset: int = 0,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> list[FacturaOut]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    consulta = select(Factura).where(Factura.emisor_id == emisor.id).order_by(Factura.id.desc())
    if estado:
        consulta = consulta.where(Factura.estado == estado)
    consulta = consulta.limit(limit).offset(offset)
    return [FacturaOut.model_validate(f) for f in db.scalars(consulta).all()]


@router.post("/facturas/reconciliar", response_model=list[FacturaOut])
def reconciliar(
    limite: int = 50,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> list[FacturaOut]:
    """Retoma las facturas que quedaron en "revisar" por un timeout de ARCA.

    Sin esto, un timeout deja el comprobante posiblemente autorizado en ARCA y no
    registrado acá, esperando que alguien se acuerde de reintentar. Se consulta con
    FECompConsultar antes de reemitir, así que no puede duplicar. Pensado para un cron.
    """
    return [
        FacturaOut.model_validate(f)
        for f in reconciliar_pendientes(db, emisor, limite=max(1, min(limite, 200)))
    ]


@router.get("/auditoria", response_model=list[AuditoriaOut])
def listar_auditoria(
    limit: int = 50,
    offset: int = 0,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> list[AuditoriaOut]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    consulta = (
        select(AuditoriaArca)
        .where(AuditoriaArca.emisor_id == emisor.id)
        .order_by(AuditoriaArca.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [AuditoriaOut.model_validate(a) for a in db.scalars(consulta).all()]


@router.get("/facturas/{factura_id}/pdf")
def factura_pdf(
    factura_id: int,
    emisor: Emisor = Depends(emisor_actual),
    db: Session = Depends(get_db),
) -> Response:
    factura = db.get(Factura, factura_id)
    if factura is None or factura.emisor_id != emisor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    if factura.estado != "emitida":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La factura no está emitida (sin CAE): no se puede generar la representación impresa.",
        )
    pdf = generar_pdf(factura)
    numero = f"{factura.punto_venta:04d}-{(factura.numero or 0):08d}"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="factura-{numero}.pdf"'},
    )


@router.get("/padron/{cuit}", response_model=DatosPadronOut)
def consultar(
    cuit: str, emisor: Emisor = Depends(emisor_actual)
) -> DatosPadronOut:
    digitos = solo_digitos(cuit)
    if not es_cuit_valido(digitos):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CUIT inválido")
    try:
        datos, autocompletado = consultar_padron(digitos, emisor)
    except ErrorArca as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return DatosPadronOut(
        cuit=datos.cuit,
        razon_social=datos.razon_social,
        domicilio=datos.domicilio,
        domicilio_autocompletado=autocompletado,
    )


@router.get("/config", response_model=ConfigOut)
def configuracion(
    emisor: Emisor = Depends(emisor_actual),
) -> ConfigOut:
    s = get_settings()
    return ConfigOut(
        arca_mode=emisor.arca_mode,
        arca_cuit=emisor.cuit,
        punto_venta=emisor.punto_venta,
        tipo_comprobante=emisor.tipo_comprobante,
        concepto_descripcion=s.arca_concepto_descripcion,
        importe_minimo=s.arca_importe_minimo,
        domicilio_default=s.domicilio_default,
    )
