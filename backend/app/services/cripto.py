"""Cifrado de credenciales de ARCA por emisor (multiempresa) y utilidades de token."""
from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet

from app.config import get_settings


def _fernet() -> Fernet:
    secret = get_settings().facturador_secret or "facturador-dev-secret-cambiar-en-produccion"
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
