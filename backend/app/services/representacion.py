"""Representación impresa del comprobante (PDF) con el código QR de AFIP (RG 4291).

El QR codifica un JSON en base64 apuntado a la página de constatación de AFIP:
https://www.afip.gob.ar/fe/qr/?p=<base64(json)>

Especificación: https://www.afip.gob.ar/fe/qr/documentos/QRespecificaciones.pdf
"""

from __future__ import annotations

import base64
import io
import json
from decimal import Decimal

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.config import get_settings
from app.models import Factura

URL_QR = "https://www.afip.gob.ar/fe/qr/?p="

TIPOS_COMPROBANTE = {
    1: "FACTURA A",
    6: "FACTURA B",
    11: "FACTURA C",
    51: "FACTURA M",
}
LETRAS = {1: "A", 6: "B", 11: "C", 51: "M"}


def datos_qr(factura: Factura) -> dict[str, object]:
    """Arma el diccionario que se codifica en el QR según la especificación de AFIP."""
    settings = get_settings()
    emisor = factura.emisor_cuit or settings.arca_cuit or "0"
    return {
        "ver": 1,
        "fecha": factura.fecha_comprobante.isoformat(),
        "cuit": int(emisor),
        "ptoVta": int(factura.punto_venta),
        "tipoCmp": int(factura.tipo_comprobante),
        "nroCmp": int(factura.numero or 0),
        "importe": float(Decimal(factura.importe)),
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": 80,  # 80 = CUIT
        "nroDocRec": int(factura.cuit_receptor),
        "tipoCodAut": "E",  # E = CAE
        "codAut": int(factura.cae) if factura.cae and factura.cae.isdigit() else 0,
    }


def url_qr(factura: Factura) -> str:
    crudo = json.dumps(datos_qr(factura), separators=(",", ":")).encode("ascii")
    return URL_QR + base64.b64encode(crudo).decode("ascii")


def _cuit_formateado(cuit: str | None) -> str:
    if not cuit or len(cuit) != 11:
        return cuit or "—"
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}"


def _money(valor) -> str:
    """Formatea un importe en formato argentino: 1.234.567,89."""
    return f"{Decimal(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def generar_pdf(factura: Factura) -> bytes:
    """Genera el PDF del comprobante. Requiere que la factura esté emitida (con CAE)."""
    settings = get_settings()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    ancho, alto = A4
    x = 20 * mm
    y = alto - 25 * mm

    letra = LETRAS.get(factura.tipo_comprobante, "C")
    titulo = TIPOS_COMPROBANTE.get(factura.tipo_comprobante, "COMPROBANTE")

    # Encabezado
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, "COMPROBANTE ELECTRÓNICO")
    c.setFont("Helvetica-Bold", 22)
    c.drawRightString(ancho - 20 * mm, y, letra)
    c.setFont("Helvetica", 9)
    c.drawRightString(ancho - 20 * mm, y - 6 * mm, titulo)
    y -= 12 * mm

    numero = f"{factura.punto_venta:04d}-{(factura.numero or 0):08d}"
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, f"Nro: {numero}")
    c.drawRightString(ancho - 20 * mm, y, f"Fecha: {factura.fecha_comprobante:%d/%m/%Y}")
    y -= 10 * mm

    # Emisor
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Emisor")
    c.setFont("Helvetica", 10)
    y -= 5 * mm
    c.drawString(x, y, f"CUIT: {_cuit_formateado(factura.emisor_cuit or settings.arca_cuit)}")
    y -= 5 * mm
    c.drawString(x, y, f"Punto de venta: {factura.punto_venta}")
    y -= 10 * mm

    # Receptor
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Receptor")
    c.setFont("Helvetica", 10)
    y -= 5 * mm
    c.drawString(x, y, f"CUIT: {_cuit_formateado(factura.cuit_receptor)}")
    y -= 5 * mm
    c.drawString(x, y, f"Razón social: {factura.razon_social or '—'}")
    y -= 5 * mm
    c.drawString(x, y, f"Domicilio: {factura.domicilio or '—'}")
    y -= 12 * mm

    # Detalle
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Detalle")
    c.setFont("Helvetica", 10)
    y -= 5 * mm
    c.drawString(x, y, factura.concepto_descripcion)
    c.drawRightString(ancho - 20 * mm, y, f"$ {_money(factura.importe)}")
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(ancho - 20 * mm, y, f"TOTAL: $ {_money(factura.importe)}")
    y -= 14 * mm

    # CAE
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, f"CAE: {factura.cae or '—'}")
    if factura.cae_vencimiento:
        c.drawString(x + 70 * mm, y, f"Vto CAE: {factura.cae_vencimiento:%d/%m/%Y}")
    y -= 8 * mm

    if settings.arca_mode == "mock":
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColorRGB(0.6, 0, 0)
        c.drawString(x, y, "COMPROBANTE SIMULADO (ARCA_MODE=mock): no tiene validez fiscal.")
        c.setFillColorRGB(0, 0, 0)

    # QR (RG 4291), abajo a la izquierda
    dibujo_qr = qr.QrCodeWidget(url_qr(factura))
    limites = dibujo_qr.getBounds()
    lado = 32 * mm
    escala_x = lado / (limites[2] - limites[0])
    escala_y = lado / (limites[3] - limites[1])
    d = Drawing(lado, lado, transform=[escala_x, 0, 0, escala_y, 0, 0])
    d.add(dibujo_qr)
    renderPDF.draw(d, c, x, 20 * mm)
    c.setFont("Helvetica", 7)
    c.drawString(x, 15 * mm, "Verificá el comprobante escaneando el QR (serviciosweb.afip.gob.ar)")

    c.showPage()
    c.save()
    return buffer.getvalue()
