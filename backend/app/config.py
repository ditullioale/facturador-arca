import base64
import binascii
import contextlib
import tempfile
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/facturador"

    cors_origins: str = "http://localhost:5173"

    # Datos del emisor (tu monotributo / responsable inscripto)
    arca_cuit: str = ""
    arca_punto_venta: int = 1
    # 11 = Factura C, 6 = Factura B, 1 = Factura A
    arca_tipo_comprobante: int = 11
    arca_concepto_descripcion: str = "HONORARIOS PROFESIONALES"
    # Condición frente al IVA del receptor (RG 5616), obligatorio en WSFE.
    # 5 = Consumidor Final, 1 = Responsable Inscripto, 6 = Monotributo, 4 = Exento.
    arca_cond_iva_receptor: int = 5

    # Solo se emite la factura cuando el importe SUPERA este mínimo.
    # Por debajo, la app pregunta si se factura o no (confirmación explícita).
    arca_importe_minimo: Decimal = Decimal("50000")

    # "mock" permite operar sin certificados (desarrollo / demo).
    # "homologacion" y "produccion" usan los web services reales de ARCA.
    arca_mode: Literal["mock", "homologacion", "produccion"] = "mock"
    arca_cert_path: str = ""
    arca_key_path: str = ""
    # Alternativa para la nube (Railway, sin filesystem persistente): certificado y
    # clave en base64. Si están seteadas, se materializan a archivos temporales al
    # usarlas y tienen prioridad sobre ARCA_CERT_PATH / ARCA_KEY_PATH.
    arca_cert_b64: str = ""
    arca_key_b64: str = ""
    # Carpeta donde se cachea el Ticket de Acceso (TA) entre reinicios.
    # Vacío = carpeta temporal del sistema.
    arca_ta_dir: str = ""

    # Domicilio por defecto cuando el padrón de ARCA no informa uno.
    domicilio_default: str = "Arroyo Seco"

    @property
    def cert_path_efectivo(self) -> str:
        return _materializar_pem(self.arca_cert_b64, self.arca_cert_path, "arca_cert.pem")

    @property
    def key_path_efectivo(self) -> str:
        return _materializar_pem(self.arca_key_b64, self.arca_key_path, "arca_key.key")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def _materializar_pem(contenido_b64: str, ruta_archivo: str, nombre: str) -> str:
    """Devuelve la ruta al PEM a usar.

    Si ``contenido_b64`` tiene contenido, lo decodifica y lo escribe a un archivo
    temporal (para entornos sin filesystem persistente como Railway) y devuelve esa
    ruta. Si no, devuelve ``ruta_archivo`` (uso local con archivos en disco).
    """
    if not contenido_b64.strip():
        return ruta_archivo
    # Se quitan espacios y saltos de línea (al copiar/pegar suelen colarse) antes de decodificar.
    limpio = "".join(contenido_b64.split())
    try:
        datos = base64.b64decode(limpio, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{nombre}: el contenido base64 es inválido: {exc}") from exc
    destino = Path(tempfile.gettempdir()) / nombre
    destino.write_bytes(datos)
    with contextlib.suppress(OSError):
        destino.chmod(0o600)
    return str(destino)


@lru_cache
def get_settings() -> Settings:
    return Settings()
