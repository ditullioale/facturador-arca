import re

CUIT_RE = re.compile(r"(?<!\d)(\d{2})[-\s.]?(\d{8})[-\s.]?(\d)(?!\d)")


def solo_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor)


def es_cuit_valido(cuit: str) -> bool:
    """Valida los 11 dígitos de un CUIT/CUIL con su dígito verificador."""
    cuit = solo_digitos(cuit)
    if len(cuit) != 11 or cuit == "0" * 11:
        return False
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    suma = sum(int(d) * p for d, p in zip(cuit[:10], pesos, strict=False))
    resto = suma % 11
    verificador = {0: 0, 1: 9}.get(resto, 11 - resto)
    return verificador == int(cuit[10])


def normalizar_cuit(valor: object) -> str | None:
    """Devuelve el CUIT normalizado a 11 dígitos, o None si no es válido."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if isinstance(valor, float) and valor.is_integer():
        texto = str(int(valor))
    digitos = solo_digitos(texto)
    if len(digitos) == 11 and es_cuit_valido(digitos):
        return digitos
    return None


def extraer_cuit(texto: str) -> str | None:
    """Busca el primer CUIT válido dentro de un texto libre (descripción del movimiento)."""
    for match in CUIT_RE.finditer(texto or ""):
        candidato = "".join(match.groups())
        if es_cuit_valido(candidato):
            return candidato
    return None
