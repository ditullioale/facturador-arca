import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

export interface Factura {
  id: number
  transferencia_id: number | null
  origen: string
  emisor_cuit: string | null
  referencia_externa: string | null
  cuit_receptor: string
  razon_social: string | null
  domicilio: string | null
  concepto_descripcion: string
  tipo_comprobante: number
  punto_venta: number
  numero: number | null
  importe: string
  fecha_comprobante: string
  cae: string | null
  cae_vencimiento: string | null
  estado: string
  error: string | null
}

export interface Transferencia {
  id: number
  lote_id: number
  banco: string
  fecha: string
  cuit: string | null
  importe: string
  descripcion: string
  razon_social: string | null
  domicilio: string | null
  estado: string
  supera_minimo: boolean
  factura: Factura | null
}

export interface ResultadoImportacion {
  lote: { id: number; nombre_archivo: string; banco: string; cantidad_transferencias: number }
  nuevas: number
  duplicadas: number
  sin_cuit: number
  transferencias: Transferencia[]
}

export interface ResultadoTransferencia {
  transferencia_id: number
  /** emitida | error | revisar | sin_cuit | requiere_confirmacion */
  estado: string
  mensaje: string | null
  factura: Factura | null
}

export interface Configuracion {
  arca_mode: string
  arca_cuit: string
  punto_venta: number
  tipo_comprobante: number
  concepto_descripcion: string
  importe_minimo: string
  domicilio_default: string
}

export async function getConfig(): Promise<Configuracion> {
  const { data } = await api.get<Configuracion>('/config')
  return data
}

export async function getTransferencias(
  filtros: { estado?: string; q?: string; limit?: number; offset?: number } = {},
): Promise<Transferencia[]> {
  const { data } = await api.get<Transferencia[]>('/transferencias', { params: filtros })
  return data
}

export async function getFacturas(
  filtros: { estado?: string; q?: string; limit?: number; offset?: number } = {},
): Promise<Factura[]> {
  const { data } = await api.get<Factura[]>('/facturas', { params: filtros })
  return data
}

export async function subirResumen(archivo: File): Promise<ResultadoImportacion> {
  const form = new FormData()
  form.append('archivo', archivo)
  const { data } = await api.post<ResultadoImportacion>('/lotes', form)
  return data
}

export async function actualizarTransferencia(
  id: number,
  cambios: { cuit?: string; estado?: string },
): Promise<Transferencia> {
  const { data } = await api.patch<Transferencia>(`/transferencias/${id}`, cambios)
  return data
}

export async function facturar(
  ids: number[],
  confirmarBajoMinimo = false,
): Promise<ResultadoTransferencia[]> {
  const { data } = await api.post<ResultadoTransferencia[]>('/transferencias/facturar', {
    transferencia_ids: ids,
    confirmar_bajo_minimo: confirmarBajoMinimo,
  })
  return data
}

/** Pydantic antepone "Value error, " al mensaje de los validadores. */
function limpiar(mensaje: string): string {
  return mensaje.replace(/^Value error,\s*/, '')
}

/** Mensaje legible de un error de axios, sin `[object Object]`. */
export function mensajeDeError(error: unknown, porDefecto: string): string {
  const detalle = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detalle === 'string') return limpiar(detalle)
  if (Array.isArray(detalle)) {
    const textos = detalle
      .map((d) => (typeof d === 'string' ? d : (d as { msg?: string })?.msg))
      .filter(Boolean)
      .map((t) => limpiar(String(t)))
    if (textos.length > 0) return textos.join('. ')
  }
  return porDefecto
}

/** URL de la representación impresa (PDF con QR de AFIP) de una factura emitida. */
export function facturaPdfUrl(facturaId: number): string {
  return `/api/facturas/${facturaId}/pdf`
}
