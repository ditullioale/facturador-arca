"""Genera planillas de ejemplo con la forma en que exportan Santander y Macro."""

import io

from openpyxl import Workbook


def _a_bytes(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def resumen_santander() -> bytes:
    wb = Workbook()
    hoja = wb.active
    hoja.append(["Banco Santander Argentina"])
    hoja.append(["Cuenta corriente en pesos 123-456/7"])
    hoja.append([])
    hoja.append(["Fecha", "Sucursal", "Concepto", "Débito", "Crédito", "Saldo"])
    hoja.append(["01/07/2026", "015", "TRANSFERENCIA RECIBIDA DE 20-30567890-3 PEREZ SA", "", "150000,50", "150000,50"])
    hoja.append(["02/07/2026", "015", "COMISION MANTENIMIENTO", "3500,00", "", "146500,50"])
    hoja.append(["03/07/2026", "015", "TRANSFERENCIA RECIBIDA CUIT 27-12345678-0 GOMEZ ANA", "", "80000,00", "226500,50"])
    hoja.append(["04/07/2026", "015", "PAGO DE SERVICIOS", "12000,00", "", "214500,50"])
    hoja.append(["05/07/2026", "015", "TRANSFERENCIA RECIBIDA SIN DATOS", "", "45000,00", "259500,50"])
    return _a_bytes(wb)


def resumen_macro() -> bytes:
    wb = Workbook()
    hoja = wb.active
    hoja.append(["BANCO MACRO S.A. - Movimientos"])
    hoja.append(["Fecha", "Descripción", "CUIT Ordenante", "Importe", "Saldo"])
    hoja.append(["10/07/2026", "CREDITO INMEDIATO", "30-71234567-1", 250000.75, 250000.75])
    hoja.append(["11/07/2026", "DEBITO AUTOMATICO SEGURO", "", -5000, 245000.75])
    hoja.append(["12/07/2026", "TRANSFERENCIA ENTRE CUENTAS", "20305678903", 99000, 344000.75])
    return _a_bytes(wb)
