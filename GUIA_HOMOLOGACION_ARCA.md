# Guía — Pasar de `mock` a un CAE real en homologación de ARCA

> Pilar 1 del checklist "listo para vender". Hoy el Facturador corre en `ARCA_MODE=mock`:
> los comprobantes y los CAE son **simulados, sin validez fiscal**. Antes de facturarle a
> un cliente real, hay que emitir al menos un comprobante en el entorno de **homologación**
> (el "campo de pruebas" oficial de ARCA) para confirmar que todo el circuito produce un
> CAE válido.

## Panorama

```
mock (hoy)  →  homologacion (probar acá)  →  produccion (recién al final)
```

- **mock**: sin certificados, todo simulado. Sirve para desarrollo y demo.
- **homologacion**: web services REALES de ARCA, pero de prueba. El CAE es real pero no
  factura de verdad. Es el paso obligatorio antes de producción.
- **produccion**: facturación fiscal real.

## Paso 1 — Certificado de ARCA (lo hacés en la web de ARCA, con tu Clave Fiscal)

Esto es trámite en ARCA, no en el código:

1. Generá una clave privada y un pedido de certificado (CSR). Ejemplo con OpenSSL:
   ```bash
   openssl genrsa -out finart.key 2048
   openssl req -new -key finart.key -subj "/C=AR/O=TU_RAZON_SOCIAL/CN=finart/serialNumber=CUIT TU_CUIT" -out finart.csr
   ```
2. Entrá a ARCA con Clave Fiscal → **Administración de Certificados Digitales** →
   ambiente de **homologación** (WSASS) → subí el `.csr` y descargá el **certificado** (`.crt`/`.pem`).
3. **Autorizá los web services** para ese certificado/CUIT:
   - `wsfe` (facturación electrónica) — imprescindible.
   - `ws_sr_constancia_inscripcion` (padrón) — opcional (en homologación suele estar caído).

Al final tenés dos archivos: la **clave privada** (`finart.key`) y el **certificado** (`.pem`).

## Paso 2 — Cargar el certificado en Railway (servicio `facturador-arca`)

Como Railway no tiene disco persistente, el certificado va en **base64** por variable de
entorno. Convertí los dos archivos:

```powershell
# En PowerShell:
[Convert]::ToBase64String([IO.File]::ReadAllBytes("finart.pem"))   # -> ARCA_CERT_B64
[Convert]::ToBase64String([IO.File]::ReadAllBytes("finart.key"))   # -> ARCA_KEY_B64
```

En Railway → servicio **`facturador-arca`** → **Variables**, cargá:

| Variable | Valor |
|---|---|
| `ARCA_MODE` | `homologacion` |
| `ARCA_CUIT` | tu CUIT (solo números) |
| `ARCA_PUNTO_VENTA` | tu punto de venta de homologación (normalmente `1`) |
| `ARCA_TIPO_COMPROBANTE` | `11` Factura C · `6` Factura B · `1` Factura A |
| `ARCA_CERT_B64` | el base64 del certificado |
| `ARCA_KEY_B64` | el base64 de la clave privada |
| `ARCA_CONSULTAR_PADRON` | `false` (en homologación el padrón suele estar caído) |
| `FACTURADOR_SECRET` | una cadena secreta larga (cifra los certificados por emisor) |

Guardá y dejá que redeploye.

## Paso 3 — Emitir un comprobante de prueba

1. Desde Finart, generá una liquidación con comisión a un propietario **con CUIT válido**
   (podés usar un CUIT de prueba de ARCA).
2. Facturá la comisión (botón "Sí, facturar" / automático).
3. Verificá que la liquidación quede **emitida con un CAE** y que el PDF muestre el CAE y el QR.

Si el CAE aparece y el PDF valida, **el circuito real funciona**. Ese es el hito del Pilar 1.

## Paso 4 — Recién ahí, producción

Cuando homologación funcione, repetí el Paso 2 con el certificado de **producción** y
`ARCA_MODE=produccion`. No pases a producción sin haber emitido bien en homologación.

## Notas

- Multiempresa: cada inmobiliaria puede tener su propio certificado (se sube por
  `POST /api/emisores`). Para vos, como primer emisor, alcanza con el emisor por defecto
  (las variables `ARCA_*` de arriba).
- El resto del circuito (idempotencia, reintentos, reconciliación) ya está probado y no
  cambia entre mock, homologación y producción.
- Si algo falla al emitir, Finart lo deja como `error` (4xx, dato inválido) o
  `requiere_reconciliacion` (timeout/5xx) y lo vas a ver en la bandeja de pendientes.
