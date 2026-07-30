from decimal import Decimal

import pytest

from app.services.cuit import es_cuit_valido, extraer_cuit
from app.services.excel_parser import ErrorDeParseo, parsear_resumen
from tests.factories import resumen_macro, resumen_santander


def test_parsea_transferencias_recibidas_de_santander():
    resultado = parsear_resumen(resumen_santander(), "resumen santander julio.xlsx")

    assert resultado.banco == "santander"
    assert len(resultado.movimientos) == 3
    primero = resultado.movimientos[0]
    assert primero.cuit == "20305678903"
    assert primero.importe == Decimal("150000.50")
    assert primero.fecha.isoformat() == "2026-07-01"
    # El movimiento sin CUIT se importa igual para que el usuario lo complete.
    assert resultado.movimientos[2].cuit is None


def test_ignora_debitos_y_comisiones():
    resultado = parsear_resumen(resumen_santander(), "santander.xlsx")
    descripciones = " ".join(m.descripcion.upper() for m in resultado.movimientos)
    assert "COMISION" not in descripciones
    assert "PAGO DE SERVICIOS" not in descripciones


def test_parsea_macro_con_columna_de_cuit_e_importe_unico():
    resultado = parsear_resumen(resumen_macro(), "macro.xlsx")

    assert resultado.banco == "macro"
    cuits = [m.cuit for m in resultado.movimientos]
    assert cuits == ["30712345671", "20305678903"]
    assert resultado.movimientos[0].importe == Decimal("250000.75")


def test_huella_es_estable_para_deduplicar():
    a = parsear_resumen(resumen_macro(), "macro.xlsx").movimientos
    b = parsear_resumen(resumen_macro(), "macro copia.xlsx").movimientos
    assert [m.huella for m in a] == [m.huella for m in b]


def test_archivo_sin_encabezados_reconocibles():
    with pytest.raises(ErrorDeParseo):
        parsear_resumen(b"col1;col2\n1;2\n", "cualquiera.csv")


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("20-30567890-3", True), ("20305678903", True), ("20305678904", False), ("123", False)],
)
def test_validacion_de_cuit(valor, esperado):
    assert es_cuit_valido(valor) is esperado


def test_extrae_cuit_de_texto_libre():
    assert extraer_cuit("TRF DE 27-12345678-0 GOMEZ") == "27123456780"
    assert extraer_cuit("TRF SIN CUIT 12345") is None
