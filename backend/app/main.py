from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import emisores, facturas, integracion, lotes, transferencias
from app.config import get_settings

app = FastAPI(title="Facturador ARCA", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lotes.router)
app.include_router(transferencias.router)
app.include_router(facturas.router)
app.include_router(integracion.router)
app.include_router(emisores.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
