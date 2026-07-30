# Facturador ARCA

Carga un resumen bancario (**Excel, CSV o PDF** de **Santander** o **Macro**), detecta las
**transferencias recibidas** (CUIT del emisor, importe y fecha) y emite las facturas
electrónicas en **ARCA** con el concepto **HONORARIOS PROFESIONALES**.

- Si el padrón de ARCA no informa domicilio del receptor, se autocompleta con `Arroyo Seco`
  (configurable en `DOMICILIO_DEFAULT`).
- Cada transferencia se factura una sola vez: se deduplica por huella (fecha + importe + CUIT +
  descripción) y hay una factura como máximo por transferencia.
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

Documentación interactiva: http://localhost:8000/docs

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

## Flujo

1. `POST /api/lotes` — subida del Excel/CSV/PDF; devuelve las transferencias nuevas, duplicadas y las
   que quedaron sin CUIT detectado.
2. `PATCH /api/transferencias/{id}` — completar el CUIT faltante o marcar la transferencia como
   ignorada (no se factura).
3. `POST /api/transferencias/facturar` — emite las facturas seleccionadas: consulta el padrón,
   completa domicilio y pide el CAE.
4. `GET /api/facturas` — comprobantes emitidos con CAE y vencimiento.

## Límites conocidos

- WSFEv1 autoriza importes, no renglones: el texto del concepto se guarda en la factura y se usa
  en la representación impresa (aún no incluida).
- Los formatos de exportación de los bancos cambian; el parser detecta encabezados por nombre de
  columna. Ante un resumen que no reconozca, agregar las palabras clave en
  `app/services/resumen_parser.py`.
- PDF: se soporta el listado normal (fecha, descripción e importe en la misma línea) y el PDF
  impreso desde una planilla ancha, donde cada bloque de páginas trae una columna y las filas se
  reconstruyen por orden. Los PDF escaneados (sin texto) no se pueden leer.
