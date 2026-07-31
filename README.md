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
   completa domicilio y pide el CAE. Las transferencias por debajo del mínimo se omiten salvo que
   se envíe `confirmar_bajo_minimo=true` (o `?confirmar=true` en el endpoint individual).
4. `GET /api/facturas` — comprobantes emitidos con CAE y vencimiento.
5. `GET /api/facturas/{id}/pdf` — representación impresa del comprobante con el QR de AFIP.

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
- Emisor único por instancia: cada inmobiliaria factura con su propio CUIT y certificado, por lo
  que la integración multiempresa usa una instancia (o credenciales) por emisor.
- Los formatos de exportación de los bancos cambian; el parser detecta encabezados por nombre de
  columna. Ante un resumen que no reconozca, agregar las palabras clave en
  `app/services/resumen_parser.py`.
- PDF: se soporta el listado normal (fecha, descripción e importe en la misma línea) y el PDF
  impreso desde una planilla ancha, donde cada bloque de páginas trae una columna y las filas se
  reconstruyen por orden. Los PDF escaneados (sin texto) no se pueden leer.
