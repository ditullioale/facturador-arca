"""Tests de idempotencia (anti-duplicado), auditoría y lote estructurado."""

from datetime import date

import app.services.facturacion as fact
from app.services.arca.wsfe import ResultadoDesconocido, ResultadoEmision
from tests.factories import resumen_santander


def _subir(client, contenido, nombre):
    return client.post("/api/lotes", files={"archivo": (nombre, contenido, "application/x")})


def _transferencia_con_cuit(client):
    datos = _subir(client, resumen_santander(), "s.xlsx").json()
    return next(t["id"] for t in datos["transferencias"] if t["cuit"])


class _FacturadorDesconocido:
    """emitir siempre queda en resultado desconocido; consultar dice que NO existe."""

    def emitir(self, solicitud):
        raise ResultadoDesconocido(4242)

    def consultar(self, punto_venta, tipo_comprobante, numero):
        return None


class _FacturadorReconcilia:
    """emitir explota si se llama (no debería); consultar dice que SÍ existe con CAE."""

    def emitir(self, solicitud):
        raise AssertionError("no debería re-emitir: hay que reconciliar")

    def consultar(self, punto_venta, tipo_comprobante, numero):
        return ResultadoEmision(
            numero=numero, cae="CAE-RECONCILIADO",
            cae_vencimiento=date(2026, 8, 10), observaciones=[],
        )


def test_timeout_no_duplica_reconcilia_con_consultar(client, monkeypatch):
    tid = _transferencia_con_cuit(client)

    # 1) Primer intento: timeout -> queda "revisar" con numero_intentado, sin CAE.
    monkeypatch.setattr(fact, "get_facturador_para", lambda emisor: _FacturadorDesconocido())
    r1 = client.post(f"/api/transferencias/{tid}/facturar").json()
    assert r1["estado"] == "revisar"
    assert r1["numero_intentado"] == 4242
    assert r1["cae"] is None

    # 2) Reintento: ARCA dice que el 4242 SÍ se había autorizado -> adopta el CAE, no re-emite.
    monkeypatch.setattr(fact, "get_facturador_para", lambda emisor: _FacturadorReconcilia())
    r2 = client.post(f"/api/transferencias/{tid}/facturar").json()
    assert r2["estado"] == "emitida"
    assert r2["cae"] == "CAE-RECONCILIADO"
    assert r2["numero_intentado"] is None


def test_reconciliacion_negativa_permite_reintentar(client, monkeypatch):
    tid = _transferencia_con_cuit(client)
    monkeypatch.setattr(fact, "get_facturador_para", lambda emisor: _FacturadorDesconocido())
    assert client.post(f"/api/transferencias/{tid}/facturar").json()["estado"] == "revisar"

    # consultar dice que NO existe -> es seguro reintentar y ahora emite bien (mock real).
    from app.services.arca.wsfe import FacturadorMock

    class _NoExisteLuegoEmite(FacturadorMock):
        def consultar(self, pv, tipo, nro):
            return None

    monkeypatch.setattr(fact, "get_facturador_para", lambda emisor: _NoExisteLuegoEmite())
    r = client.post(f"/api/transferencias/{tid}/facturar").json()
    assert r["estado"] == "emitida"
    assert r["cae"]


def test_auditoria_registra_emisiones(client):
    tid = _transferencia_con_cuit(client)
    client.post(f"/api/transferencias/{tid}/facturar")
    aud = client.get("/api/auditoria").json()
    assert len(aud) >= 1
    assert aud[0]["operacion"] == "emitir"
    assert aud[0]["resultado"] == "emitida"
    assert aud[0]["cae"]


def test_lote_estructurado_muestra_lo_que_quedo_afuera(client):
    datos = _subir(client, resumen_santander(), "s.xlsx").json()
    ids = [t["id"] for t in datos["transferencias"]]  # incluye una SIN cuit
    resultados = client.post("/api/transferencias/facturar", json={"transferencia_ids": ids}).json()
    estados = sorted(r["estado"] for r in resultados)
    assert "sin_cuit" in estados  # ya no se omite en silencio
    assert estados.count("emitida") == 2


def test_paginacion_transferencias(client):
    _subir(client, resumen_santander(), "s.xlsx")
    una = client.get("/api/transferencias?limit=1").json()
    assert len(una) == 1
    dos = client.get("/api/transferencias?limit=2&offset=1").json()
    assert len(dos) == 2
    assert dos[0]["id"] != una[0]["id"]
