"""Tests de armado del payload WSFE y del cacheo del Ticket de Acceso (WSAA)."""

from datetime import date, datetime, timedelta, timezone

from app.services.arca.wsaa import ClienteWsaa, TicketAcceso
from app.services.arca.wsfe import SolicitudFactura, construir_detalle


def test_cbtefch_usa_fecha_de_emision_no_la_del_servicio():
    """CbteFch debe ser HOY (emisión); el período del servicio va aparte."""
    solicitud = SolicitudFactura(
        cuit_receptor="27123456780",
        importe=100000,
        fecha=date(2026, 5, 1),  # transferencia vieja
        punto_venta=1,
        tipo_comprobante=11,
    )
    detalle = construir_detalle(solicitud, proximo=5, hoy=date(2026, 7, 31))
    assert detalle["CbteFch"] == "20260731"  # emisión (hoy)
    assert detalle["FchServDesde"] == "20260501"  # período del servicio
    assert detalle["FchServHasta"] == "20260501"
    assert detalle["FchVtoPago"] == "20260731"
    assert detalle["CbteDesde"] == 5
    assert detalle["Concepto"] == 2  # servicios


def test_factura_c_no_discrimina_iva():
    solicitud = SolicitudFactura("27123456780", 100000, date(2026, 7, 1), 1, 11)
    detalle = construir_detalle(solicitud, 1, date(2026, 7, 31))
    assert "Iva" not in detalle
    assert detalle["ImpIVA"] == 0


def test_factura_b_incluye_alicuota_iva():
    solicitud = SolicitudFactura("27123456780", 100000, date(2026, 7, 1), 1, 6)
    detalle = construir_detalle(solicitud, 1, date(2026, 7, 31))
    assert "Iva" in detalle


def test_ticket_acceso_se_persiste_y_reutiliza(tmp_path):
    """Un TA vigente guardado en disco se reutiliza tras 'reiniciar' (nueva instancia)."""
    expira = datetime.now(timezone.utc) + timedelta(hours=11)
    ticket = TicketAcceso(token="TOK", sign="SIGN", expira=expira)

    c1 = ClienteWsaa("homologacion", "", "", cache_dir=str(tmp_path))
    c1._guardar_ta_disco("wsfe", ticket)

    # Nueva instancia (simula reinicio del proceso): lee el TA del disco.
    c2 = ClienteWsaa("homologacion", "", "", cache_dir=str(tmp_path))
    leido = c2._leer_ta_disco("wsfe")
    assert leido is not None
    assert leido.token == "TOK"
    assert leido.vigente is True


def test_ticket_vencido_no_se_considera_vigente():
    vencido = TicketAcceso(
        token="T", sign="S", expira=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    assert vencido.vigente is False


def test_materializar_pem_desde_base64(tmp_path, monkeypatch):
    """El certificado/clave en base64 se escribe a un archivo y se devuelve su ruta."""
    import base64

    from app.config import _materializar_pem

    contenido = b"-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n"
    b64 = base64.b64encode(contenido).decode()
    ruta = _materializar_pem(b64, "", "arca_cert_test.pem")
    assert ruta.endswith("arca_cert_test.pem")
    with open(ruta, "rb") as f:
        assert f.read() == contenido


def test_materializar_pem_sin_b64_devuelve_ruta_archivo():
    from app.config import _materializar_pem

    assert _materializar_pem("", "/ruta/cert.crt", "arca_cert.pem") == "/ruta/cert.crt"
