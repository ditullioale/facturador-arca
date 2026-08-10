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
from zeep.transports import Transport

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
    # Condición frente al IVA del receptor (RG 5616). 5 = Consumidor Final.
    condicion_iva_receptor: int = 5


@dataclass
class ResultadoEmision:
    numero: int
    cae: str
    cae_vencimiento: date
    observaciones: list[str]


class ResultadoDesconocido(Exception):
    """El envío a ARCA no obtuvo respuesta (timeout/red): el comprobante PUEDE haberse
    autorizado. Guarda el número intentado para reconciliar con FECompConsultar antes de
    reintentar y no duplicar."""

    def __init__(self, numero: int) -> None:
        super().__init__(f"Resultado desconocido para el comprobante {numero}")
        self.numero = numero


class Facturador(Protocol):
    def emitir(self, solicitud: SolicitudFactura) -> ResultadoEmision: ...

    def consultar(
        self, punto_venta: int, tipo_comprobante: int, numero: int
    ) -> ResultadoEmision | None: ...


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

    def consultar(
        self, punto_venta: int, tipo_comprobante: int, numero: int
    ) -> ResultadoEmision | None:
        return None


def construir_detalle(
    solicitud: SolicitudFactura, proximo: int, hoy: date
) -> dict[str, object]:
    """Arma el detalle FECAEDetRequest de WSFEv1.

    Importante: ``CbteFch`` (fecha del comprobante) es la fecha de EMISIÓN (hoy), no la
    del servicio: WSFEv1 exige que la fecha del comprobante esté dentro del rango
    permitido (± unos pocos días respecto de la autorización) y rechaza fechas viejas
    (error 10016). El período del servicio prestado va en ``FchServDesde`` /
    ``FchServHasta`` (la fecha de la transferencia o liquidación), y ``FchVtoPago`` se
    fija en la fecha de emisión.
    """
    emision = hoy.strftime("%Y%m%d")
    servicio = solicitud.fecha.strftime("%Y%m%d")
    importe = float(solicitud.importe)
    detalle: dict[str, object] = {
        "Concepto": CONCEPTO_SERVICIOS,
        "DocTipo": DOC_TIPO_CUIT,
        "DocNro": int(solicitud.cuit_receptor),
        "CondicionIVAReceptorId": int(solicitud.condicion_iva_receptor),
        "CbteDesde": proximo,
        "CbteHasta": proximo,
        "CbteFch": emision,
        "ImpTotal": importe,
        "ImpTotConc": 0,
        "ImpNeto": importe,
        "ImpOpEx": 0,
        "ImpIVA": 0,
        "ImpTrib": 0,
        "FchServDesde": servicio,
        "FchServHasta": servicio,
        "FchVtoPago": emision,
        "MonId": "PES",
        "MonCotiz": 1,
    }
    if solicitud.tipo_comprobante not in TIPOS_SIN_IVA:
        detalle["ImpNeto"] = importe
        detalle["Iva"] = {"AlicIva": [{"Id": IVA_NO_GRAVADO, "BaseImp": importe, "Importe": 0}]}
    return detalle


class FacturadorArca:
    def __init__(self, modo: str, cuit_emisor: str, wsaa: ClienteWsaa) -> None:
        if modo not in URLS_WSFE:
            raise ErrorArca(f"Modo de ARCA inválido para WSFE: {modo}")
        try:
            self._cliente = zeep.Client(
                URLS_WSFE[modo], transport=Transport(timeout=15, operation_timeout=15)
            )
        except Exception as exc:  # noqa: BLE001 - no se pudo bajar el WSDL / conectar
            raise ErrorArca(
                f"No se pudo conectar al servicio de facturación de ARCA ({modo}): {exc}"
            ) from exc
        self._cuit_emisor = int(cuit_emisor)
        self._wsaa = wsaa

    def _auth(self) -> dict[str, object]:
        ticket = self._wsaa.ticket(SERVICIO)
        return {"Token": ticket.token, "Sign": ticket.sign, "Cuit": self._cuit_emisor}

    def ultimo_autorizado(self, punto_venta: int, tipo_comprobante: int) -> int:
        try:
            respuesta = self._cliente.service.FECompUltimoAutorizado(
                Auth=self._auth(), PtoVta=punto_venta, CbteTipo=tipo_comprobante
            )
        except ErrorArca:
            raise  # WSAA u otro error ya tipado
        except Exception as exc:  # noqa: BLE001 - falla SOAP/red al consultar el último número
            raise ErrorArca(
                "No se pudo consultar el último comprobante autorizado en ARCA "
                f"(revisá que el punto de venta {punto_venta} sea de tipo Web Services y esté "
                f"autorizado para el web service de facturación): {exc}"
            ) from exc
        _verificar_errores(respuesta)
        numero = getattr(respuesta, "CbteNro", None)
        if numero is None:
            raise ErrorArca(
                "ARCA no devolvió el último número autorizado. Suele ser el punto de venta: "
                "verificá que exista como 'Factura Electrónica - Web Services' y esté habilitado."
            )
        return int(numero)

    def emitir(self, solicitud: SolicitudFactura) -> ResultadoEmision:
        proximo = self.ultimo_autorizado(solicitud.punto_venta, solicitud.tipo_comprobante) + 1
        detalle = construir_detalle(solicitud, proximo, date.today())
        # Se resuelve la autenticación ANTES del envío: si falla el WSAA no se envió nada
        # a ARCA (reintento seguro). Lo que puede quedar en resultado desconocido es solo
        # el FECAESolicitar.
        auth = self._auth()
        req = {
            "FeCabReq": {
                "CantReg": 1,
                "PtoVta": solicitud.punto_venta,
                "CbteTipo": solicitud.tipo_comprobante,
            },
            "FeDetReq": {"FECAEDetRequest": [detalle]},
        }
        try:
            respuesta = self._cliente.service.FECAESolicitar(Auth=auth, FeCAEReq=req)
        except Exception as exc:  # noqa: BLE001 - timeout/red: resultado DESCONOCIDO
            raise ResultadoDesconocido(proximo) from exc
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

    def consultar(
        self, punto_venta: int, tipo_comprobante: int, numero: int
    ) -> ResultadoEmision | None:
        """Consulta un comprobante en ARCA (FECompConsultar). Devuelve el CAE si existe,
        o None si no fue emitido. Se usa para reconciliar tras un resultado desconocido."""
        try:
            respuesta = self._cliente.service.FECompConsultar(
                Auth=self._auth(),
                FeCompConsReq={
                    "CbteTipo": tipo_comprobante,
                    "CbteNro": numero,
                    "PtoVta": punto_venta,
                },
            )
        except Exception as exc:  # noqa: BLE001 - fallas SOAP heterogéneas
            raise ErrorArca(f"Error consultando comprobante en ARCA: {exc}") from exc
        if getattr(respuesta, "Errors", None) is not None:
            return None  # no existe (típicamente error 602)
        r = getattr(respuesta, "ResultGet", None)
        cae = getattr(r, "CodAutorizacion", None) if r is not None else None
        if not cae:
            return None
        vto = str(getattr(r, "FchVto", "") or "")
        try:
            vencimiento = date(int(vto[0:4]), int(vto[4:6]), int(vto[6:8]))
        except (ValueError, IndexError):
            vencimiento = date.today()
        return ResultadoEmision(
            numero=int(getattr(r, "CbteDesde", numero)),
            cae=str(cae),
            cae_vencimiento=vencimiento,
            observaciones=[],
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
