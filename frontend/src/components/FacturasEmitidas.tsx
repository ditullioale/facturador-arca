import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import InputAdornment from '@mui/material/InputAdornment'
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
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import SearchIcon from '@mui/icons-material/Search'
import { facturaPdfUrl, getFacturas, type Factura } from '../api/client'
import { useDebounce } from '../hooks/useDebounce'

const moneda = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' })
const POR_PAGINA = 50

type Filtro = 'emitida' | 'revisar' | 'error' | 'todas'

function numero(f: Factura): string {
  if (f.numero === null) return '—'
  return `${String(f.punto_venta).padStart(4, '0')}-${String(f.numero).padStart(8, '0')}`
}

function estadoChip(f: Factura) {
  if (f.estado === 'emitida') {
    return <Chip size="small" color="success" variant="outlined" label="Emitida" />
  }
  if (f.estado === 'revisar') {
    return (
      <Tooltip title="ARCA no respondió a tiempo. Se reconcilia con FECompConsultar.">
        <Chip size="small" color="info" variant="outlined" label="En revisión" />
      </Tooltip>
    )
  }
  return (
    <Tooltip title={f.error ?? ''}>
      <Chip size="small" color="error" variant="outlined" label="Error" />
    </Tooltip>
  )
}

export default function FacturasEmitidas() {
  const [filtro, setFiltro] = useState<Filtro>('emitida')
  const [busqueda, setBusqueda] = useState('')
  const [pagina, setPagina] = useState(0)

  const busquedaDiferida = useDebounce(busqueda.trim())

  useEffect(() => {
    setPagina(0)
  }, [busquedaDiferida])

  const { data: visibles = [], isLoading } = useQuery({
    queryKey: ['facturas', filtro, pagina, busquedaDiferida],
    queryFn: () =>
      getFacturas({
        estado: filtro === 'todas' ? undefined : filtro,
        q: busquedaDiferida || undefined,
        limit: POR_PAGINA,
        offset: pagina * POR_PAGINA,
      }),
  })

  return (
    <Card>
      <CardContent sx={{ pb: 0 }}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          justifyContent="space-between"
          alignItems={{ xs: 'stretch', md: 'center' }}
          spacing={1.5}
        >
          <Typography variant="h6">Facturas emitidas</Typography>
          <TextField
            size="small"
            placeholder="Buscar CUIT, razón social, CAE o número"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            sx={{ minWidth: { xs: 0, sm: 320 } }}
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
        </Stack>
        <Tabs
          value={filtro}
          onChange={(_e, v: Filtro) => {
            setFiltro(v)
            setPagina(0)
          }}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{ mt: 1, borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab value="emitida" label="Emitidas" />
          <Tab value="revisar" label="En revisión" />
          <Tab value="error" label="Con error" />
          <Tab value="todas" label="Todas" />
        </Tabs>
      </CardContent>

      <CardContent sx={{ pt: 2 }}>
        {isLoading ? (
          <Stack spacing={1}>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} variant="rounded" height={38} />
            ))}
          </Stack>
        ) : visibles.length === 0 ? (
          <Alert severity="info">
            {busqueda ? 'Ninguna factura coincide con la búsqueda.' : 'No hay facturas acá.'}
          </Alert>
        ) : (
          <TableContainer>
            <Table size="small" sx={{ minWidth: 900 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Número</TableCell>
                  <TableCell>Fecha</TableCell>
                  <TableCell>CUIT receptor</TableCell>
                  <TableCell>Razón social</TableCell>
                  <TableCell align="right">Importe</TableCell>
                  <TableCell>CAE</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell align="right">PDF</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {visibles.map((f) => (
                  <TableRow key={f.id} hover>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{numero(f)}</TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{f.fecha_comprobante}</TableCell>
                    <TableCell>{f.cuit_receptor}</TableCell>
                    <TableCell>{f.razon_social ?? '—'}</TableCell>
                    <TableCell
                      align="right"
                      sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}
                    >
                      {moneda.format(Number(f.importe))}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{f.cae ?? '—'}</Typography>
                      {f.cae_vencimiento && (
                        <Typography variant="caption" color="text.secondary">
                          vence {f.cae_vencimiento}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>{estadoChip(f)}</TableCell>
                    <TableCell align="right">
                      {f.cae && (
                        <Tooltip title="Ver PDF con QR de AFIP">
                          <Link
                            href={facturaPdfUrl(f.id)}
                            target="_blank"
                            rel="noopener"
                            sx={{ display: 'inline-flex' }}
                          >
                            <PictureAsPdfIcon fontSize="small" />
                          </Link>
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
            <Button size="small" disabled={pagina === 0} onClick={() => setPagina((p) => p - 1)}>
              Anteriores
            </Button>
            <Button
              size="small"
              disabled={visibles.length < POR_PAGINA}
              onClick={() => setPagina((p) => p + 1)}
            >
              Siguientes
            </Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  )
}
