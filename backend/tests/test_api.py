from tests.factories import resumen_macro, resumen_pdf_en_linea, resumen_santander


def _subir(client, contenido: bytes, nombre: str):
    return client.post(
        "/api/lotes",
        files={"archivo": (nombre, contenido, "application/vnd.ms-excel")},
    )


def test_importar_y_facturar_flujo_completo(client):
    respuesta = _subir(client, resumen_santander(), "santander.xlsx")
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["nuevas"] == 3
    assert datos["sin_cuit"] == 1

    facturables = [t["id"] for t in datos["transferencias"] if t["cuit"]]
    emision = client.post("/api/transferencias/facturar", json={"transferencia_ids": facturables})
    assert emision.status_code == 200
    facturas = emision.json()
    assert len(facturas) == 2
    for factura in facturas:
        assert factura["estado"] == "emitida"
        assert factura["cae"]
        assert factura["concepto_descripcion"] == "HONORARIOS PROFESIONALES"
        # ARCA no informa domicilio en el padrón simulado: se autocompleta.
        assert factura["domicilio"] == "Arroyo Seco"


def test_importar_resumen_en_pdf(client):
    respuesta = _subir(client, resumen_pdf_en_linea(), "movimientos.pdf")
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["lote"]["banco"] == "santander"
    assert datos["nuevas"] == 2
    assert datos["sin_cuit"] == 0

    facturas = client.post(
        "/api/transferencias/facturar",
        json={"transferencia_ids": [t["id"] for t in datos["transferencias"]]},
    ).json()
    assert [f["estado"] for f in facturas] == ["emitida", "emitida"]


def test_formato_no_soportado(client):
    respuesta = _subir(client, b"cualquier cosa", "resumen.docx")
    assert respuesta.status_code == 400
    assert ".pdf" in respuesta.json()["detail"]


def test_reimportar_el_mismo_resumen_no_duplica(client):
    _subir(client, resumen_macro(), "macro.xlsx")
    segunda = _subir(client, resumen_macro(), "macro.xlsx").json()
    assert segunda["nuevas"] == 0
    assert segunda["duplicadas"] == 2


def test_no_factura_dos_veces_la_misma_transferencia(client):
    datos = _subir(client, resumen_macro(), "macro.xlsx").json()
    id_transferencia = datos["transferencias"][0]["id"]

    primera = client.post(f"/api/transferencias/{id_transferencia}/facturar").json()
    segunda = client.post(f"/api/transferencias/{id_transferencia}/facturar").json()
    assert primera["cae"] == segunda["cae"]
    assert primera["id"] == segunda["id"]


def test_completar_cuit_faltante_y_facturar(client):
    datos = _subir(client, resumen_santander(), "santander.xlsx").json()
    sin_cuit = next(t for t in datos["transferencias"] if not t["cuit"])

    invalido = client.patch(f"/api/transferencias/{sin_cuit['id']}", json={"cuit": "20305678904"})
    assert invalido.status_code == 422

    ok = client.patch(f"/api/transferencias/{sin_cuit['id']}", json={"cuit": "27-12345678-0"})
    assert ok.status_code == 200
    assert ok.json()["cuit"] == "27123456780"

    factura = client.post(f"/api/transferencias/{sin_cuit['id']}/facturar").json()
    assert factura["estado"] == "emitida"


def test_facturar_sin_cuit_devuelve_422(client):
    datos = _subir(client, resumen_santander(), "santander.xlsx").json()
    sin_cuit = next(t for t in datos["transferencias"] if not t["cuit"])
    respuesta = client.post(f"/api/transferencias/{sin_cuit['id']}/facturar")
    assert respuesta.status_code == 422


def test_transferencia_facturada_no_se_modifica(client):
    datos = _subir(client, resumen_macro(), "macro.xlsx").json()
    id_transferencia = datos["transferencias"][0]["id"]
    client.post(f"/api/transferencias/{id_transferencia}/facturar")
    respuesta = client.patch(
        f"/api/transferencias/{id_transferencia}", json={"cuit": "27123456780"}
    )
    assert respuesta.status_code == 409


def test_padron_autocompleta_domicilio(client):
    respuesta = client.get("/api/padron/20-30567890-3")
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "cuit": "20305678903",
        "razon_social": "CONTRIBUYENTE 20305678903",
        "domicilio": "Arroyo Seco",
        "domicilio_autocompletado": True,
    }


def test_config_expone_parametros_de_facturacion(client):
    config = client.get("/api/config").json()
    assert config["concepto_descripcion"] == "HONORARIOS PROFESIONALES"
    assert config["domicilio_default"] == "Arroyo Seco"
    assert config["arca_mode"] == "mock"
