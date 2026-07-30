import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import {
  actualizarTransferencia,
  facturar,
  getTransferencias,
  type Transferencia,
} from '../api/client'

const moneda = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' })

function estadoChip(t: Transferencia) {
  if (t.estado === 'facturada' && t.factura?.cae) {
    return <Chip size="small" color="success" label={`CAE ${t.factura.cae}`} />
  }
  if (t.factura?.estado === 'error') {
    return (
      <Tooltip title={t.factura.error ?? ''}>
        <Chip size="small" color="error" label="Error ARCA" />
      </Tooltip>
    )
  }
  if (t.estado === 'ignorada') return <Chip size="small" label="Ignorada" />
  return <Chip size="small" color="warning" label="Pendiente" />
}

export default function TablaTransferencias() {
  const queryClient = useQueryClient()
  const [seleccion, setSeleccion] = useState<number[]>([])
  const { data: transferencias = [], isLoading } = useQuery({
    queryKey: ['transferencias'],
    queryFn: getTransferencias,
  })

  const invalidar = () => queryClient.invalidateQueries({ queryKey: ['transferencias'] })
  const actualizar = useMutation({
    mutationFn: ({ id, cuit }: { id: number; cuit: string }) =>
      actualizarTransferencia(id, { cuit }),
    onSuccess: invalidar,
  })
  const errorActualizar =
    actualizar.error && typeof actualizar.error === 'object' && 'response' in actualizar.error
      ? ((actualizar.error as { response?: { data?: { detail?: unknown } } }).response?.data
          ?.detail ?? null)
      : null

  const emitir = useMutation({
    mutationFn: facturar,
    onSuccess: () => {
      setSeleccion([])
      invalidar()
    },
  })

  const facturables = transferencias.filter(
    (t) => t.estado === 'pendiente' && t.cuit && t.factura?.estado !== 'emitida',
  )

  if (isLoading) return <CircularProgress />

  return (
    <Card>
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="h6">2. Revisar y facturar</Typography>
          <Button
            variant="contained"
            startIcon={<ReceiptLongIcon />}
            disabled={seleccion.length === 0 || emitir.isPending}
            onClick={() => emitir.mutate(seleccion)}
          >
            {emitir.isPending ? 'Emitiendo…' : `Facturar (${seleccion.length})`}
          </Button>
        </Stack>
        {actualizar.isError && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => actualizar.reset()}>
            No se pudo guardar el CUIT
            {typeof errorActualizar === 'string' ? `: ${errorActualizar}` : ' (CUIT inválido)'}
          </Alert>
        )}
        {emitir.isError && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => emitir.reset()}>
            No se pudieron emitir las facturas seleccionadas.
          </Alert>
        )}
        {transferencias.length === 0 ? (
          <Alert severity="info">Todavía no importaste ningún resumen bancario.</Alert>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={seleccion.length > 0 && seleccion.length === facturables.length}
                    indeterminate={seleccion.length > 0 && seleccion.length < facturables.length}
                    onChange={(e) =>
                      setSeleccion(e.target.checked ? facturables.map((t) => t.id) : [])
                    }
                  />
                </TableCell>
                <TableCell>Fecha</TableCell>
                <TableCell>CUIT emisor</TableCell>
                <TableCell>Razón social</TableCell>
                <TableCell>Domicilio</TableCell>
                <TableCell align="right">Importe</TableCell>
                <TableCell>Descripción</TableCell>
                <TableCell>Estado</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {transferencias.map((t) => (
                <TableRow key={t.id} hover>
                  <TableCell padding="checkbox">
                    <Checkbox
                      disabled={!facturables.some((f) => f.id === t.id)}
                      checked={seleccion.includes(t.id)}
                      onChange={(e) =>
                        setSeleccion((prev) =>
                          e.target.checked ? [...prev, t.id] : prev.filter((id) => id !== t.id),
                        )
                      }
                    />
                  </TableCell>
                  <TableCell>{t.fecha}</TableCell>
                  <TableCell>
                    {t.estado === 'facturada' ? (
                      t.cuit
                    ) : (
                      <TextField
                        size="small"
                        variant="standard"
                        placeholder="CUIT"
                        defaultValue={t.cuit ?? ''}
                        error={!t.cuit}
                        onBlur={(e) => {
                          const valor = e.target.value.replace(/\D/g, '')
                          if (valor.length === 11 && valor !== t.cuit) {
                            actualizar.mutate({ id: t.id, cuit: valor })
                          }
                        }}
                      />
                    )}
                  </TableCell>
                  <TableCell>{t.razon_social ?? '—'}</TableCell>
                  <TableCell>{t.domicilio ?? '—'}</TableCell>
                  <TableCell align="right">{moneda.format(Number(t.importe))}</TableCell>
                  <TableCell sx={{ maxWidth: 280 }}>
                    <Typography variant="caption" noWrap display="block" title={t.descripcion}>
                      {t.descripcion}
                    </Typography>
                  </TableCell>
                  <TableCell>{estadoChip(t)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
