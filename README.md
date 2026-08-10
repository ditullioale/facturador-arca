# Facturador ARCA

Carga un resumen bancario (**Excel, CSV o PDF** de **Santander** o **Macro**), detecta las
**transferencias recibidas** (CUIT del emisor, importe y fecha) y emite las facturas
electrónicas en **ARCA** con el concepto **HONORARIOS PROFESIONALES**.

- Si el padrón de ARCA no informa domicilio del receptor, se autocompleta con `Arroyo Seco`
  (configurable en `DOMICILIO_DEFAULT`).
- Cada transferencia se factura una sola vez: se deduplica por huella (fecha + importe + CUIT +
  descripción) y hay una factura como máximo por transferencia.
- Solo se emite la factura cuando el importe **supera** el mínimo configurado
  (`ARCA_IMPORTE_MINIMO`, $50.000 por defecto). Por debajo, la app **pregunta si se factura o
  no** (confirmación explícita).
- Cada comprobante emitido tiene su **representación impresa en PDF con el código QR de AFIP**
  (RG 4291): `GET /api/facturas/{id}/pdf`.
- `ARCA_MODE=mock` permite usar la app completa sin certificados; los comprobantes son simulados
  y **no tienen validez fiscal**.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL, pandas, openpyxl, pdfplumber, zeep (SOAP de
  ARCA).
- Frontend: React, Vite, Material UI, React Query, Axios.

## Puesta en marcha

### Backend

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # completar CUIT, punto de venta y credenciales
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

Documentación interactiva: http://localhost:8000/docs, con `FACTURADOR_DOCS=1` (apagada por
defecto: en producción el catálogo de endpoints sólo le sirve a quien quiera sondear el servicio).

### Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxy /api -> :8000)
```

### Tests

```bash
cd backend && .venv/bin/python -m pytest && .venv/bin/ruff check .
cd frontend && npm run typecheck && npm run build
```

## Credenciales de ARCA

1. Generar el certificado en ARCA (Administración de Certificados Digitales) y habilitar los
   web services `wsfe` (facturación) y `ws_sr_constancia_inscripcion` (padrón) para el CUIT.
2. Guardar el certificado y la clave privada fuera del repo y apuntar `ARCA_CERT_PATH` y
   `ARCA_KEY_PATH`.
3. Probar primero con `ARCA_MODE=homologacion` y recién después pasar a `produccion`.

`ARCA_TIPO_COMPROBANTE` define el comprobante a emitir: `11` Factura C (monotributo),
`6` Factura B, `1` Factura A.

## Seguridad y puesta en producción

El facturador es un servicio **server-to-server**: emite comprobantes fiscales con el
certificado de una inmobiliaria, así que nadie debería poder llamarlo sin credencial.

| Variable | Para qué |
|---|---|
| `FACTURADOR_SECRET` | Clave maestra con la que se cifran los certificados de cada emisor. |
| `FACTURADOR_INTEGRACION_TOKEN` | Secreto compartido con el gestor (header `X-Integracion-Token`) para los pedidos que usan el emisor por defecto. Mismo valor en los dos servicios. |
| `FACTURADOR_ADMIN_TOKEN` | Alta de emisores y diagnóstico (header `X-Admin-Token`). |
| `FACTURADOR_DOCS` | `1` para publicar `/docs`, `/redoc` y `/openapi.json`. |
| `FACTURADOR_MAX_UPLOAD_MB` | Tope del resumen bancario que se acepta subir (10 por defecto). |

Con `ARCA_MODE=homologacion` o `produccion` la configuración se valida **al arrancar** y el
proceso no levanta si falta `FACTURADOR_SECRET` o `FACTURADOR_INTEGRACION_TOKEN`, o si
`CORS_ORIGINS` es `*`: operar contra ARCA con la frontera abierta o con los certificados cifrados
con la clave de desarrollo (que está en el código) no es un aviso, es un motivo para no arrancar.
En `mock` no se exige nada, así que el desarrollo y las demos no cambian.

`GET /api/emisores/diagnostico` (con `X-Admin-Token`) responde las dos preguntas que hoy sólo se
contestan cuando algo ya falló: **cuándo vence cada certificado de ARCA** —duran un año y al
vencer cortan la facturación de golpe— y **cuántos comprobantes quedaron sin reconciliar**.
Conviene mirarlo desde el monitor de uptime.

## Flujo

1. `POST /api/lotes` — subida del Excel/CSV/PDF; devuelve las transferencias nuevas, duplicadas y las
   que quedaron sin CUIT detectado.
2. `PATCH /api/transferencias/{id}` — completar el CUIT faltante o marcar la transferencia como
   ignorada (no se factura).
3. `POST /api/transferencias/facturar` — emite las facturas seleccionadas: consulta el padrón,
   completa domicilio y pide el CAE. Las transferencias por debajo del mínimo se omiten salvo que
   se envíe `confirmar_bajo_minimo=true` (o `?confirmar=true` en el endpoint individual).
4. `GET /api/facturas` — comprobantes emitidos con CAE y vencimiento.
5. `GET /api/facturas/{id}/pdf` — representación impresa del comprobante con el QR de AFIP.
6. `POST /api/facturas/reconciliar` — retoma las facturas que quedaron en `revisar` porque ARCA
   no contestó a tiempo: el comprobante puede estar autorizado allá y no registrado acá. Consulta
   con `FECompConsultar` antes de reemitir, así que llamarlo de más nunca duplica. Pensado para un
   cron (el gestor ya lo llama en su reconciliación).

## Integración con el gestor de alquileres (finart-alquileres)

Cuando el gestor genera una liquidación al propietario, emite la factura de honorarios
(comisión de la inmobiliaria) al propietario llamando a:

`POST /api/integracion/liquidacion`

```jsonc
{
  "receptor_cuit": "27123456780",   // CUIT del propietario
  "importe": "120000.00",            // comisión de la liquidación
  "fecha": "2026-07-31",
  "referencia_externa": "gestor:1:LIQ-0001",  // idempotencia
  "emisor_cuit": "20111111112",      // CUIT de la inmobiliaria (opcional)
  "concepto_descripcion": "HONORARIOS PROFESIONALES",
  "razon_social": "PEREZ SA",
  "domicilio": "Calle Falsa 123",
  "confirmar_bajo_minimo": false
}
```

Respuesta: `{ "estado": "emitida" | "error" | "requiere_confirmacion", "mensaje": ..., "factura": ... }`.
Es **idempotente** por `referencia_externa` (no factura dos veces la misma liquidación) y respeta
el mínimo de $50.000: si la comisión no lo supera, devuelve `requiere_confirmacion` para que el
gestor pregunte al usuario.

## Límites conocidos

- WSFEv1 autoriza importes, no renglones: el texto del concepto se guarda en la factura y se usa
  en la representación impresa en PDF (con QR de AFIP, RG 4291).
- No hay notas de crédito: un comprobante emitido por error se corrige en el portal de ARCA.
- Los formatos de exportación de los bancos cambian; el parser detecta encabezados por nombre de
  columna. Ante un resumen que no reconozca, agregar las palabras clave en
  `app/services/resumen_parser.py`.
- PDF: se soporta el listado normal (fecha, descripción e importe en la misma línea) y el PDF
  impreso desde una planilla ancha, donde cada bloque de páginas trae una columna y las filas se
  reconstruyen por orden. Los PDF escaneados (sin texto) no se pueden leer.
