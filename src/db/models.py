from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EstadoProducto(str, Enum):
    DISPONIBLE = "disponible"
    RESERVADO = "reservado"
    VENDIDO = "vendido"


class EstadoPago(str, Enum):
    PENDIENTE = "pendiente"
    PAGADO = "pagado"


class Inventario(BaseModel):
    id_sku: str = Field(..., description="Código único del producto (ej: 'ABR-001')")
    descripcion: str = Field(..., description="Descripción del producto")
    costo_compra: float = Field(..., ge=0, description="Costo de compra")
    precio_venta: float = Field(..., ge=0, description="Precio de venta al público")
    estado: EstadoProducto = Field(default=EstadoProducto.DISPONIBLE)

    @property
    def margen(self) -> float:
        if self.costo_compra == 0:
            return 0.0
        return ((self.precio_venta - self.costo_compra) / self.costo_compra) * 100


class Venta(BaseModel):
    id_venta: Optional[int] = Field(default=None, description="ID autoincremental")
    id_sku: str = Field(..., description="SKU del producto vendido")
    usuario_tiktok: str = Field(..., description="Usuario de TikTok del comprador")
    timestamp: datetime = Field(default_factory=datetime.now)
    estado_pago: EstadoPago = Field(default=EstadoPago.PENDIENTE)
    monto_final: float = Field(..., ge=0, description="Monto final de la venta")
