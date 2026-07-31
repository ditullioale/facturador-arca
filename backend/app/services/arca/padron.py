"""Consulta al padrón de ARCA (constancia de inscripción, servicio A13)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import zeep
from zeep.transports import Transport

from app.services.arca.wsaa import ClienteWsaa, ErrorArca

URLS_PADRON = {
    "homologacion": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA13?WSDL",
    "produccion": "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA13?WSDL",
}
SERVICIO = "ws_sr_constancia_inscripcion"


@dataclass
class DatosPadron:
    cuit: str
    razon_social: str | None
    domicilio: str | None


class Padron(Protocol):
    def consultar(self, cuit: str) -> DatosPadron: ...


class PadronMock:
    """Padrón simulado para desarrollo sin certificados."""

    def consultar(self, cuit: str) -> DatosPadron:
        return DatosPadron(cuit=cuit, razon_social=f"CONTRIBUYENTE {cuit}", domicilio=None)


class PadronArca:
    def __init__(self, modo: str, cuit_representada: str, wsaa: ClienteWsaa) -> None:
        if modo not in URLS_PADRON:
            raise ErrorArca(f"Modo de ARCA inválido para padrón: {modo}")
        self._url = URLS_PADRON[modo]
        self._cuit_representada = cuit_representada
        self._wsaa = wsaa

    def consultar(self, cuit: str) -> DatosPadron:
        ticket = self._wsaa.ticket(SERVICIO)
        try:
            persona = zeep.Client(
                self._url, transport=Transport(timeout=15, operation_timeout=15)
            ).service.getPersona(
                token=ticket.token,
                sign=ticket.sign,
                cuitRepresentada=int(self._cuit_representada),
                idPersona=int(cuit),
            )
        except Exception as exc:  # noqa: BLE001 - fallas SOAP heterogéneas
            raise ErrorArca(f"Error consultando el padrón de ARCA para {cuit}: {exc}") from exc
        return _mapear_persona(cuit, persona)


def _mapear_persona(cuit: str, persona: object) -> DatosPadron:
    datos = getattr(persona, "datosGenerales", None)
    if datos is None:
        return DatosPadron(cuit=cuit, razon_social=None, domicilio=None)
    razon_social = getattr(datos, "razonSocial", None) or " ".join(
        parte
        for parte in (getattr(datos, "apellido", None), getattr(datos, "nombre", None))
        if parte
    )
    return DatosPadron(
        cuit=cuit,
        razon_social=razon_social or None,
        domicilio=_domicilio(datos),
    )


def _domicilio(datos: object) -> str | None:
    domicilios = getattr(datos, "domicilioFiscal", None)
    if domicilios is None:
        return None
    partes = [
        getattr(domicilios, campo, None)
        for campo in ("direccion", "localidad", "descripcionProvincia")
    ]
    texto = ", ".join(str(p).strip() for p in partes if p and str(p).strip())
    return texto or None
