import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Alert from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogContentText from '@mui/material/DialogContentText'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import LinearProgress from '@mui/material/LinearProgress'
import Link from '@mui/material/Link'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import BlockIcon from '@mui/icons-material/BlockOutlined'
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import SearchIcon from '@mui/icons-material/Search'
import UndoIcon from '@mui/icons-material/UndoOutlined'
import {
  actualizarTransferencia,
  facturaPdfUrl,
  facturar,
  getTransferencias,
  mensajeDeError,
  type ResultadoTransferencia,
  type Transferencia,
} from '../api/client'
import { useDebounce } from '../hooks/useDebounce'

const moneda = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' })
const POR_PAGINA = 50

type Filtro = 'pendiente' | 'facturada' | 'ignorada' | 'todas'

const MOTIVOS: Record<string, string> = {
  sin_cuit: 'Falta el CUIT del emisor',
  requiere_confirmacion: 'No supera el importe mínimo',
  revisar: 'Sin respuesta de ARCA: queda para reconciliar',
  error: 'ARCA rechazó el comprobante',
}

function estadoChip(t: Transferencia) {
  if (t.estado === 'facturada' && t.factura?.cae) {
    return (
      <Stack direction="row" spacing={0.75} alignItems="center">
        <Chip size="small" color="success" variant="outlined" label={`CAE ${t.factura.cae}`} />
        <Tooltip title="Ver PDF con QR de AFIP">
          <Link
            href={facturaPdfUrl(t.factura.id)}
            target="_blank"
            rel="noopener"
            sx={{ display: 'inline-flex', alignItems: 'center' }}
          >
            <PictureAsPdfIcon fontSize="small" />
          </Link>
        </Tooltip>
      </Stack>
    )
  }
  if (t.factura?.estado === 'error') {
    return (
      <Tooltip title={t.factura.error ?? ''}>
        <Chip size="small" color="error" variant="outlined" label="Error ARCA" />
      </Tooltip>
    )
  }
  if (t.factura?.estado === 'revisar') {
    return (
      <Tooltip title="Se pidió el CAE y ARCA no contestó. Se reconcilia automáticamente.">
        <Chip size="small" color="info" variant="outlined" label="En revisión" />
      </Tooltip>
    )
  }
  if (t.estado === 'ignorada') return <Chip size="small" variant="outlined" label="Ignorada" />
  return <Chip size="small" color="warning" variant="outlined" label="Pendiente" />
}

interface Props {
  importeMinimo?: string
  concepto?: string
}

export default function TablaTransferencias({ importeMinimo, concepto }: Props) {
  const queryClient = useQueryClient()
  const [seleccion, setSeleccion] = useState<number[]>([])
  const [filtro, setFiltro] = useState<Filtro>('pendiente')
  const [busqueda, setBusqueda] = useState('')
  const [pagina, setPagina] = useState(0)
  const [aConfirmar, setAConfirmar] = useState<Transferencia[] | null>(null)
  const [resultados, setResultados] = useState<ResultadoTransferencia[] | null>(null)

  const busquedaDiferida = useDebounce(busqueda.trim())

  useEffect(() => {
    setPagina(0)
    setSeleccion([])
  }, [busquedaDiferida])

  const { data: visibles = [], isLoading } = useQuery({
    queryKey: ['transferencias', filtro, pagina, busquedaDiferida],
    queryFn: () =>
      getTransferencias({
        estado: filtro === 'todas' ? undefined : filtro,
        q: busquedaDiferida || undefined,
        limit: POR_PAGINA,
        offset: pagina * POR_PAGINA,
      }),
  })

  const invalidar = () => queryClient.invalidateQueries({ queryKey: ['transferencias'] })

  const actualizar = useMutation({
    mutationFn: ({ id, cambios }: { id: number; cambios: { cuit?: string; estado?: string } }) =>
      actualizarTransferencia(id, cambios),
    onSuccess: invalidar,
  })

  const emitir = useMutation({
    mutationFn: ({ ids, confirmar }: { ids: number[]; confirmar: boolean }) =>
      facturar(ids, confirmar),
    onSuccess: (datos) => {
      setSeleccion([])
      setResultados(datos)
      invalidar()
    },
  })

  const facturables = visibles.filter(
    (t) => t.estado === 'pendiente' && t.cuit && t.factura?.estado !== 'emitida',
  )

  const cambiarFiltro = (valor: Filtro) => {
    setFiltro(valor)
    setPagina(0)
    setSeleccion([])
  }

  const emitirSeleccion = () => {
    const bajoMinimo = visibles.filter((t) => seleccion.includes(t.id) && !t.supera_minimo)
    if (bajoMinimo.length > 0) {
      setAConfirmar(bajoMinimo)
      return
    }
    emitir.mutate({ ids: seleccion, confirmar: false })
  }

  const emitidas = resultados?.filter((r) => r.estado === 'emitida') ?? []
  const omitidas = resultados?.filter((r) => r.estado !== 'emitida') ?? []
  const totalSeleccionado = visibles
    .filter((t) => seleccion.includes(t.id))
    .reduce((suma, t) => suma + Number(t.importe), 0)

  return (
    <Card>
      <CardContent sx={{ pb: 0 }}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          justifyContent="space-between"
          alignItems={{ xs: 'stretch', md: 'center' }}
          spacing={1.5}
        >
          <Box>
            <Stack direction="row" spacing={1} alignItems="baseline">
              <Typography variant="h6">Revisar y facturar</Typography>
              <Typography variant="caption" color="text.secondary">
                paso 2
              </Typography>
            </Stack>
            {concepto && (
              <Typography variant="caption" color="text.secondary">
                Concepto: {concepto}
                {importeMinimo && ` · mínimo para facturar ${moneda.format(Number(importeMinimo))}`}
              </Typography>
            )}
          </Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <TextField
              size="small"
              placeholder="Buscar CUIT, razón social o importe"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              sx={{ minWidth: { xs: 0, sm: 280 } }}
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon fontSize="small" />
                    </InputAdornment>
                  ),
                },
              }}
            />
            <Button
              variant="contained"
              startIcon={<ReceiptLongIcon />}
              disabled={seleccion.length === 0 || emitir.isPending}
              onClick={emitirSeleccion}
            >
              {emitir.isPending ? 'Emitiendo…' : `Facturar (${seleccion.length})`}
            </Button>
          </Stack>
        </Stack>

        <Tabs
          value={filtro}
          onChange={(_e, v: Filtro) => cambiarFiltro(v)}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{ mt: 1, borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab value="pendiente" label="Pendientes" />
          <Tab value="facturada" label="Facturadas" />
          <Tab value="ignorada" label="Ignoradas" />
          <Tab value="todas" label="Todas" />
        </Tabs>
      </CardContent>

      <CardContent sx={{ pt: 2 }}>
        {seleccion.length > 0 && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {seleccion.length} seleccionada(s) por {moneda.format(totalSeleccionado)}.
          </Alert>
        )}
        {actualizar.isError && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => actualizar.reset()}>
            {mensajeDeError(actualizar.error, 'No se pudo guardar el cambio (CUIT inválido)')}
          </Alert>
        )}
        {emitir.isError && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => emitir.reset()}>
            {mensajeDeError(emitir.error, 'No se pudieron emitir las facturas seleccionadas.')}
          </Alert>
        )}
        {resultados && (
          <Alert
            severity={omitidas.length === 0 ? 'success' : 'warning'}
            sx={{ mb: 2 }}
            onClose={() => setResultados(null)}
          >
            <AlertTitle>
              {emitidas.length} emitida(s), {omitidas.length} sin emitir
            </AlertTitle>
            {omitidas.map((r) => (
              <Typography key={r.transferencia_id} variant="body2">
                #{r.transferencia_id}: {MOTIVOS[r.estado] ?? r.estado}
                {r.mensaje ? ` — ${r.mensaje}` : ''}
              </Typography>
            ))}
          </Alert>
        )}
        {emitir.isPending && <LinearProgress sx={{ mb: 2, borderRadius: 1 }} />}

        {isLoading ? (
          <Stack spacing={1}>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} variant="rounded" height={38} />
            ))}
          </Stack>
        ) : visibles.length === 0 ? (
          <Alert severity="info">
            {busqueda
              ? 'Ninguna transferencia coincide con la búsqueda.'
              : filtro === 'pendiente'
                ? 'No hay transferencias pendientes. Subí un resumen bancario para empezar.'
                : 'No hay transferencias en esta solapa.'}
          </Alert>
        ) : (
          <TableContainer>
            <Table size="small" sx={{ minWidth: 900 }}>
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Checkbox
                      disabled={facturables.length === 0}
                      checked={facturables.length > 0 && seleccion.length === facturables.length}
                      indeterminate={seleccion.length > 0 && seleccion.length < facturables.length}
                      onChange={(e) =>
                        setSeleccion(e.target.checked ? facturables.map((t) => t.id) : [])
                      }
                    />
                  </TableCell>
                  <TableCell>Fecha</TableCell>
                  <TableCell>CUIT emisor</TableCell>
                  <TableCell>Razón social</TableCell>
                  <TableCell align="right">Importe</TableCell>
                  <TableCell>Descripción</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell align="right">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {visibles.map((t) => (
                  <TableRow key={t.id} hover selected={seleccion.includes(t.id)}>
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
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{t.fecha}</TableCell>
                    <TableCell>
                      {t.estado === 'facturada' ? (
                        t.cuit
                      ) : (
                        <TextField
                          size="small"
                          variant="standard"
                          placeholder="Completar CUIT"
                          defaultValue={t.cuit ?? ''}
                          error={!t.cuit}
                          helperText={!t.cuit ? 'Sin CUIT no se puede facturar' : undefined}
                          onBlur={(e) => {
                            const valor = e.target.value.replace(/\D/g, '')
                            if (valor.length === 11 && valor !== t.cuit) {
                              actualizar.mutate({ id: t.id, cambios: { cuit: valor } })
                            }
                          }}
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{t.razon_social ?? '—'}</Typography>
                      {t.domicilio && (
                        <Typography variant="caption" color="text.secondary">
                          {t.domicilio}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}
                    >
                      {moneda.format(Number(t.importe))}
                      {!t.supera_minimo && (
                        <Typography variant="caption" color="warning.main" display="block">
                          bajo el mínimo
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 260 }}>
                      <Typography variant="caption" noWrap display="block" title={t.descripcion}>
                        {t.descripcion}
                      </Typography>
                    </TableCell>
                    <TableCell>{estadoChip(t)}</TableCell>
                    <TableCell align="right">
                      {t.estado === 'pendiente' && (
                        <Tooltip title="Ignorar: no es un honorario a facturar">
                          <IconButton
                            size="small"
                            onClick={() =>
                              actualizar.mutate({ id: t.id, cambios: { estado: 'ignorada' } })
                            }
                          >
                            <BlockIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                      {t.estado === 'ignorada' && (
                        <Tooltip title="Volver a pendiente">
                          <IconButton
                            size="small"
                            onClick={() =>
                              actualizar.mutate({ id: t.id, cambios: { estado: 'pendiente' } })
                            }
                          >
                            <UndoIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">
            {visibles.length} en pantalla
          </Typography>
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              disabled={pagina === 0}
              onClick={() => {
                setPagina((p) => Math.max(0, p - 1))
                setSeleccion([])
              }}
            >
              Anteriores
            </Button>
            <Button
              size="small"
              disabled={visibles.length < POR_PAGINA}
              onClick={() => {
                setPagina((p) => p + 1)
                setSeleccion([])
              }}
            >
              Siguientes
            </Button>
          </Stack>
        </Stack>
      </CardContent>

      <Dialog open={aConfirmar !== null} onClose={() => setAConfirmar(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Hay transferencias por debajo del mínimo</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {importeMinimo
              ? `El mínimo configurado para facturar es ${moneda.format(Number(importeMinimo))}. `
              : ''}
            Estas no lo superan. Si confirmás, se emiten igual con validez fiscal.
          </DialogContentText>
          <Table size="small">
            <TableBody>
              {(aConfirmar ?? []).map((t) => (
                <TableRow key={t.id}>
                  <TableCell>{t.fecha}</TableCell>
                  <TableCell>{t.razon_social ?? t.cuit ?? '—'}</TableCell>
                  <TableCell align="right">{moneda.format(Number(t.importe))}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAConfirmar(null)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={() => {
              setAConfirmar(null)
              emitir.mutate({ ids: seleccion, confirmar: true })
            }}
          >
            Facturar igual
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  )
}
