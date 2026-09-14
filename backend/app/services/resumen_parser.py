"""Parseo de resúmenes bancarios en Excel/CSV/PDF (Santander, Macro y formatos similares).

Los bancos exportan planillas con encabezados en filas variables y nombres de columna
distintos, por lo que el parser detecta el encabezado y mapea las columnas por nombre
en lugar de asumir posiciones fijas.

Para PDF hay dos formas posibles: el listado normal, donde fecha, descripción e importe
viven en la misma línea, y el PDF impreso desde una planilla ancha, donde cada bloque de
páginas trae una columna distinta y las filas hay que reconstruirlas por orden.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd
import pdfplumber

from app.services.cuit import extraer_cuit, normalizar_cuit

RE_FECHA = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
RE_IMPORTE_FINAL = re.compile(
    r"("
    r"-?\$?\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})"  # con miles y decimales: 1.234,56
    r"|-?\$?\s?\d+[.,]\d{2}"  # simple con decimales: 1234.56
    r"|-?\$\s?\d{1,3}(?:\.\d{3})+"  # monto redondo con $ y miles, sin decimales: $480.000
    r")\s*$"
)

PALABRAS_ENCABEZADO = (
    "fecha",
    "importe",
    "credito",
    "debito",
    "concepto",
    "descripcion",
    "detalle",
    "movimiento",
    "saldo",
    "cuit",
    "referencia",
    "origen",
)

PALABRAS_TRANSFERENCIA = (
    "transferencia",
    "transf",
    "trf",
    "credito inmediato",
    "cred inmediato",
    "acreditacion",
    "deposito por transferencia",
    "debin",
    "interbanking",
    "pago recibido",
)

PALABRAS_DESCRIPCION = (
    "concepto",
    "descripcion",
    "detalle",
    "movimiento",
    "referencia",
    "origen",
    "ordenante",
)

# Claves que identifican al banco en el encabezado del resumen ("work cafe" es Santander).
BANCOS = {"santander": "santander", "work cafe": "santander", "macro": "macro"}


@dataclass
class MovimientoParseado:
    fecha: date
    importe: Decimal
    descripcion: str
    cuit: str | None

    @property
    def huella(self) -> str:
        base = "|".join(
            [self.fecha.isoformat(), str(self.importe), self.cuit or "", self.descripcion.lower()]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()


@dataclass
class ResultadoParseo:
    banco: str
    cantidad_filas: int
    movimientos: list[MovimientoParseado]


class ErrorDeParseo(ValueError):
    pass


def _sin_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def _normalizar(valor: object) -> str:
    return re.sub(r"\s+", " ", _sin_acentos(str(valor or "")).strip().lower())


def _leer_planilla(contenido: bytes, nombre_archivo: str) -> pd.DataFrame:
    nombre = nombre_archivo.lower()
    if nombre.endswith(".csv"):
        for sep in (";", ",", "\t"):
            df = pd.read_csv(io.BytesIO(contenido), header=None, dtype=object, sep=sep)
            if df.shape[1] > 1:
                return df
        return df
    motor = "xlrd" if nombre.endswith(".xls") else "openpyxl"
    return pd.read_excel(io.BytesIO(contenido), header=None, dtype=object, engine=motor)


def _detectar_banco_en_texto(texto: str) -> str:
    normalizado = _normalizar(texto)
    for clave, banco in BANCOS.items():
        if clave in normalizado:
            return banco
    return "desconocido"


def _detectar_banco(df: pd.DataFrame, nombre_archivo: str) -> str:
    celdas = " ".join(_normalizar(v) for v in df.head(15).to_numpy().flatten())
    return _detectar_banco_en_texto(f"{nombre_archivo} {celdas}")


def _fila_encabezado(df: pd.DataFrame) -> int:
    for idx in range(min(len(df), 30)):
        celdas = [_normalizar(v) for v in df.iloc[idx].tolist()]
        coincidencias = sum(
            1 for celda in celdas if any(p in celda for p in PALABRAS_ENCABEZADO) and celda
        )
        if coincidencias >= 2:
            return idx
    raise ErrorDeParseo(
        "No se encontró la fila de encabezados. Se esperaban columnas de fecha e importe."
    )


def _mapear_columnas(encabezados: list[str]) -> dict[str, list[int]]:
    mapa: dict[str, list[int]] = {
        "fecha": [],
        "credito": [],
        "debito": [],
        "importe": [],
        "descripcion": [],
        "cuit": [],
    }
    for idx, encabezado in enumerate(encabezados):
        if not encabezado:
            continue
        if "fecha" in encabezado:
            mapa["fecha"].append(idx)
        elif "cuit" in encabezado or "cuil" in encabezado:
            mapa["cuit"].append(idx)
        elif "credito" in encabezado or "haber" in encabezado:
            mapa["credito"].append(idx)
        elif "debito" in encabezado or "debe" in encabezado:
            mapa["debito"].append(idx)
        elif "importe" in encabezado or "monto" in encabezado:
            mapa["importe"].append(idx)
        elif (
            "caja de ahorro" in encabezado
            or "caja ahorro" in encabezado
            or "cuenta corriente" in encabezado
            or "cta cte" in encabezado
        ):
            # Santander exporta el movimiento (con signo) en la columna de la
            # cuenta: "Caja de Ahorro" / "Cuenta Corriente". Positivo = crédito
            # recibido, negativo = débito (se descarta después por importe <= 0).
            mapa["importe"].append(idx)
        elif any(p in encabezado for p in PALABRAS_DESCRIPCION):
            mapa["descripcion"].append(idx)
    return mapa


def _a_decimal(valor: object) -> Decimal | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, int | float | Decimal):
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    texto = str(valor).strip()
    if not texto:
        return None
    negativo = texto.startswith("(") and texto.endswith(")")
    texto = re.sub(r"[^\d,.\-]", "", texto)
    if not texto:
        return None
    if "," in texto and "." in texto:
        # Formato local: 1.234,56
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    elif "." in texto:
        # Solo puntos: en es-AR son separadores de miles cuando hay varios
        # (1.234.567) o cuando el único grupo tiene 3 dígitos y no hay decimales
        # (480.000 = 480000). Un punto con 1-2 dígitos (1234.56) es decimal.
        partes = texto.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
            texto = texto.replace(".", "")
    try:
        monto = Decimal(texto).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return -monto if negativo else monto


def _a_fecha(valor: object) -> date | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    marca = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    if pd.isna(marca):
        return None
    return marca.date()


def _lineas_pdf(contenido: bytes) -> list[str]:
    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            paginas = [pagina.extract_text() or "" for pagina in pdf.pages]
    except Exception as exc:  # noqa: BLE001 - pdfplumber levanta excepciones heterogéneas
        raise ErrorDeParseo(f"No se pudo leer el PDF: {exc}") from exc
    lineas = [linea.strip() for pagina in paginas for linea in pagina.split("\n")]
    if not any(lineas):
        raise ErrorDeParseo(
            "El PDF no tiene texto seleccionable (parece escaneado). Exportá el resumen en "
            "Excel/CSV o en un PDF de texto."
        )
    return [linea for linea in lineas if linea]


def _importe_final(linea: str) -> tuple[Decimal, str] | None:
    """Separa el importe del final de la línea y devuelve (importe, resto de la línea)."""
    match = RE_IMPORTE_FINAL.search(linea)
    if match is None:
        return None
    importe = _a_decimal(match.group(1))
    if importe is None:
        return None
    return importe, linea[: match.start()].strip()


def _movimiento(fecha: date, importe: Decimal, descripcion: str) -> MovimientoParseado | None:
    if importe <= 0:
        return None
    cuit = extraer_cuit(descripcion)
    if not _es_transferencia(descripcion, cuit is not None):
        return None
    return MovimientoParseado(
        fecha=fecha, importe=importe, descripcion=descripcion[:500], cuit=cuit
    )


def _es_linea_movimiento(linea: str) -> bool:
    """La línea tiene fecha e importe juntos (es la fila del movimiento)."""
    return RE_FECHA.search(linea) is not None and _importe_final(linea) is not None


def _movimientos_en_linea(lineas: list[str]) -> list[MovimientoParseado]:
    """PDF con una fila por línea.

    Cubre dos variantes: la fecha, descripción e importe en la misma línea, y el
    formato tipo Santander donde la línea del importe trae sólo fecha y monto y el
    concepto/detalle (con el CUIT) quedan en las líneas de arriba y abajo.
    """
    movimientos: list[MovimientoParseado] = []
    total = len(lineas)
    for indice, linea in enumerate(lineas):
        match_fecha = RE_FECHA.search(linea)
        partido = _importe_final(linea)
        if match_fecha is None or partido is None:
            continue
        fecha = _a_fecha(match_fecha.group(0))
        if fecha is None:
            continue
        importe, resto = partido
        descripcion = _sin_fechas(resto)
        if not descripcion:
            contexto = []
            if indice > 0 and not _es_linea_movimiento(lineas[indice - 1]):
                contexto.append(lineas[indice - 1])
            if indice + 1 < total and not _es_linea_movimiento(lineas[indice + 1]):
                contexto.append(lineas[indice + 1])
            descripcion = _sin_fechas(" ".join(contexto))
        movimiento = _movimiento(fecha, importe, descripcion)
        if movimiento is not None:
            movimientos.append(movimiento)
    return movimientos


def _movimientos_por_columnas(lineas: list[str]) -> list[MovimientoParseado]:
    """PDF impreso desde una planilla ancha: las columnas quedan en bloques de páginas.

    Se reconstruyen las filas por orden: la enésima línea de fechas corresponde al enésimo
    movimiento con descripción e importe. Las líneas que son sólo un número (columna de
    saldo) se descartan.
    """
    fechas: list[date] = []
    detalles: list[tuple[Decimal, str]] = []
    for linea in lineas:
        match_fecha = RE_FECHA.match(linea)
        partido = _importe_final(linea)
        if match_fecha is not None and partido is None:
            fecha = _a_fecha(match_fecha.group(0))
            if fecha is not None:
                fechas.append(fecha)
        elif partido is not None and match_fecha is None:
            importe, resto = partido
            if resto:
                detalles.append((importe, resto))

    if not fechas or not detalles:
        return []
    if len(fechas) != len(detalles):
        raise ErrorDeParseo(
            f"El PDF tiene {len(fechas)} fechas y {len(detalles)} movimientos: no se pueden "
            "emparejar las filas. Exportá el resumen en Excel/CSV."
        )

    movimientos = []
    for fecha, (importe, descripcion) in zip(fechas, detalles, strict=True):
        movimiento = _movimiento(fecha, importe, descripcion)
        if movimiento is not None:
            movimientos.append(movimiento)
    return movimientos


def _sin_fechas(texto: str) -> str:
    return RE_FECHA.sub("", texto).strip(" -\t")


def _parsear_pdf(contenido: bytes, nombre_archivo: str) -> ResultadoParseo:
    lineas = _lineas_pdf(contenido)
    banco = _detectar_banco_en_texto(" ".join([nombre_archivo, *lineas[:60]]))
    en_linea = _movimientos_en_linea(lineas)
    try:
        por_columnas = _movimientos_por_columnas(lineas)
    except ErrorDeParseo:
        if not en_linea:
            raise
        por_columnas = []
    # Un PDF de columnas partidas puede tener alguna línea suelta con fecha e importe juntos:
    # se queda la lectura que reconstruye más movimientos.
    movimientos = max(en_linea, por_columnas, key=len)
    if not movimientos and not any(RE_FECHA.search(linea) for linea in lineas):
        raise ErrorDeParseo("No se encontraron movimientos con fecha e importe en el PDF.")
    filas = sum(1 for linea in lineas if RE_FECHA.search(linea))
    return ResultadoParseo(banco=banco, cantidad_filas=filas, movimientos=movimientos)


def _es_transferencia(descripcion: str, tiene_cuit: bool) -> bool:
    texto = _normalizar(descripcion)
    if any(p in texto for p in PALABRAS_TRANSFERENCIA):
        return True
    return tiene_cuit


def parsear_resumen(contenido: bytes, nombre_archivo: str) -> ResultadoParseo:
    """Extrae las transferencias recibidas (crédito) de un resumen bancario."""
    if nombre_archivo.lower().endswith(".pdf"):
        return _parsear_pdf(contenido, nombre_archivo)
    df = _leer_planilla(contenido, nombre_archivo)
    if df.empty:
        raise ErrorDeParseo("El archivo está vacío.")

    banco = _detectar_banco(df, nombre_archivo)
    fila = _fila_encabezado(df)
    encabezados = [_normalizar(v) for v in df.iloc[fila].tolist()]
    mapa = _mapear_columnas(encabezados)
    if not mapa["fecha"] or not (mapa["credito"] or mapa["importe"]):
        raise ErrorDeParseo(
            "No se pudieron identificar las columnas de fecha e importe/crédito del resumen."
        )

    cuerpo = df.iloc[fila + 1 :]
    movimientos: list[MovimientoParseado] = []
    filas_utiles = 0

    for _, fila_datos in cuerpo.iterrows():
        valores = fila_datos.tolist()
        fecha = next((f for f in (_a_fecha(valores[i]) for i in mapa["fecha"]) if f), None)
        if fecha is None:
            continue
        filas_utiles += 1

        debito = next((d for d in (_a_decimal(valores[i]) for i in mapa["debito"]) if d), None)
        credito = next((c for c in (_a_decimal(valores[i]) for i in mapa["credito"]) if c), None)
        importe = credito
        if importe is None:
            importe = next(
                (m for m in (_a_decimal(valores[i]) for i in mapa["importe"]) if m), None
            )
        if importe is None or importe <= 0:
            continue
        if credito is None and debito is not None and debito > 0:
            continue

        descripcion = " ".join(
            str(valores[i]).strip()
            for i in mapa["descripcion"]
            if valores[i] is not None and str(valores[i]).strip() and str(valores[i]) != "nan"
        )
        cuit = next(
            (c for c in (normalizar_cuit(valores[i]) for i in mapa["cuit"]) if c),
            None,
        ) or extraer_cuit(descripcion)

        if not _es_transferencia(descripcion, cuit is not None):
            continue

        movimientos.append(
            MovimientoParseado(
                fecha=fecha,
                importe=importe,
                descripcion=descripcion[:500],
                cuit=cuit,
            )
        )

    return ResultadoParseo(banco=banco, cantidad_filas=filas_utiles, movimientos=movimientos)
