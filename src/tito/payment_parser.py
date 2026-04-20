"""
Parsers de correos de pago para bancos chilenos.
Cada banco tiene su propio formato de comprobante.
"""
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Modelo de resultado de parsing
# ---------------------------------------------------------------------------

@dataclass
class ParsedPayment:
    """Datos extraídos de un correo de comprobante de pago."""
    monto: float
    emisor: str
    banco_origen: str
    raw_subject: str
    raw_snippet: str = ""


# ---------------------------------------------------------------------------
# Patrones por banco (orden de prioridad: más específico primero)
# ---------------------------------------------------------------------------

# Monto: acepta formatos como $15.000, $15,000, 15000, 15.000,00
_MONTO_PATTERNS = [
    r"\$\s?([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)",   # $15.000 / $15,000.00
    r"(?:monto|valor|importe|total)[:\s]+\$?\s?([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)",
    r"([\d]{1,3}(?:\.\d{3})+)(?:\s*pesos|\s*CLP|\s*clp)?",  # 15.000 pesos
]

_EMISOR_PATTERNS = [
    r"(?:de|desde|nombre|emisor|remitente|transferido por)[:\s]+([A-Za-záéíóúÁÉÍÓÚñÑ\s]{3,50}?)(?:\n|,|\.|$)",
    r"(?:te\s+(?:envió|envio|transfirió|transfirió))[:\s]+([A-Za-záéíóúÁÉÍÓÚñÑ\s]{3,50}?)(?:\n|,|\.|$)",
]

_BANCO_KEYWORDS = {
    "BancoEstado":  ["bancoestado", "banco estado", "cuentarut"],
    "Tenpo":        ["tenpo"],
    "MercadoPago":  ["mercadopago", "mercado pago", "mp"],
    "Santander":    ["santander"],
    "BCI":          ["bci", "banco bci"],
    "Scotiabank":   ["scotiabank"],
    "Itaú":         ["itau", "itaú"],
    "BICE":         ["bice"],
}


def _extract_monto(text: str) -> float | None:
    """Extrae el primer monto monetario encontrado en el texto."""
    for pattern in _MONTO_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(".", "").replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _extract_emisor(text: str) -> str:
    """Extrae el nombre del emisor del pago."""
    for pattern in _EMISOR_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip().title()
    return "Desconocido"


def _detect_banco(text: str) -> str:
    """Detecta el banco origen según palabras clave."""
    lower = text.lower()
    for banco, keywords in _BANCO_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return banco
    return "Desconocido"


def parse_email(subject: str, body: str) -> ParsedPayment | None:
    """
    Intenta extraer datos de pago de un correo.

    Args:
        subject: Asunto del correo.
        body:    Cuerpo del correo en texto plano.

    Returns:
        ParsedPayment si se pudo extraer el monto, None si no aplica.
    """
    full_text = f"{subject}\n{body}"
    monto = _extract_monto(full_text)
    if monto is None:
        return None

    return ParsedPayment(
        monto=monto,
        emisor=_extract_emisor(full_text),
        banco_origen=_detect_banco(full_text),
        raw_subject=subject,
        raw_snippet=body[:200].replace("\n", " "),
    )
