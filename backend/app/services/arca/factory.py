"""Clientes de ARCA por emisor (multiempresa): cada uno firma con su certificado."""
from app.config import get_settings
from app.services.arca.padron import Padron, PadronArca, PadronMock
from app.services.arca.wsaa import ClienteWsaa
from app.services.arca.wsfe import Facturador, FacturadorArca, FacturadorMock

_facturadores: dict[tuple, Facturador] = {}
_padrones: dict[tuple, Padron] = {}


def _wsaa_para(emisor) -> ClienteWsaa:
    from app.services.emisores import credenciales_pem

    cert, key = credenciales_pem(emisor)
    return ClienteWsaa(emisor.arca_mode, cert, key, get_settings().arca_ta_dir or None)


def get_facturador_para(emisor) -> Facturador:
    clave = (emisor.id, emisor.arca_mode)
    if emisor.arca_mode == "mock":
        return _facturadores.setdefault(clave, FacturadorMock())
    if clave not in _facturadores:
        _facturadores[clave] = FacturadorArca(emisor.arca_mode, emisor.cuit, _wsaa_para(emisor))
    return _facturadores[clave]


def get_padron_para(emisor) -> Padron:
    clave = (emisor.id, emisor.arca_mode)
    if emisor.arca_mode == "mock":
        return _padrones.setdefault(clave, PadronMock())
    if clave not in _padrones:
        _padrones[clave] = PadronArca(emisor.arca_mode, emisor.cuit, _wsaa_para(emisor))
    return _padrones[clave]


def invalidar_emisor(emisor_id: int) -> None:
    for cache in (_facturadores, _padrones):
        for clave in [k for k in cache if k[0] == emisor_id]:
            cache.pop(clave, None)
