"""Tests de la regla de umbral, la representación en PDF y la integración con el gestor."""

from tests.factories import resumen_santander


def _subir(client, contenido: bytes, nombre: str):
    return client.post(
        "/api/lotes",
        files={"archivo": (nombre, contenido, "application/vnd.ms-excel")},
    )


def _transferencia_bajo_minimo(client):
    """La fila 'SIN DATOS' del resumen Santander es de $45.000 (bajo el mínimo)."""
    datos = _subir(client, resumen_santander(), "santander.xlsx").json()
    t = next(t for t in datos["transferencias"] if not t["cuit"])
    client.patch(f"/api/transferencias/{t['id']}", json={"cuit": "27-12345678-0"})
    return t["id"]


# --------------------------------------------------------------------------- #
#  Umbral
# --------------------------------------------------------------------------- #
def test_transferencia_expone_supera_minimo(client):
    datos = _subir(client, resumen_santander(), "santander.xlsx").json()
    por_importe = {t["importe"]: t for t in datos["transferencias"]}
    assert por_importe["150000.50"]["supera_minimo"] is True
    assert por_importe["45000.00"]["supera_minimo"] is False


def test_config_expone_importe_minimo(client):
    config = client.get("/api/config").json()
    assert config["importe_minimo"] == "50000"


def test_facturar_bajo_minimo_requiere_confirmacion(client):
    tid = _transferencia_bajo_minimo(client)
    r = client.post(f"/api/transferencias/{tid}/facturar")
    assert r.status_code == 409
    assert "mínimo" in r.json()["detail"]

    ok = client.post(f"/api/transferencias/{tid}/facturar?confirmar=true").json()
    assert ok["estado"] == "emitida"


def test_lote_omite_bajo_minimo_sin_confirmar(client):
    datos = _subir(client, resumen_santander(), "santander.xlsx").json()
    ids = [t["id"] for t in datos["transferencias"] if t["cuit"]]  # 150000.50 y 80000
    facturas = client.post("/api/transferencias/facturar", json={"transferencia_ids": ids}).json()
    assert len(facturas) == 2  # ambas superan el mínimo


# --------------------------------------------------------------------------- #
#  Representación impresa (PDF con QR)
# --------------------------------------------------------------------------- #
def test_pdf_de_factura_emitida(client):
    datos = _subir(client, resumen_santander(), "santander.xlsx").json()
    tid = next(t["id"] for t in datos["transferencias"] if t["importe"] == "150000.50")
    factura = client.post(f"/api/transferencias/{tid}/facturar").json()
    r = client.get(f"/api/facturas/{factura['id']}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_pdf_de_factura_inexistente_404(client):
    assert client.get("/api/facturas/9999/pdf").status_code == 404


def test_qr_contiene_datos_afip(client):
    from app.models import Factura
    from app.services.representacion import datos_qr, url_qr

    f = Factura(
        origen="resumen_bancario",
        emisor_cuit="20111111112",
        cuit_receptor="27123456780",
        concepto_descripcion="HONORARIOS PROFESIONALES",
        tipo_comprobante=11,
        punto_venta=1,
        numero=42,
        importe="150000.50",
        fecha_comprobante=__import__("datetime").date(2026, 7, 30),
        cae="71234567890123",
        estado="emitida",
    )
    d = datos_qr(f)
    assert d["cuit"] == 20111111112
    assert d["nroDocRec"] == 27123456780
    assert d["tipoCodAut"] == "E"
    assert d["codAut"] == 71234567890123
    assert url_qr(f).startswith("https://www.afip.gob.ar/fe/qr/?p=")


# --------------------------------------------------------------------------- #
#  Integración con el gestor de alquileres
# --------------------------------------------------------------------------- #
def _liquidacion(**extra):
    base = {
        "receptor_cuit": "27-12345678-0",
        "importe": "120000.00",
        "fecha": "2026-07-31",
        "referencia_externa": "gestor:1:LIQ-0001",
        "emisor_cuit": "20111111112",
        "concepto_descripcion": "HONORARIOS PROFESIONALES",
        "razon_social": "PEREZ SA",
        "domicilio": "Calle Falsa 123",
    }
    base.update(extra)
    return base


def test_integracion_emite_factura_de_liquidacion(client):
    r = client.post("/api/integracion/liquidacion", json=_liquidacion()).json()
    assert r["estado"] == "emitida"
    assert r["factura"]["origen"] == "gestor_alquileres"
    assert r["factura"]["referencia_externa"] == "gestor:1:LIQ-0001"
    assert r["factura"]["cuit_receptor"] == "27123456780"
    assert r["factura"]["cae"]


def test_integracion_es_idempotente(client):
    primera = client.post("/api/integracion/liquidacion", json=_liquidacion()).json()
    segunda = client.post("/api/integracion/liquidacion", json=_liquidacion()).json()
    assert primera["factura"]["id"] == segunda["factura"]["id"]
    assert primera["factura"]["cae"] == segunda["factura"]["cae"]


def test_integracion_bajo_minimo_pregunta(client):
    r = client.post(
        "/api/integracion/liquidacion",
        json=_liquidacion(importe="30000.00", referencia_externa="gestor:1:LIQ-0002"),
    ).json()
    assert r["estado"] == "requiere_confirmacion"
    assert r["factura"] is None

    confirmada = client.post(
        "/api/integracion/liquidacion",
        json=_liquidacion(
            importe="30000.00",
            referencia_externa="gestor:1:LIQ-0002",
            confirmar_bajo_minimo=True,
        ),
    ).json()
    assert confirmada["estado"] == "emitida"


def test_integracion_cuit_invalido_422(client):
    r = client.post("/api/integracion/liquidacion", json=_liquidacion(receptor_cuit="123"))
    assert r.status_code == 422


def test_reconciliacion_consulta_por_referencia(client):
    emitida = client.post(
        "/api/integracion/liquidacion",
        json=_liquidacion(referencia_externa="gestor:1:LIQ-REC"),
    ).json()
    assert emitida["estado"] == "emitida"

    consulta = client.get(
        "/api/integracion/liquidacion", params={"referencia_externa": "gestor:1:LIQ-REC"}
    )
    assert consulta.status_code == 200
    datos = consulta.json()
    assert datos["estado"] == "emitida"
    assert datos["factura"]["id"] == emitida["factura"]["id"]
    assert datos["factura"]["cae"] == emitida["factura"]["cae"]


def test_reconciliacion_referencia_inexistente_404(client):
    r = client.get(
        "/api/integracion/liquidacion", params={"referencia_externa": "gestor:1:NO-EXISTE"}
    )
    assert r.status_code == 404
