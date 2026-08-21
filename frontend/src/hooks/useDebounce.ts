import { useEffect, useState } from 'react'

/** Difiere un valor que cambia con cada tecla, para no pegarle al backend en cada letra. */
export function useDebounce<T>(valor: T, ms = 300): T {
  const [diferido, setDiferido] = useState(valor)

  useEffect(() => {
    const id = setTimeout(() => setDiferido(valor), ms)
    return () => clearTimeout(id)
  }, [valor, ms])

  return diferido
}
