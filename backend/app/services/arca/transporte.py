"""Transporte HTTP para los servicios SOAP de ARCA.

Los servidores de producción de ARCA (`servicios1.afip.gov.ar`, `aws.afip.gov.ar`)
negocian Diffie-Hellman con una clave de 1024 bits. OpenSSL 3 exige 2048 como mínimo
en su nivel de seguridad por defecto, así que el handshake falla antes de empezar con
`[SSL: DH_KEY_TOO_SMALL] dh key too small`. Homologación no lo sufre porque usa otro
servidor.

Se baja el nivel de seguridad a 1 sólo en la sesión que habla con ARCA; el resto de la
aplicación mantiene el default. La verificación del certificado del servidor sigue
activa: lo único que se acepta es un grupo DH más corto.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from zeep.transports import Transport

TIMEOUT = 15
_CIFRADOS = "DEFAULT@SECLEVEL=1"


class _AdaptadorDhCorto(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        contexto = create_urllib3_context()
        contexto.set_ciphers(_CIFRADOS)
        kwargs["ssl_context"] = contexto
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        contexto = create_urllib3_context()
        contexto.set_ciphers(_CIFRADOS)
        kwargs["ssl_context"] = contexto
        return super().proxy_manager_for(*args, **kwargs)


def sesion_arca() -> requests.Session:
    sesion = requests.Session()
    sesion.mount("https://", _AdaptadorDhCorto())
    return sesion


def transporte_arca() -> Transport:
    return Transport(session=sesion_arca(), timeout=TIMEOUT, operation_timeout=TIMEOUT)
