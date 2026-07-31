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

export async function getTransferencias(): Promise<Transferencia[]> {
  const { data } = await api.get<Transferencia[]>('/transferencias')
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
): Promise<Factura[]> {
  const { data } = await api.post<Factura[]>('/transferencias/facturar', {
    transferencia_ids: ids,
    confirmar_bajo_minimo: confirmarBajoMinimo,
  })
  return data
}

/** URL de la representación impresa (PDF con QR de AFIP) de una factura emitida. */
export function facturaPdfUrl(facturaId: number): string {
  return `/api/facturas/${facturaId}/pdf`
}
