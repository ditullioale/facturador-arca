"""Emisión de comprobantes electrónicos en ARCA (WSFEv1).

Nota: WSFEv1 no transporta el detalle/concepto de la prestación (la factura electrónica
autoriza importes, no renglones). El texto "HONORARIOS PROFESIONALES" se persiste en la
factura y se usa en la representación impresa del comprobante.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

import zeep

from app.services.arca.wsaa import ClienteWsaa, ErrorArca

URLS_WSFE = {
    "homologacion": "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL",
    "produccion": "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL",
}
SERVICIO = "wsfe"

# Concepto WSFEv1: 1 productos, 2 servicios, 3 productos y servicios.
CONCEPTO_SERVICIOS = 2
# Documento del receptor: 80 CUIT, 99 consumidor final.
DOC_TIPO_CUIT = 80
# Tipos de comprobante sin discriminación de IVA (monotributo / sujeto exento).
TIPOS_SIN_IVA = {11, 12, 13, 15}
# 5 = "sin gravado" para comprobantes que no discriminan IVA.
IVA_NO_GRAVADO = 3


@dataclass
class SolicitudFactura:
    cuit_receptor: str
    importe: Decimal
    fecha: date
    punto_venta: int
    tipo_comprobante: int


@dataclass
class ResultadoEmision:
    numero: int
    cae: str
    cae_vencimiento: date
    observaciones: list[str]


class Facturador(Protocol):
    def emitir(self, solicitud: SolicitudFactura) -> ResultadoEmision: ...


class FacturadorMock:
    """Emisor simulado: numera y devuelve un CAE ficticio, sin tocar ARCA."""

    def __init__(self) -> None:
        self._contador = itertools.count(1)

    def emitir(self, solicitud: SolicitudFactura) -> ResultadoEmision:
        numero = next(self._contador)
        return ResultadoEmision(
            numero=numero,
            cae=f"7{solicitud.fecha.strftime('%y%m%d')}{numero:07d}",
            cae_vencimiento=solicitud.fecha + timedelta(days=10),
            observaciones=["Comprobante simulado (ARCA_MODE=mock): no tiene validez fiscal."],
        )


class FacturadorArca:
    def __init__(self, modo: str, cuit_emisor: str, wsaa: ClienteWsaa) -> None:
        if modo not in URLS_WSFE:
            raise ErrorArca(f"Modo de ARCA inválido para WSFE: {modo}")
        self._cliente = zeep.Client(URLS_WSFE[modo])
        self._cuit_emisor = int(cuit_emisor)
        self._wsaa = wsaa

    def _auth(self) -> dict[str, object]:
        ticket = self._wsaa.ticket(SERVICIO)
        return {"Token": ticket.token, "Sign": ticket.sign, "Cuit": self._cuit_emisor}

    def ultimo_autorizado(self, punto_venta: int, tipo_comprobante: int) -> int:
        respuesta = self._cliente.service.FECompUltimoAutorizado(
            Auth=self._auth(), PtoVta=punto_venta, CbteTipo=tipo_comprobante
        )
        _verificar_errores(respuesta)
        return int(respuesta.CbteNro)

    def emitir(self, solicitud: SolicitudFactura) -> ResultadoEmision:
        proximo = self.ultimo_autorizado(solicitud.punto_venta, solicitud.tipo_comprobante) + 1
        fecha = solicitud.fecha.strftime("%Y%m%d")
        importe = float(solicitud.importe)
        detalle: dict[str, object] = {
            "Concepto": CONCEPTO_SERVICIOS,
            "DocTipo": DOC_TIPO_CUIT,
            "DocNro": int(solicitud.cuit_receptor),
            "CbteDesde": proximo,
            "CbteHasta": proximo,
            "CbteFch": fecha,
            "ImpTotal": importe,
            "ImpTotConc": 0,
            "ImpNeto": importe,
            "ImpOpEx": 0,
            "ImpIVA": 0,
            "ImpTrib": 0,
            "FchServDesde": fecha,
            "FchServHasta": fecha,
            "FchVtoPago": fecha,
            "MonId": "PES",
            "MonCotiz": 1,
        }
        if solicitud.tipo_comprobante not in TIPOS_SIN_IVA:
            detalle["ImpNeto"] = importe
            detalle["Iva"] = {
                "AlicIva": [{"Id": IVA_NO_GRAVADO, "BaseImp": importe, "Importe": 0}]
            }

        respuesta = self._cliente.service.FECAESolicitar(
            Auth=self._auth(),
            FeCAEReq={
                "FeCabReq": {
                    "CantReg": 1,
                    "PtoVta": solicitud.punto_venta,
                    "CbteTipo": solicitud.tipo_comprobante,
                },
                "FeDetReq": {"FECAEDetRequest": [detalle]},
            },
        )
        _verificar_errores(respuesta)
        det = respuesta.FeDetResp.FECAEDetResponse[0]
        vto = str(det.CAEFchVto)
        if det.Resultado != "A" or not det.CAE:
            raise ErrorArca(f"ARCA rechazó el comprobante: {_observaciones(det) or det.Resultado}")
        return ResultadoEmision(
            numero=int(det.CbteDesde),
            cae=str(det.CAE),
            cae_vencimiento=date(int(vto[0:4]), int(vto[4:6]), int(vto[6:8])),
            observaciones=_observaciones(det),
        )


def _observaciones(det: object) -> list[str]:
    obs = getattr(det, "Observaciones", None)
    if obs is None:
        return []
    return [f"{o.Code}: {o.Msg}" for o in obs.Obs]


def _verificar_errores(respuesta: object) -> None:
    errores = getattr(respuesta, "Errors", None)
    if errores is not None:
        detalle = "; ".join(f"{e.Code}: {e.Msg}" for e in errores.Err)
        raise ErrorArca(f"ARCA devolvió errores: {detalle}")
