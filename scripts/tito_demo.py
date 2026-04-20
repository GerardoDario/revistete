"""
Demo de TITO: prueba las funciones básicas de la base de datos.
Ejecutar desde la raíz del proyecto:
    uv run python scripts/tito_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import Database, EstadoProducto, EstadoPago
from src.db.models import Inventario

db = Database(Path("tito_demo.db"))

print("\n--- Agregando productos al inventario ---")
productos = [
    Inventario(id_sku="ABR-001", descripcion="Abrigo Only talla L beige",    costo_compra=8000,  precio_venta=15000),
    Inventario(id_sku="ABR-002", descripcion="Abrigo paño negro talla M",    costo_compra=6000,  precio_venta=12000),
    Inventario(id_sku="ABR-003", descripcion="Chaleco acolchado talla S",     costo_compra=4500,  precio_venta=9000),
    Inventario(id_sku="ABR-004", descripcion="Abrigo largo gris talla L",    costo_compra=10000, precio_venta=18000),
]

for p in productos:
    db.agregar_producto(p)
    print(f"  OK {p.id_sku} - {p.descripcion} (${p.precio_venta:,.0f})")

print("\n--- Valor inicial del inventario ---")
v = db.valor_inventario()
print(f"  Disponibles: {v['disponibles']} | Stock valorizado: ${v['valor_stock_disponible']:,.0f}")

print("\n--- Reservando productos durante el live ---")
venta1 = db.reservar_producto("ABR-001", "@libby_cl")
print(f"  Reserva #{venta1.id_venta}: {venta1.id_sku} -> {venta1.usuario_tiktok} (${venta1.monto_final:,.0f})")

venta2 = db.reservar_producto("ABR-003", "@carolina_r")
print(f"  Reserva #{venta2.id_venta}: {venta2.id_sku} -> {venta2.usuario_tiktok} (${venta2.monto_final:,.0f})")

print("\n--- Confirmando pago de venta #1 ---")
venta1_pagada = db.confirmar_pago(venta1.id_venta)
print(f"  Venta #{venta1_pagada.id_venta} -> estado: {venta1_pagada.estado_pago.value}")

print("\n--- Cancelando reserva #2 (no pago) ---")
db.cancelar_reserva(venta2.id_venta)
print(f"  Reserva #{venta2.id_venta} cancelada. ABR-003 vuelve a disponible.")

print("\n--- Verificando inventario disponible ---")
disponibles = db.listar_inventario(EstadoProducto.DISPONIBLE)
for p in disponibles:
    print(f"  {p.id_sku} - {p.descripcion}")

print()
print(db.resumen_live())

import os
os.remove("tito_demo.db")
print("\nDemo completada. Base de datos demo eliminada.")
