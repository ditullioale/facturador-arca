"""Autenticación contra el WSAA de ARCA (token y sign para los web services)."""

from __future__ import annotations

import base64
import contextlib
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import zeep
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509 import load_pem_x509_certificate

URLS_WSAA = {
    "homologacion": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl",
    "produccion": "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl",
}


class ErrorArca(RuntimeError):
    pass


@dataclass
class TicketAcceso:
    token: str
    sign: str
    expira: datetime

    @property
    def vigente(self) -> bool:
        return datetime.now(timezone.utc) < self.expira - timedelta(minutes=10)

    def a_dict(self) -> dict[str, str]:
        return {"token": self.token, "sign": self.sign, "expira": self.expira.isoformat()}

    @classmethod
    def desde_dict(cls, datos: dict[str, str]) -> TicketAcceso:
        return cls(
            token=datos["token"],
            sign=datos["sign"],
            expira=datetime.fromisoformat(datos["expira"]),
        )


def _tra(servicio: str) -> bytes:
    ahora = datetime.now(timezone.utc)
    unico = int(ahora.timestamp())
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<loginTicketRequest version=\"1.0\">"
        f"<header><uniqueId>{unico}</uniqueId>"
        f"<generationTime>{(ahora - timedelta(minutes=10)).isoformat()}</generationTime>"
        f"<expirationTime>{(ahora + timedelta(hours=12)).isoformat()}</expirationTime></header>"
        f"<service>{servicio}</service>"
        "</loginTicketRequest>"
    )
    return xml.encode("utf-8")


def _firmar_cms(tra: bytes, cert_path: str, key_path: str) -> str:
    for ruta in (cert_path, key_path):
        if not ruta or not Path(ruta).is_file():
            raise ErrorArca(
                f"No se encontró el archivo de credenciales de ARCA: {ruta or '(vacío)'}"
            )
    certificado = load_pem_x509_certificate(Path(cert_path).read_bytes())
    clave = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    cms = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra)
        .add_signer(certificado, clave, hashes.SHA256())
        # Binary: evita la canonicalización S/MIME (CRLF) sobre el TRA firmado.
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary])
    )
    return base64.b64encode(cms).decode("ascii")


class ClienteWsaa:
    """Obtiene y cachea el ticket de acceso por servicio."""

    def __init__(
        self, modo: str, cert_path: str, key_path: str, cache_dir: str | None = None
    ) -> None:
        if modo not in URLS_WSAA:
            raise ErrorArca(f"Modo de ARCA inválido para WSAA: {modo}")
        self._url = URLS_WSAA[modo]
        self._cert_path = cert_path
        self._key_path = key_path
        self._tickets: dict[str, TicketAcceso] = {}
        # Persistencia del TA entre reinicios: ARCA rechaza pedir un TA nuevo si ya
        # hay uno vigente para el mismo servicio ("el CEE ya posee un TA válido").
        base = cache_dir or str(Path(tempfile.gettempdir()) / "arca_ta")
        self._cache_dir = Path(base) / modo
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self._cache_dir = None  # type: ignore[assignment]

    def _ruta_ta(self, servicio: str) -> Path | None:
        return (self._cache_dir / f"ta_{servicio}.json") if self._cache_dir else None

    def _leer_ta_disco(self, servicio: str) -> TicketAcceso | None:
        ruta = self._ruta_ta(servicio)
        if not ruta or not ruta.is_file():
            return None
        try:
            return TicketAcceso.desde_dict(json.loads(ruta.read_text()))
        except (OSError, ValueError, KeyError):
            return None

    def _guardar_ta_disco(self, servicio: str, ticket: TicketAcceso) -> None:
        ruta = self._ruta_ta(servicio)
        if not ruta:
            return
        with contextlib.suppress(OSError):
            ruta.write_text(json.dumps(ticket.a_dict()))

    def ticket(self, servicio: str) -> TicketAcceso:
        cacheado = self._tickets.get(servicio) or self._leer_ta_disco(servicio)
        if cacheado and cacheado.vigente:
            self._tickets[servicio] = cacheado
            return cacheado
        cms = _firmar_cms(_tra(servicio), self._cert_path, self._key_path)
        try:
            respuesta = zeep.Client(self._url).service.loginCms(in0=cms)
        except Exception as exc:  # noqa: BLE001 - el WSAA devuelve fallas SOAP heterogéneas
            raise ErrorArca(f"Error autenticando en WSAA: {exc}") from exc
        raiz = ElementTree.fromstring(respuesta)
        token = raiz.findtext("./credentials/token")
        sign = raiz.findtext("./credentials/sign")
        expira = raiz.findtext("./header/expirationTime")
        if not token or not sign or not expira:
            raise ErrorArca("El WSAA no devolvió un ticket de acceso válido.")
        ticket = TicketAcceso(token=token, sign=sign, expira=datetime.fromisoformat(expira))
        self._tickets[servicio] = ticket
        self._guardar_ta_disco(servicio, ticket)
        return ticket
