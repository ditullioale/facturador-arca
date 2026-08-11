"""Pasaje de prueba (mock/homologación) a producción real.

Cubre tres comportamientos clave para no bloquear la emisión real:
1. El emisor por defecto sincroniza su modo/punto de venta desde las variables de entorno.
2. Una liquidación facturada en mock NO bloquea la emisión real (idempotencia por modo).
3. Una transferencia facturada en mock NO bloquea la emisión real, y luego es idempotente.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AuditoriaArca, Emisor, Factura, Lote, Transferencia
from app.services import emisores, facturacion


def _db():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, autoflush=False, autocommit=False)()


def test_emisor_por_defecto_sincroniza_modo(monkeypatch):
    db = _db()
    db.add(Emisor(cuit="20305903990", punto_venta=1, tipo_comprobante=11,
                  arca_mode="homologacion", consultar_padron=True, por_defecto=True, activo=True))
    db.commit()
    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    monkeypatch.setattr(s, "arca_mode", "produccion")
    monkeypatch.setattr(s, "arca_punto_venta", 7)
    e = emisores.emisor_por_defecto(db)
    assert e.arca_mode == "produccion" and e.punto_venta == 7


def _emisor_prod(db):
    e = Emisor(cuit="20305903990", punto_venta=7, tipo_comprobante=11,
               arca_mode="produccion", consultar_padron=False, por_defecto=True, activo=True)
    db.add(e); db.commit(); db.refresh(e)
    return e


def _fake_emitir(monkeypatch):
    llamado = {"n": 0}

    def fake(db, factura, emisor, cond):
        llamado["n"] += 1
        factura.estado = "emitida"; factura.cae = "86327784730732"; factura.numero = 1
        db.add(AuditoriaArca(factura_id=factura.id, emisor_id=emisor.id, operacion="emitir",
                             modo=emisor.arca_mode, resultado="emitida"))
        db.commit(); db.refresh(factura)
        return factura

    monkeypatch.setattr(facturacion, "_emitir_en_arca", fake)
    return llamado


def test_liquidacion_mock_no_bloquea_produccion(monkeypatch):
    db = _db(); emisor = _emisor_prod(db)
    ref = "gestor:1:julio"
    f = Factura(emisor_id=emisor.id, origen="gestor_alquileres", referencia_externa=ref,
                cuit_receptor="20111111112", concepto_descripcion="HON", tipo_comprobante=11,
                punto_venta=1, importe=Decimal("60000"), fecha_comprobante=date.today(),
                cae="70000000000001", estado="emitida")
    db.add(f); db.commit(); db.refresh(f)
    db.add(AuditoriaArca(factura_id=f.id, emisor_id=emisor.id, operacion="emitir",
                         modo="mock", resultado="emitida")); db.commit()
    assert facturacion._emitida_en_modo(db, f, "produccion") is False
    llamado = _fake_emitir(monkeypatch)
    facturacion.emitir_factura_directa(db, emisor, receptor_cuit="20111111112",
        importe=Decimal("60000"), fecha=date.today(), referencia_externa=ref,
        razon_social="X", domicilio="Y")
    assert llamado["n"] == 1
    # Segunda vez en produccion -> idempotente
    facturacion.emitir_factura_directa(db, emisor, receptor_cuit="20111111112",
        importe=Decimal("60000"), fecha=date.today(), referencia_externa=ref,
        razon_social="X", domicilio="Y")
    assert llamado["n"] == 1


def test_transferencia_mock_no_bloquea_produccion(monkeypatch):
    db = _db(); emisor = _emisor_prod(db)
    lote = Lote(emisor_id=emisor.id, nombre_archivo="julio.xlsx", banco="X")
    db.add(lote); db.commit(); db.refresh(lote)
    t = Transferencia(lote_id=lote.id, emisor_id=emisor.id, banco="X", fecha=date.today(),
                      cuit="20111111112", importe=Decimal("80000"), descripcion="hon",
                      huella="h1", estado="facturada")
    db.add(t); db.commit(); db.refresh(t)
    f = Factura(transferencia_id=t.id, emisor_id=emisor.id, origen="resumen_bancario",
                cuit_receptor="20111111112", concepto_descripcion="HON", tipo_comprobante=11,
                punto_venta=1, importe=Decimal("80000"), fecha_comprobante=date.today(),
                cae="70000000000009", estado="emitida")
    db.add(f); db.commit(); db.refresh(f)
    db.add(AuditoriaArca(factura_id=f.id, emisor_id=emisor.id, operacion="emitir",
                         modo="mock", resultado="emitida")); db.commit()
    llamado = _fake_emitir(monkeypatch)
    res = facturacion.emitir_factura(db, t, emisor)
    assert llamado["n"] == 1
    # Al re-emitir usa el punto de venta ACTUAL del emisor (7 = producción), no el de la
    # factura de prueba (1 = mock), que en producción ARCA rechaza.
    assert res.punto_venta == 7, res.punto_venta
    facturacion.emitir_factura(db, t, emisor)   # idempotente
    assert llamado["n"] == 1
