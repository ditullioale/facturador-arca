"""Cifrado de credenciales de ARCA por emisor (multiempresa) y utilidades de token."""
from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet

from app.config import get_settings

SECRETO_DE_DESARROLLO = "facturador-dev-secret-cambiar-en-produccion"


class SecretoNoConfigurado(RuntimeError):
    """Falta FACTURADOR_SECRET operando contra ARCA real."""


def _fernet() -> Fernet:
    ajustes = get_settings()
    secret = ajustes.facturador_secret.strip()
    if not secret:
        # El fallback existe para desarrollo, pero está en el código fuente: cifrar con
        # él un certificado de ARCA real equivale a guardarlo en claro.
        if ajustes.modo_real:
            raise SecretoNoConfigurado(
                "Falta FACTURADOR_SECRET: no se puede guardar ni leer un certificado de "
                "ARCA cifrado con la clave de desarrollo."
            )
        secret = SECRETO_DE_DESARROLLO
    clave = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(clave)


def cifrar(datos: bytes) -> str:
    return _fernet().encrypt(datos).decode("ascii")


def descifrar(texto: str) -> bytes:
    return _fernet().decrypt(texto.encode("ascii"))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def nuevo_token() -> str:
    return secrets.token_urlsafe(32)
