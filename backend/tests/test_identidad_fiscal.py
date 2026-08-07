"""Fase 5.1 — La identidad fiscal (el emisor) la determina SIEMPRE el token, nunca el
cuerpo del request. Es una frontera de seguridad: el consumidor (Finart) no puede
elegir bajo qué CUIT se emite.
"""

from tests.test_multiempresa import _alta


def _liq(**extra):
    base = {
        "receptor_cuit": "27-12345678-0",
        "importe": "120000.00",
        "fecha": "2026-07-31",
        "referencia_externa": "gestor:1:IDENT",
        "concepto_descripcion": "HONORARIOS PROFESIONALES",
        "razon_social": "PEREZ SA",
        "domicilio": "Calle 1",
    }
    base.update(extra)
    return base


def _emitir(client, token, **extra):
    return client.post(
        "/api/integracion/liquidacion",
        json=_liq(**extra),
        headers={"Authorization": f"Bearer {token}"},
    )


def test_cada_token_emite_bajo_su_propio_emisor(client):
    """Token A → CUIT A, Token B → CUIT B (sin que el cuerpo diga nada)."""
    token_a = _alta(client, "20305903990")
    token_b = _alta(client, "27123456780")
    ra = _emitir(client, token_a, referencia_externa="gestor:1:A").json()
    rb = _emitir(client, token_b, referencia_externa="gestor:1:B").json()
    assert ra["estado"] == "emitida" and ra["factura"]["emisor_cuit"] == "20305903990"
    assert rb["estado"] == "emitida" and rb["factura"]["emisor_cuit"] == "27123456780"


def test_emisor_cuit_ajeno_es_rechazado(client):
    """El cliente intenta forzar OTRO emisor en el cuerpo → se rechaza (no se emite)."""
    token_a = _alta(client, "20305903990")
    r = _emitir(client, token_a, emisor_cuit="27123456780",
                referencia_externa="gestor:1:HOSTIL").json()
    assert r["estado"] == "error"
    assert "no coincide" in (r["mensaje"] or "").lower()


def test_emisor_cuit_propio_se_acepta(client):
    """Si el cuerpo repite el CUIT propio (el del token), se acepta."""
    token_a = _alta(client, "20305903990")
    r = _emitir(client, token_a, emisor_cuit="20305903990",
                referencia_externa="gestor:1:PROPIO").json()
    assert r["estado"] == "emitida"


def test_token_invalido_401(client):
    assert _emitir(client, "token-que-no-existe",
                   referencia_externa="gestor:1:INV").status_code == 401


def test_token_revocado_por_rotacion_401(client):
    """Rotar el token del emisor (volver a darlo de alta) invalida el token viejo."""
    token_viejo = _alta(client, "20305903990")
    _alta(client, "20305903990")   # rota el token
    assert _emitir(client, token_viejo,
                   referencia_externa="gestor:1:ROT").status_code == 401


def test_sin_token_usa_emisor_por_defecto(client):
    """Sin token cae al emisor por defecto (compatibilidad de una sola empresa).
    En un deploy multiempresa puro (sin ARCA_CUIT) esto sería 401."""
    r = client.post("/api/integracion/liquidacion", json=_liq(referencia_externa="gestor:1:DEF"))
    assert r.status_code == 200
    assert r.json()["factura"]["emisor_cuit"] == "20111111112"
