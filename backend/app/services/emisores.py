"""Multiempresa: resolución del emisor por token, emisor por defecto y alta de emisores."""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuditoriaArca, Emisor, Factura, Lote, Transferencia
from app.services import cripto
from app.services.arca.wsaa import ErrorArca


def credenciales_pem(emisor: Emisor) -> tuple[str, str]:
    """Rutas a archivos con el cert y la clave del emisor.

    Emisores registrados: se descifran a archivos temporales. Emisor por defecto sin
    certificado propio: usa el del entorno (compatibilidad con el deploy de una empresa).
    """
    if not emisor.cert_cifrado or not emisor.key_cifrado:
        if emisor.por_defecto:
            s = get_settings()
            return s.cert_path_efectivo, s.key_path_efectivo
        raise ErrorArca(f"El emisor {emisor.cuit} no tiene certificado de ARCA cargado.")
    base = Path(tempfile.gettempdir()) / "arca_emisores"
    base.mkdir(parents=True, exist_ok=True)
    cert_p = base / f"emisor_{emisor.id}_cert.pem"
    key_p = base / f"emisor_{emisor.id}_key.key"
    cert_p.write_bytes(cripto.descifrar(emisor.cert_cifrado))
    key_p.write_bytes(cripto.descifrar(emisor.key_cifrado))
    import contextlib

    for ruta in (cert_p, key_p):
        with contextlib.suppress(OSError):
            ruta.chmod(0o600)
    return str(cert_p), str(key_p)




def emisor_por_defecto(db: Session) -> Emisor | None:
    """El emisor migrado desde las variables de entorno (compatibilidad de una sola empresa).

    Si hay ARCA_CUIT configurado y aún no existe, lo crea con las credenciales del entorno
    y adopta los datos previos (los que tienen emisor_id NULL)."""
    existente = db.scalar(select(Emisor).where(Emisor.por_defecto.is_(True)))
    if existente is not None:
        return existente
    s = get_settings()
    cuit = (s.arca_cuit or "").strip()
    if not cuit:
        return None
    emisor = Emisor(
        cuit=cuit,
        punto_venta=s.arca_punto_venta,
        tipo_comprobante=s.arca_tipo_comprobante,
        arca_mode=s.arca_mode,
        consultar_padron=s.arca_consultar_padron,
        por_defecto=True,
        activo=True,
    )
    # El emisor por defecto NO guarda el certificado: usa el del entorno directamente
    # (así el deploy actual no depende de configurar FACTURADOR_SECRET).
    db.add(emisor)
    db.flush()
    for modelo in (Lote, Transferencia, Factura, AuditoriaArca):
        db.execute(
            update(modelo).where(modelo.emisor_id.is_(None)).values(emisor_id=emisor.id)
        )
    db.commit()
    db.refresh(emisor)
    return emisor


def emisor_actual(
    authorization: str | None = Header(default=None),
    x_integracion_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Emisor:
    """Resuelve el emisor de la request: por token Bearer, o el emisor por defecto.

    El emisor por defecto (sin token propio) queda protegido por un secreto compartido:
    si se configuró FACTURADOR_INTEGRACION_TOKEN, el pedido debe traer el header
    X-Integracion-Token con ese valor. Si no se configuró, el comportamiento no cambia."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        emisor = db.scalar(
            select(Emisor).where(
                Emisor.token_hash == cripto.hash_token(token), Emisor.activo.is_(True)
            )
        )
        if emisor is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de emisor inválido.")
        return emisor
    # Sin token de emisor: se usa el emisor por defecto, pero protegido por el secreto
    # compartido (si está configurado) para que el endpoint no quede abierto.
    secreto = get_settings().facturador_integracion_token
    if secreto and (x_integracion_token or "") != secreto:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Falta o no coincide el token de integración (X-Integracion-Token).",
        )
    emisor = emisor_por_defecto(db)
    if emisor is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Falta autenticación: enviá el token del emisor (Authorization: Bearer ...).",
        )
    return emisor


def registrar_emisor(
    db: Session,
    *,
    cuit: str,
    cert_bytes: bytes | None,
    key_bytes: bytes | None,
    punto_venta: int,
    tipo_comprobante: int,
    arca_mode: str,
    razon_social: str | None = None,
    consultar_padron: bool = True,
) -> tuple[Emisor, str]:
    """Da de alta o actualiza un emisor. Devuelve el emisor y su token en texto plano (una vez)."""
    emisor = db.scalar(select(Emisor).where(Emisor.cuit == cuit))
    token = cripto.nuevo_token()
    if emisor is None:
        emisor = Emisor(cuit=cuit)
        db.add(emisor)
    emisor.razon_social = razon_social
    emisor.punto_venta = punto_venta
    emisor.tipo_comprobante = tipo_comprobante
    emisor.arca_mode = arca_mode
    emisor.consultar_padron = consultar_padron
    if cert_bytes and key_bytes:
        emisor.cert_cifrado = cripto.cifrar(cert_bytes)
        emisor.key_cifrado = cripto.cifrar(key_bytes)
    emisor.token_hash = cripto.hash_token(token)
    emisor.activo = True
    db.commit()
    db.refresh(emisor)
    from app.services.arca.factory import invalidar_emisor

    invalidar_emisor(emisor.id)
    return emisor, token


def b64_a_bytes(contenido_b64: str | None) -> bytes | None:
    if not contenido_b64 or not contenido_b64.strip():
        return None
    return base64.b64decode("".join(contenido_b64.split()))
