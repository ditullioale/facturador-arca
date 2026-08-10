import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import emisores, facturas, integracion, lotes, transferencias
from app.config import get_settings


def _crear_app() -> FastAPI:
    ajustes = get_settings()
    problemas = ajustes.errores_de_configuracion()
    if problemas:
        # Operar contra ARCA con la frontera abierta o con los certificados cifrados
        # con una clave pública no es un aviso: es motivo para no levantar.
        detalle = "\n - ".join(problemas)
        raise RuntimeError(
            f"Configuración insegura para ARCA_MODE={ajustes.arca_mode}:\n - {detalle}"
        )
    # Con las docs apagadas, FastAPI tampoco publica /openapi.json.
    docs = "/docs" if ajustes.facturador_docs else None
    return FastAPI(
        title="Facturador ARCA",
        version="0.1.0",
        docs_url=docs,
        redoc_url="/redoc" if ajustes.facturador_docs else None,
        openapi_url="/openapi.json" if ajustes.facturador_docs else None,
    )


app = _crear_app()

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlacion_y_cabeceras(request: Request, call_next):
    """Id de correlación por request (el mismo que usa el gestor) y cabeceras de
    seguridad. El id viaja en X-Request-Id: si el gestor ya mandó uno, se respeta, así
    un problema se sigue de punta a punta entre los dos servicios."""
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    respuesta = await call_next(request)
    respuesta.headers["X-Request-Id"] = request_id
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    return respuesta


app.include_router(lotes.router)
app.include_router(transferencias.router)
app.include_router(facturas.router)
app.include_router(integracion.router)
app.include_router(emisores.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Salud pública: sólo responde que el proceso está vivo. El detalle (modo, emisores,
    vencimiento de certificados) va en /api/emisores/diagnostico, que pide token de admin:
    es información útil para operar y también para quien quiera sondear el servicio."""
    return {"status": "ok"}
