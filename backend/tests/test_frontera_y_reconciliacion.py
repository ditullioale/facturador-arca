"""Blindaje de la frontera (quién puede emitir) y cierre del circuito (nada queda colgado).

Los tests de configuración fuerzan los ajustes con `monkeypatch` sobre el entorno y
limpian la cache de `get_settings`, porque el resto de la suite corre en modo mock y acá
hace falta mirar cómo se comporta el servicio operando contra ARCA de verdad.
"""

import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import app.services.facturacion as fact
from app.config import get_settings
from app.models import Emisor
from app.services import cripto
from app.services.emisores import vencimiento_certificado
from tests.factories import resumen_santander
from tests.test_idempotencia_auditoria import _FacturadorDesconocido, _FacturadorReconcilia


@pytest.fixture()
def ajustes_de(monkeypatch):
    """Devuelve una función para reconfigurar el servicio dentro de un test."""

    def configurar(**variables):
        for nombre, valor in variables.items():
            monkeypatch.setenv(nombre, valor)
        get_settings.cache_clear()
        return get_settings()

    yield configurar
    monkeypatch.undo()
    get_settings.cache_clear()


def _transferencia_con_cuit(client):
    datos = client.post(
        "/api/lotes", files={"archivo": ("s.xlsx", resumen_santander(), "application/x")}
    ).json()
    return next(t["id"] for t in datos["transferencias"] if t["cuit"])


# --- Frontera --------------------------------------------------------------------


def test_sin_token_de_integracion_contra_arca_real_no_se_atiende(client, ajustes_de):
    """El agujero que cierra esto: con FACTURADOR_INTEGRACION_TOKEN vacío, cualquiera
    que conociera la URL emitía con el emisor por defecto. En mock sigue abierto (es el
    modo de desarrollo); contra ARCA real, se rechaza."""
    ajustes_de(ARCA_MODE="produccion", FACTURADOR_INTEGRACION_TOKEN="")
    assert client.get("/api/facturas").status_code == 401


def test_con_token_de_integracion_se_atiende_solo_al_que_lo_trae(client, ajustes_de):
    ajustes_de(ARCA_MODE="produccion", FACTURADOR_INTEGRACION_TOKEN="secreto-compartido")
    assert client.get("/api/facturas").status_code == 401
    assert client.get("/api/facturas", headers={"X-Integracion-Token": "otro"}).status_code == 401
    ok = client.get("/api/facturas", headers={"X-Integracion-Token": "secreto-compartido"})
    assert ok.status_code == 200


def test_en_mock_no_se_exige_token(client):
    """Desarrollo y demo siguen funcionando sin configurar nada."""
    assert client.get("/api/facturas").status_code == 200


def test_arranque_falla_si_falta_el_secreto_de_cifrado(ajustes_de):
    ajustes = ajustes_de(
        ARCA_MODE="produccion", FACTURADOR_SECRET="", FACTURADOR_INTEGRACION_TOKEN="x"
    )
    assert any("FACTURADOR_SECRET" in p for p in ajustes.errores_de_configuracion())


def test_arranque_falla_si_cors_es_abierto(ajustes_de):
    ajustes = ajustes_de(
        ARCA_MODE="produccion",
        FACTURADOR_SECRET="s",
        FACTURADOR_INTEGRACION_TOKEN="x",
        CORS_ORIGINS="*",
    )
    assert any("CORS_ORIGINS" in p for p in ajustes.errores_de_configuracion())


def test_en_mock_no_se_exige_configuracion(ajustes_de):
    ajustes = ajustes_de(ARCA_MODE="mock", FACTURADOR_SECRET="", FACTURADOR_INTEGRACION_TOKEN="")
    assert ajustes.errores_de_configuracion() == []


def test_no_se_cifra_un_certificado_real_con_la_clave_de_desarrollo(ajustes_de):
    ajustes_de(ARCA_MODE="produccion", FACTURADOR_SECRET="")
    with pytest.raises(cripto.SecretoNoConfigurado):
        cripto.cifrar(b"certificado")


def test_las_docs_no_estan_publicadas(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_cabeceras_de_seguridad_y_correlacion(client):
    respuesta = client.get("/api/health", headers={"X-Request-Id": "abc123"})
    assert respuesta.headers["X-Request-Id"] == "abc123"
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/health").headers["X-Request-Id"]


def test_el_resumen_gigante_se_rechaza_sin_leerlo_entero(client, ajustes_de):
    ajustes_de(FACTURADOR_MAX_UPLOAD_MB="1")
    grande = b"0" * (1024 * 1024 + 10)
    respuesta = client.post("/api/lotes", files={"archivo": ("s.csv", grande, "text/csv")})
    assert respuesta.status_code == 413


# --- Circuito --------------------------------------------------------------------


def test_reconciliar_resuelve_las_facturas_colgadas_por_timeout(client, monkeypatch):
    """Una factura en "revisar" puede estar autorizada en ARCA y no registrada acá.
    Hasta ahora esperaba a que alguien reintentara esa transferencia a mano."""
    tid = _transferencia_con_cuit(client)
    monkeypatch.setattr(fact, "get_facturador_para", lambda emisor: _FacturadorDesconocido())
    assert client.post(f"/api/transferencias/{tid}/facturar").json()["estado"] == "revisar"

    monkeypatch.setattr(fact, "get_facturador_para", lambda emisor: _FacturadorReconcilia())
    resueltas = client.post("/api/facturas/reconciliar").json()
    assert [f["estado"] for f in resueltas] == ["emitida"]
    assert resueltas[0]["cae"] == "CAE-RECONCILIADO"
    # La transferencia acompaña el estado: no queda "pendiente" con su factura emitida.
    transferencia = next(
        t for t in client.get("/api/transferencias").json() if t["id"] == tid
    )
    assert transferencia["estado"] == "facturada"


def test_reconciliar_sin_pendientes_no_hace_nada(client):
    assert client.post("/api/facturas/reconciliar").json() == []


def _certificado_que_vence(dias: int) -> bytes:
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "emisor de prueba")])
    ahora = datetime.datetime.now(datetime.timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - datetime.timedelta(days=1))
        .not_valid_after(ahora + datetime.timedelta(days=dias))
        .sign(clave, hashes.SHA256())
    )
    pem_cert = certificado.public_bytes(serialization.Encoding.PEM)
    pem_key = clave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_cert, pem_key


def test_el_vencimiento_del_certificado_se_puede_leer():
    """Los certificados de ARCA duran un año y al vencer cortan la facturación de golpe."""
    pem_cert, pem_key = _certificado_que_vence(40)
    emisor = Emisor(
        id=99,
        cuit="20111111112",
        cert_cifrado=cripto.cifrar(pem_cert),
        key_cifrado=cripto.cifrar(pem_key),
    )
    vence = vencimiento_certificado(emisor)
    assert vence == (datetime.date.today() + datetime.timedelta(days=40))


def test_el_diagnostico_avisa_del_certificado_por_vencer(client, db_session):
    pem_cert, pem_key = _certificado_que_vence(10)
    db_session.add(
        Emisor(
            cuit="27123456780",
            arca_mode="homologacion",
            cert_cifrado=cripto.cifrar(pem_cert),
            key_cifrado=cripto.cifrar(pem_key),
            token_hash=cripto.hash_token("token-de-prueba"),
        )
    )
    db_session.commit()

    datos = client.get(
        "/api/emisores/diagnostico", headers={"X-Admin-Token": "admin-test"}
    ).json()
    fila = next(e for e in datos["emisores"] if e["cuit"] == "27123456780")
    assert fila["dias_para_vencer"] == 10
    assert fila["certificado_vencido"] is False
    assert any("vence en 10 días" in a for a in datos["advertencias"])


def test_el_diagnostico_pide_token_de_admin(client):
    assert client.get("/api/emisores/diagnostico").status_code == 401
