import { useQuery } from '@tanstack/react-query'
import Alert from '@mui/material/Alert'
import AppBar from '@mui/material/AppBar'
import Chip from '@mui/material/Chip'
import Container from '@mui/material/Container'
import Stack from '@mui/material/Stack'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import SubirResumen from './components/SubirResumen'
import TablaTransferencias from './components/TablaTransferencias'
import { getConfig } from './api/client'

export default function App() {
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: getConfig })

  return (
    <>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Facturador ARCA
          </Typography>
          {config && (
            <Stack direction="row" spacing={1}>
              <Chip
                size="small"
                color={config.arca_mode === 'produccion' ? 'error' : 'default'}
                label={`ARCA: ${config.arca_mode}`}
              />
              <Chip size="small" label={`Pto. venta ${config.punto_venta}`} />
            </Stack>
          )}
        </Toolbar>
      </AppBar>
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Stack spacing={3}>
          {config?.arca_mode === 'mock' && (
            <Alert severity="warning">
              Modo simulado: los comprobantes no se envían a ARCA y no tienen validez fiscal.
              Configurá el certificado y ARCA_MODE=homologacion o produccion.
            </Alert>
          )}
          {config && (
            <Alert severity="info">
              Concepto de las facturas: <strong>{config.concepto_descripcion}</strong>. Si el padrón
              de ARCA no informa domicilio, se completa con{' '}
              <strong>{config.domicilio_default}</strong>.
            </Alert>
          )}
          <SubirResumen />
          <TablaTransferencias />
        </Stack>
      </Container>
    </>
  )
}
