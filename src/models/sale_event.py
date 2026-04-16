from datetime import datetime

from pydantic import BaseModel, Field


class SaleEvent(BaseModel):
    """A single sale event detected in the transcription."""

    code: str = Field(..., description="Product code mentioned (e.g. '8', 'código 8')")
    buyer: str = Field(default="", description="Name of the buyer if mentioned")
    price: float | None = Field(default=None, description="Price in local currency")
    description: str = Field(default="", description="Product description context")
    raw_context: str = Field(default="", description="Raw transcription snippet where this was detected")
    timestamp_start: float | None = Field(default=None, description="Approx start time in seconds")


class SalesExtractionResult(BaseModel):
    """Complete sales extraction from a transcription."""

    audio_file: str
    total_sales: int = 0
    total_revenue: float | None = None
    sales: list[SaleEvent] = Field(default_factory=list)
    unmatched_buyers: list[str] = Field(default_factory=list, description="Buyers without a matched code")
    unmatched_codes: list[str] = Field(default_factory=list, description="Codes without a confirmed buyer")
    created_at: datetime = Field(default_factory=datetime.now)

    def compute_totals(self) -> None:
        self.total_sales = len(self.sales)
        prices = [s.price for s in self.sales if s.price is not None]
        self.total_revenue = sum(prices) if prices else None

    def to_report(self) -> str:
        lines = [
            "=" * 65,
            "REPORTE DE VENTAS DETECTADAS EN LIVE",
            "=" * 65,
            f"Archivo: {self.audio_file}",
            f"Fecha:   {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Ventas detectadas: {self.total_sales}",
        ]
        if self.total_revenue is not None:
            lines.append(f"Ingreso total estimado: ${self.total_revenue:,.0f}")
        lines += ["", "-" * 65, "DETALLE DE VENTAS:", "-" * 65, ""]

        for i, sale in enumerate(self.sales, 1):
            buyer = sale.buyer or "Comprador no identificado"
            price = f"${sale.price:,.0f}" if sale.price is not None else "precio no detectado"
            lines.append(f"  {i:>3}. Código {sale.code:<8} → {buyer:<20} {price}")
            if sale.description:
                lines.append(f"       Prenda: {sale.description}")

        if self.unmatched_buyers:
            lines += ["", "-" * 65, "COMPRADORES SIN CÓDIGO ASOCIADO:"]
            for b in self.unmatched_buyers:
                lines.append(f"  - {b}")

        if self.unmatched_codes:
            lines += ["", "-" * 65, "CÓDIGOS SIN COMPRADOR CONFIRMADO:"]
            for c in self.unmatched_codes:
                lines.append(f"  - Código {c}")

        lines.append("=" * 65)
        return "\n".join(lines)
