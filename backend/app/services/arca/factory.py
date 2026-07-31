from functools import lru_cache

from app.config import get_settings
from app.services.arca.padron import Padron, PadronArca, PadronMock
from app.services.arca.wsaa import ClienteWsaa, ErrorArca
from app.services.arca.wsfe import Facturador, FacturadorArca, FacturadorMock


@lru_cache
def _wsaa() -> ClienteWsaa:
    s = get_settings()
    return ClienteWsaa(s.arca_mode, s.arca_cert_path, s.arca_key_path, s.arca_ta_dir or None)


@lru_cache
def get_padron() -> Padron:
    s = get_settings()
    if s.arca_mode == "mock":
        return PadronMock()
    return PadronArca(s.arca_mode, _cuit_emisor(), _wsaa())


@lru_cache
def get_facturador() -> Facturador:
    s = get_settings()
    if s.arca_mode == "mock":
        return FacturadorMock()
    return FacturadorArca(s.arca_mode, _cuit_emisor(), _wsaa())


def _cuit_emisor() -> str:
    cuit = get_settings().arca_cuit
    if not cuit:
        raise ErrorArca("Falta configurar ARCA_CUIT (CUIT del emisor).")
    return cuit
