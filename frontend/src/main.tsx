import React, { useMemo, useState } from 'react'
import ReactDOM from 'react-dom/client'
import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { crearTema, type Modo } from './theme'

const CLAVE_TEMA = 'facturador.tema'

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } })

function Raiz() {
  const [modo, setModo] = useState<Modo>(
    () => (localStorage.getItem(CLAVE_TEMA) as Modo | null) ?? 'oscuro',
  )
  const tema = useMemo(() => crearTema(modo), [modo])

  const alternarTema = () => {
    const siguiente: Modo = modo === 'oscuro' ? 'claro' : 'oscuro'
    localStorage.setItem(CLAVE_TEMA, siguiente)
    setModo(siguiente)
  }

  return (
    <ThemeProvider theme={tema}>
      <CssBaseline />
      <App modo={modo} alternarTema={alternarTema} />
    </ThemeProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <Raiz />
    </QueryClientProvider>
  </React.StrictMode>,
)
