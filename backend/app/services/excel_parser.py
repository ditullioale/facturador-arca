"""Parseo de resúmenes bancarios en Excel/CSV (Santander, Macro y formatos similares).

Los bancos exportan planillas con encabezados en filas variables y nombres de columna
distintos, por lo que el parser detecta el encabezado y mapea las columnas por nombre
en lugar de asumir posiciones fijas.
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

from app.services.cuit import extraer_cuit, normalizar_cuit

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

BANCOS = {"santander": "santander", "macro": "macro"}


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


def _detectar_banco(df: pd.DataFrame, nombre_archivo: str) -> str:
    texto = _normalizar(nombre_archivo) + " " + " ".join(
        _normalizar(v) for v in df.head(15).to_numpy().flatten()
    )
    for clave, banco in BANCOS.items():
        if clave in texto:
            return banco
    return "desconocido"


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


def _es_transferencia(descripcion: str, tiene_cuit: bool) -> bool:
    texto = _normalizar(descripcion)
    if any(p in texto for p in PALABRAS_TRANSFERENCIA):
        return True
    return tiene_cuit


def parsear_resumen(contenido: bytes, nombre_archivo: str) -> ResultadoParseo:
    """Extrae las transferencias recibidas (crédito) de un resumen bancario."""
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
