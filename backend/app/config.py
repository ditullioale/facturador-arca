from functools import lru_cache
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

    # "mock" permite operar sin certificados (desarrollo / demo).
    # "homologacion" y "produccion" usan los web services reales de ARCA.
    arca_mode: Literal["mock", "homologacion", "produccion"] = "mock"
    arca_cert_path: str = ""
    arca_key_path: str = ""

    # Domicilio por defecto cuando el padrón de ARCA no informa uno.
    domicilio_default: str = "Arroyo Seco"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
