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
    resultados = emision.json()
    assert len(resultados) == 2
    for r in resultados:
        assert r["estado"] == "emitida"
        f = r["factura"]
        assert f["cae"]
        assert f["concepto_descripcion"] == "HONORARIOS PROFESIONALES"
        # ARCA no informa domicilio en el padrón simulado: se autocompleta.
        assert f["domicilio"] == "Arroyo Seco"


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

    # $45.000 no supera el mínimo ($50.000): sin confirmar devuelve 409.
    sin_confirmar = client.post(f"/api/transferencias/{sin_cuit['id']}/facturar")
    assert sin_confirmar.status_code == 409

    # Con ?confirmar=true se factura igual.
    factura = client.post(
        f"/api/transferencias/{sin_cuit['id']}/facturar?confirmar=true"
    ).json()
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


def test_buscar_transferencias_en_el_servidor(client):
    """La búsqueda tiene que mirar toda la tabla, no sólo la página que ya se trajo."""
    datos = _subir(client, resumen_santander(), "santander.xlsx").json()
    con_cuit = next(t for t in datos["transferencias"] if t["cuit"])

    encontradas = client.get("/api/transferencias", params={"q": con_cuit["cuit"]}).json()
    assert [t["id"] for t in encontradas] == [con_cuit["id"]]

    assert client.get("/api/transferencias", params={"q": "no existe"}).json() == []


def test_buscar_facturas_por_cae_y_por_numero_formateado(client):
    datos = _subir(client, resumen_macro(), "macro.xlsx").json()
    factura = client.post(f"/api/transferencias/{datos['transferencias'][0]['id']}/facturar").json()

    por_cae = client.get("/api/facturas", params={"q": factura["cae"]}).json()
    assert [f["id"] for f in por_cae] == [factura["id"]]

    formateado = f"{factura['punto_venta']:04d}-{factura['numero']:08d}"
    por_numero = client.get("/api/facturas", params={"q": formateado}).json()
    assert [f["id"] for f in por_numero] == [factura["id"]]
