import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { subirResumen, type ResultadoImportacion } from '../api/client'

export default function SubirResumen() {
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const [resultado, setResultado] = useState<ResultadoImportacion | null>(null)

  const mutacion = useMutation({
    mutationFn: subirResumen,
    onSuccess: (data) => {
      setResultado(data)
      queryClient.invalidateQueries({ queryKey: ['transferencias'] })
    },
  })

  const error = mutacion.error
  const mensajeError =
    error && typeof error === 'object' && 'response' in error
      ? ((error as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
        'No se pudo procesar el archivo')
      : error
        ? 'No se pudo procesar el archivo'
        : null

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          1. Subir resumen bancario
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Excel, CSV o PDF exportado de Santander o Macro. Se detectan las transferencias recibidas
          (CUIT del emisor, importe y fecha).
        </Typography>
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 2 }}>
          <Button
            variant="contained"
            startIcon={<UploadFileIcon />}
            disabled={mutacion.isPending}
            onClick={() => inputRef.current?.click()}
          >
            {mutacion.isPending ? 'Procesando…' : 'Elegir archivo'}
          </Button>
          <input
            ref={inputRef}
            type="file"
            hidden
            accept=".xlsx,.xlsm,.xls,.csv,.pdf"
            onChange={(e) => {
              const archivo = e.target.files?.[0]
              if (archivo) mutacion.mutate(archivo)
              e.target.value = ''
            }}
          />
        </Stack>
        {mensajeError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {mensajeError}
          </Alert>
        )}
        {resultado && (
          <Box sx={{ mt: 2 }}>
            <Alert severity={resultado.nuevas > 0 ? 'success' : 'info'}>
              {resultado.lote.nombre_archivo} ({resultado.lote.banco}):{' '}
              {resultado.nuevas} transferencias nuevas, {resultado.duplicadas} duplicadas
              omitidas, {resultado.sin_cuit} sin CUIT detectado.
            </Alert>
          </Box>
        )}
      </CardContent>
    </Card>
  )
}
