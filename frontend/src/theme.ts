import { createTheme, type Theme } from '@mui/material/styles'

/** Tokens del sistema de diseño "Aurora" del gestor (app/static/aurora.css),
 *  para que las dos apps se vean como un solo producto. */
const oscuro = {
  bg: '#08090b',
  surface: '#111318',
  surface2: '#161920',
  line: '#22262f',
  tx: '#e8eaf0',
  tx2: '#a2a9b8',
}

const claro = {
  bg: '#f7f8fa',
  surface: '#ffffff',
  surface2: '#f2f4f7',
  line: '#e4e7ec',
  tx: '#101828',
  tx2: '#5a6478',
}

/** El violeta del modo oscuro sobre blanco no llega a 4.5:1 con texto blanco encima. */
const acento = { oscuro: '#7c6cff', claro: '#5b4fd6' }

export type Modo = 'oscuro' | 'claro'

export function crearTema(modo: Modo): Theme {
  const c = modo === 'oscuro' ? oscuro : claro
  const esOscuro = modo === 'oscuro'

  return createTheme({
    palette: {
      mode: esOscuro ? 'dark' : 'light',
      primary: { main: esOscuro ? acento.oscuro : acento.claro, light: '#9d92ff' },
      success: { main: esOscuro ? '#31c48d' : '#12805c' },
      warning: { main: esOscuro ? '#e8b339' : '#a56a08' },
      error: { main: esOscuro ? '#f2555a' : '#c62c33' },
      info: { main: esOscuro ? '#48a9f8' : '#1a72c4' },
      background: { default: c.bg, paper: c.surface },
      text: { primary: c.tx, secondary: c.tx2 },
      divider: c.line,
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif',
      fontSize: 14,
      h6: { fontSize: '0.95rem', fontWeight: 600, letterSpacing: '-0.01em' },
      body2: { fontSize: '0.8125rem' },
      button: { textTransform: 'none', fontWeight: 500 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundImage: `radial-gradient(900px 300px at 22% -140px, rgba(124,108,255,${
              esOscuro ? 0.14 : 0.06
            }), transparent 70%)`,
            backgroundAttachment: 'fixed',
          },
          '::-webkit-scrollbar': { width: 10, height: 10 },
          '::-webkit-scrollbar-thumb': {
            background: c.line,
            border: '3px solid transparent',
            backgroundClip: 'content-box',
            borderRadius: 8,
          },
        },
      },
      MuiAppBar: {
        defaultProps: { elevation: 0, color: 'transparent' },
        styleOverrides: {
          root: {
            backgroundColor: esOscuro ? 'rgba(13,15,19,.82)' : 'rgba(255,255,255,.82)',
            backdropFilter: 'blur(10px)',
            borderBottom: `1px solid ${c.line}`,
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: 'none', border: `1px solid ${c.line}` },
        },
      },
      MuiCard: { defaultProps: { elevation: 0 } },
      MuiCardContent: { styleOverrides: { root: { padding: 20, '&:last-child': { paddingBottom: 20 } } } },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: { root: { borderRadius: 8, paddingInline: 14 } },
      },
      MuiChip: {
        styleOverrides: {
          root: { borderRadius: 7, fontWeight: 500 },
          sizeSmall: { height: 22, fontSize: '0.72rem' },
        },
      },
      MuiAlert: { styleOverrides: { root: { border: `1px solid ${c.line}`, borderRadius: 10 } } },
      MuiTableCell: {
        styleOverrides: {
          root: { borderColor: c.line, paddingBlock: 10 },
          head: {
            color: c.tx2,
            fontSize: '0.72rem',
            fontWeight: 600,
            letterSpacing: '.04em',
            textTransform: 'uppercase',
            backgroundColor: c.surface2,
          },
        },
      },
      MuiTableRow: {
        styleOverrides: { hover: { '&:hover': { backgroundColor: c.surface2 } } },
      },
      MuiTab: {
        styleOverrides: { root: { textTransform: 'none', fontWeight: 500, minHeight: 42 } },
      },
      MuiTabs: { styleOverrides: { root: { minHeight: 42 } } },
      MuiTooltip: { defaultProps: { arrow: true } },
    },
  })
}
