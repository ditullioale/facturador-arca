"""Genera resúmenes de ejemplo con la forma en que exportan Santander y Macro."""

import io

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


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


def pdf_con_lineas(paginas: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    lienzo = canvas.Canvas(buffer, pagesize=A4)
    for lineas in paginas:
        y = A4[1] - 50
        for linea in lineas:
            lienzo.drawString(40, y, linea)
            y -= 16
        lienzo.showPage()
    lienzo.save()
    return buffer.getvalue()


def resumen_pdf_en_linea() -> bytes:
    """PDF con el listado normal: fecha, descripción e importe en la misma línea."""
    return pdf_con_lineas(
        [
            [
                "Banco Santander - Ultimos movimientos",
                "Fecha Descripcion Importe",
                "30/07/2026 Transferencia recibida De perez sa / transf / 20-30567890-3 150000.50",
                "29/07/2026 Compra con tarjeta de debito Farmacia - tarj nro. 2624 -32400.00",
                "28/07/2026 Transferencia recibida De gomez ana / var / 27-12345678-0 80000.00",
                "27/07/2026 Transferencia inmediata A proveedor sa / 30-71234567-1 -24000.00",
                "26/07/2026 Comision mantenimiento de cuenta -3500.00",
            ]
        ]
    )


def resumen_pdf_por_columnas() -> bytes:
    """PDF impreso desde una planilla ancha: cada bloque de páginas trae una columna."""
    return pdf_con_lineas(
        [
            [
                "Cuenta unica 060-360920/4 - Work Cafe",
                "Fecha Sucursal origen",
                "30/07/2026 464 - ARROYO SECO",
                "29/07/2026 000 - CASA CENTRAL",
                "28/07/2026 464 - ARROYO SECO",
            ],
            [
                "Descripcion Referencia Caja de Ahorro",
                "Transferencia recibida - credin cuit 27343814289 07511591 66000.00",
                "Compra con tarjeta de debito Farina - tarj nro. 2624 08189504 -8000.00",
                "Transf recibida cvu dif titular De julian / 20-30567890-3 33254226 260000.00",
            ],
            [
                "Cuenta Corriente Saldo",
                "1993298.59",
                "1985298.59",
                "2245298.59",
            ],
        ]
    )


def resumen_macro() -> bytes:
    wb = Workbook()
    hoja = wb.active
    hoja.append(["BANCO MACRO S.A. - Movimientos"])
    hoja.append(["Fecha", "Descripción", "CUIT Ordenante", "Importe", "Saldo"])
    hoja.append(["10/07/2026", "CREDITO INMEDIATO", "30-71234567-1", 250000.75, 250000.75])
    hoja.append(["11/07/2026", "DEBITO AUTOMATICO SEGURO", "", -5000, 245000.75])
    hoja.append(["12/07/2026", "TRANSFERENCIA ENTRE CUENTAS", "20305678903", 99000, 344000.75])
    return _a_bytes(wb)
