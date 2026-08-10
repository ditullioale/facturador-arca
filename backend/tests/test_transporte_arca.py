"""El transporte de ARCA tiene que tolerar el Diffie-Hellman de 1024 bits que usan
los servidores de producción, que OpenSSL 3 rechaza por defecto."""

import os

import pytest
import requests

from app.services.arca.transporte import sesion_arca, transporte_arca

URL_PRODUCCION_WSFE = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"


def test_transporte_usa_una_sesion_propia():
    transporte = transporte_arca()
    assert transporte.session is not None
    assert transporte.session.get_adapter("https://servicios1.afip.gov.ar") is not (
        requests.Session().get_adapter("https://servicios1.afip.gov.ar")
    )


def test_la_sesion_verifica_el_certificado_del_servidor():
    """Bajar el nivel de seguridad es sólo para el grupo DH: la verificación sigue."""
    assert sesion_arca().verify is True


@pytest.mark.skipif(
    os.environ.get("ARCA_TEST_RED") != "1",
    reason="requiere salida a internet hacia ARCA (ARCA_TEST_RED=1)",
)
def test_handshake_con_produccion_no_falla_por_dh_key_too_small():
    respuesta = sesion_arca().get(URL_PRODUCCION_WSFE, timeout=30)
    assert respuesta.status_code == 200
    assert b"FECAESolicitar" in respuesta.content
