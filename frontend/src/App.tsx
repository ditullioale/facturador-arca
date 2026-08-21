import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Alert from '@mui/material/Alert'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Container from '@mui/material/Container'
import IconButton from '@mui/material/IconButton'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Toolbar from '@mui/material/Toolbar'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import DarkModeIcon from '@mui/icons-material/DarkModeOutlined'
import LightModeIcon from '@mui/icons-material/LightModeOutlined'
import SubirResumen from './components/SubirResumen'
import TablaTransferencias from './components/TablaTransferencias'
import FacturasEmitidas from './components/FacturasEmitidas'
import { getConfig } from './api/client'
import type { Modo } from './theme'

interface Props {
  modo: Modo
  alternarTema: () => void
}

export default function App({ modo, alternarTema }: Props) {
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig })
  const [seccion, setSeccion] = useState<'transferencias' | 'facturas'>('transferencias')
  const enProduccion = config?.arca_mode === 'produccion'

  const solapas = (ancho: boolean) => (
    <Tabs
      value={seccion}
      onChange={(_e, v) => setSeccion(v)}
      variant={ancho ? 'fullWidth' : 'standard'}
      sx={{ flexGrow: 1, minWidth: 0, '& .MuiTabs-indicator': { height: 2 } }}
    >
      <Tab value="transferencias" label="Transferencias" />
      <Tab value="facturas" label="Facturas emitidas" />
    </Tabs>
  )

  return (
    <>
      <AppBar position="sticky">
        <Toolbar sx={{ gap: 2, minHeight: { xs: 56, sm: 56 } }}>
          <Stack direction="row" spacing={1.25} alignItems="center">
            <Box
              sx={{
                width: 24,
                height: 24,
                borderRadius: '7px',
                background: 'linear-gradient(140deg,#9d92ff,#7c6cff)',
              }}
            />
            <Typography sx={{ fontWeight: 600, letterSpacing: '-0.01em' }}>Facturador</Typography>
          </Stack>
          <Box sx={{ display: { xs: 'none', sm: 'flex' }, flexGrow: 1, minWidth: 0 }}>
            {solapas(false)}
          </Box>
          <Box sx={{ flexGrow: { xs: 1, sm: 0 } }} />
          {config && (
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip
                size="small"
                color={enProduccion ? 'error' : 'default'}
                variant={enProduccion ? 'filled' : 'outlined'}
                label={enProduccion ? 'ARCA producción' : `ARCA ${config.arca_mode}`}
              />
              <Chip
                size="small"
                variant="outlined"
                label={`Pto. venta ${config.punto_venta}`}
                sx={{ display: { xs: 'none', sm: 'inline-flex' } }}
              />
            </Stack>
          )}
          <Tooltip title={modo === 'oscuro' ? 'Tema claro' : 'Tema oscuro'}>
            <IconButton size="small" onClick={alternarTema}>
              {modo === 'oscuro' ? (
                <LightModeIcon fontSize="small" />
              ) : (
                <DarkModeIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        </Toolbar>
        <Box sx={{ display: { xs: 'block', sm: 'none' }, borderTop: 1, borderColor: 'divider' }}>
          {solapas(true)}
        </Box>
      </AppBar>
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Stack spacing={2.5}>
          {config?.arca_mode === 'mock' && (
            <Alert severity="warning">
              Modo simulado: los comprobantes no se envían a ARCA y no tienen validez fiscal.
              Configurá el certificado y ARCA_MODE=homologacion o produccion.
            </Alert>
          )}
          {seccion === 'transferencias' ? (
            <>
              <SubirResumen />
              <TablaTransferencias
                importeMinimo={config?.importe_minimo}
                concepto={config?.concepto_descripcion}
              />
            </>
          ) : (
            <FacturasEmitidas />
          )}
        </Stack>
      </Container>
    </>
  )
}
