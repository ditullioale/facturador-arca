"""Tests de multiempresa: alta de emisores, auth por token y aislamiento de datos."""

from tests.factories import resumen_santander

ADMIN = {"X-Admin-Token": "admin-test"}


def _alta(client, cuit, mode="mock"):
    r = client.post(
        "/api/emisores",
        json={"cuit": cuit, "arca_mode": mode, "punto_venta": 1, "tipo_comprobante": 11},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _subir(client, headers=None):
    return client.post(
        "/api/lotes",
        files={"archivo": ("s.xlsx", resumen_santander(), "application/x")},
        headers=headers or {},
    )


def test_alta_emisor_requiere_admin(client):
    # sin token de admin -> 401
    r = client.post("/api/emisores", json={"cuit": "20305903990"}, headers={})
    assert r.status_code == 401
    # con token de admin -> 200 y devuelve token del emisor
    r2 = client.post("/api/emisores", json={"cuit": "20305903990"}, headers=ADMIN)
    assert r2.status_code == 200
    assert r2.json()["token"]
    assert r2.json()["emisor"]["cuit"] == "20305903990"


def test_token_invalido_rechazado(client):
    r = client.get("/api/transferencias", headers={"Authorization": "Bearer no-existe"})
    assert r.status_code == 401


def test_aislamiento_entre_emisores(client):
    token_a = _alta(client, "20305903990")
    token_b = _alta(client, "27123456780")
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}

    # A sube un resumen; B no sube nada.
    assert _subir(client, auth_a).status_code == 201

    lista_a = client.get("/api/transferencias", headers=auth_a).json()
    lista_b = client.get("/api/transferencias", headers=auth_b).json()
    assert len(lista_a) == 3  # las nuevas del resumen santander
    assert lista_b == []       # B no ve nada de A

    # B no puede facturar una transferencia de A (aislamiento -> 404).
    tid_a = lista_a[0]["id"]
    assert client.post(f"/api/transferencias/{tid_a}/facturar", headers=auth_b).status_code == 404

    # A factura la suya y queda en SU listado de facturas; B ve 0 facturas.
    facturable = next(t["id"] for t in lista_a if t["cuit"])
    emit = client.post(f"/api/transferencias/{facturable}/facturar", headers=auth_a).json()
    assert emit["estado"] == "emitida"
    assert len(client.get("/api/facturas", headers=auth_a).json()) == 1
    assert client.get("/api/facturas", headers=auth_b).json() == []


def test_config_por_emisor(client):
    token = _alta(client, "20305903990", mode="mock")
    cfg = client.get("/api/config", headers={"Authorization": f"Bearer {token}"}).json()
    assert cfg["arca_cuit"] == "20305903990"
    assert cfg["arca_mode"] == "mock"


def test_compatibilidad_emisor_por_defecto(client):
    # Sin token: usa el emisor por defecto (de las variables de entorno) y funciona igual.
    assert _subir(client).status_code == 201
    assert len(client.get("/api/transferencias").json()) == 3
    cfg = client.get("/api/config").json()
    assert cfg["arca_cuit"] == "20111111112"  # el ARCA_CUIT del entorno
