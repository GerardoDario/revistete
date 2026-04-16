from datetime import datetime

from pydantic import BaseModel, Field


class SaleItem(BaseModel):
    """Represents a single item or product mentioned as sold."""

    product: str = Field(..., description="Product or item name")
    quantity: int = Field(default=1, ge=0)
    unit_price: float | None = Field(default=None, ge=0)
    total_price: float | None = Field(default=None, ge=0)
    notes: str = ""


class SalesSummary(BaseModel):
    """Summary of sales extracted from a transcription."""

    audio_file: str
    transcription_file: str = ""
    items: list[SaleItem] = Field(default_factory=list)
    total_items_sold: int = 0
    total_revenue: float | None = None
    general_observations: str = ""
    created_at: datetime = Field(default_factory=datetime.now)

    def compute_totals(self) -> None:
        """Recalculate totals based on items."""
        self.total_items_sold = sum(item.quantity for item in self.items)
        prices = [item.total_price for item in self.items if item.total_price is not None]
        if prices:
            self.total_revenue = sum(prices)

    def to_report(self) -> str:
        """Generate a human-readable sales report."""
        lines = [
            "=" * 60,
            "RESUMEN DE VENTAS",
            "=" * 60,
            f"Archivo de audio: {self.audio_file}",
            f"Fecha de análisis: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "-" * 60,
            "",
            "PRODUCTOS VENDIDOS:",
            "",
        ]

        for i, item in enumerate(self.items, 1):
            line = f"  {i}. {item.product}"
            if item.quantity > 1:
                line += f" (x{item.quantity})"
            if item.unit_price is not None:
                line += f" - Precio unitario: ${item.unit_price:,.2f}"
            if item.total_price is not None:
                line += f" - Total: ${item.total_price:,.2f}"
            if item.notes:
                line += f"\n     Nota: {item.notes}"
            lines.append(line)

        lines.append("")
        lines.append("-" * 60)
        lines.append(f"Total de artículos vendidos: {self.total_items_sold}")
        if self.total_revenue is not None:
            lines.append(f"Ingreso total: ${self.total_revenue:,.2f}")
        if self.general_observations:
            lines.append(f"\nObservaciones: {self.general_observations}")
        lines.append("=" * 60)

        return "\n".join(lines)
