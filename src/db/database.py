import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from .models import EstadoPago, EstadoProducto, Inventario, Venta

DEFAULT_DB_PATH = Path("tito.db")


class Database:
    """
    Gestiona la base de datos SQLite local de TITO.
    Maneja inventario de productos y registro de ventas del live.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Crea las tablas si no existen."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS inventario (
                    id_sku       TEXT PRIMARY KEY,
                    descripcion  TEXT NOT NULL,
                    costo_compra REAL NOT NULL CHECK(costo_compra >= 0),
                    precio_venta REAL NOT NULL CHECK(precio_venta >= 0),
                    estado       TEXT NOT NULL DEFAULT 'disponible'
                                 CHECK(estado IN ('disponible', 'reservado', 'vendido'))
                );

                CREATE TABLE IF NOT EXISTS ventas (
                    id_venta       INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_sku         TEXT NOT NULL REFERENCES inventario(id_sku),
                    usuario_tiktok TEXT NOT NULL,
                    timestamp      TEXT NOT NULL,
                    estado_pago    TEXT NOT NULL DEFAULT 'pendiente'
                                   CHECK(estado_pago IN ('pendiente', 'pagado')),
                    monto_final    REAL NOT NULL CHECK(monto_final >= 0)
                );
            """)

    # ------------------------------------------------------------------
    # INVENTARIO
    # ------------------------------------------------------------------

    def agregar_producto(self, producto: Inventario) -> Inventario:
        """
        Agrega un nuevo producto al inventario.
        Lanza ValueError si el id_sku ya existe.
        """
        with self._conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO inventario (id_sku, descripcion, costo_compra, precio_venta, estado)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        producto.id_sku,
                        producto.descripcion,
                        producto.costo_compra,
                        producto.precio_venta,
                        producto.estado.value,
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"El SKU '{producto.id_sku}' ya existe en el inventario.")
        return producto

    def obtener_producto(self, id_sku: str) -> Optional[Inventario]:
        """Retorna un producto por su SKU, o None si no existe."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM inventario WHERE id_sku = ?", (id_sku,)
            ).fetchone()
        if row is None:
            return None
        return Inventario(**dict(row))

    def listar_inventario(
        self, estado: Optional[EstadoProducto] = None
    ) -> list[Inventario]:
        """Lista productos, opcionalmente filtrados por estado."""
        with self._conn() as conn:
            if estado:
                rows = conn.execute(
                    "SELECT * FROM inventario WHERE estado = ? ORDER BY id_sku",
                    (estado.value,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM inventario ORDER BY id_sku"
                ).fetchall()
        return [Inventario(**dict(r)) for r in rows]

    def reservar_producto(self, id_sku: str, usuario_tiktok: str) -> Venta:
        """
        Marca un producto como RESERVADO durante el live y crea una venta pendiente.
        Lanza ValueError si el producto no está disponible.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM inventario WHERE id_sku = ?", (id_sku,)
            ).fetchone()

            if row is None:
                raise ValueError(f"Producto '{id_sku}' no encontrado.")
            if row["estado"] != EstadoProducto.DISPONIBLE.value:
                raise ValueError(
                    f"Producto '{id_sku}' no está disponible (estado: {row['estado']})."
                )

            conn.execute(
                "UPDATE inventario SET estado = ? WHERE id_sku = ?",
                (EstadoProducto.RESERVADO.value, id_sku),
            )

            now = datetime.now().isoformat()
            cursor = conn.execute(
                """
                INSERT INTO ventas (id_sku, usuario_tiktok, timestamp, estado_pago, monto_final)
                VALUES (?, ?, ?, ?, ?)
                """,
                (id_sku, usuario_tiktok, now, EstadoPago.PENDIENTE.value, row["precio_venta"]),
            )
            venta = Venta(
                id_venta=cursor.lastrowid,
                id_sku=id_sku,
                usuario_tiktok=usuario_tiktok,
                timestamp=datetime.fromisoformat(now),
                estado_pago=EstadoPago.PENDIENTE,
                monto_final=row["precio_venta"],
            )
        return venta

    def confirmar_pago(self, id_venta: int) -> Venta:
        """
        Marca una venta como PAGADA y el producto como VENDIDO.
        Lanza ValueError si la venta no existe o ya está pagada.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM ventas WHERE id_venta = ?", (id_venta,)
            ).fetchone()

            if row is None:
                raise ValueError(f"Venta #{id_venta} no encontrada.")
            if row["estado_pago"] == EstadoPago.PAGADO.value:
                raise ValueError(f"Venta #{id_venta} ya está pagada.")

            conn.execute(
                "UPDATE ventas SET estado_pago = ? WHERE id_venta = ?",
                (EstadoPago.PAGADO.value, id_venta),
            )
            conn.execute(
                "UPDATE inventario SET estado = ? WHERE id_sku = ?",
                (EstadoProducto.VENDIDO.value, row["id_sku"]),
            )

            venta = Venta(
                id_venta=row["id_venta"],
                id_sku=row["id_sku"],
                usuario_tiktok=row["usuario_tiktok"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                estado_pago=EstadoPago.PAGADO,
                monto_final=row["monto_final"],
            )
        return venta

    def cancelar_reserva(self, id_venta: int) -> None:
        """
        Cancela una reserva pendiente y devuelve el producto a DISPONIBLE.
        Lanza ValueError si la venta no existe o ya fue pagada.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM ventas WHERE id_venta = ?", (id_venta,)
            ).fetchone()

            if row is None:
                raise ValueError(f"Venta #{id_venta} no encontrada.")
            if row["estado_pago"] == EstadoPago.PAGADO.value:
                raise ValueError(f"No se puede cancelar: venta #{id_venta} ya está pagada.")

            conn.execute("DELETE FROM ventas WHERE id_venta = ?", (id_venta,))
            conn.execute(
                "UPDATE inventario SET estado = ? WHERE id_sku = ?",
                (EstadoProducto.DISPONIBLE.value, row["id_sku"]),
            )

    # ------------------------------------------------------------------
    # VENTAS
    # ------------------------------------------------------------------

    def listar_ventas(
        self, estado_pago: Optional[EstadoPago] = None
    ) -> list[Venta]:
        """Lista ventas, opcionalmente filtradas por estado de pago."""
        with self._conn() as conn:
            if estado_pago:
                rows = conn.execute(
                    "SELECT * FROM ventas WHERE estado_pago = ? ORDER BY timestamp",
                    (estado_pago.value,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ventas ORDER BY timestamp"
                ).fetchall()
        return [
            Venta(
                id_venta=r["id_venta"],
                id_sku=r["id_sku"],
                usuario_tiktok=r["usuario_tiktok"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                estado_pago=EstadoPago(r["estado_pago"]),
                monto_final=r["monto_final"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # REPORTES
    # ------------------------------------------------------------------

    def valor_inventario(self) -> dict:
        """
        Calcula el valor total del inventario disponible y vendido.
        Retorna un dict con métricas de negocio.
        """
        with self._conn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE estado = 'disponible')  AS disponibles,
                    COUNT(*) FILTER (WHERE estado = 'reservado')   AS reservados,
                    COUNT(*) FILTER (WHERE estado = 'vendido')     AS vendidos,
                    COALESCE(SUM(costo_compra)  FILTER (WHERE estado = 'disponible'), 0) AS costo_stock,
                    COALESCE(SUM(precio_venta)  FILTER (WHERE estado = 'disponible'), 0) AS valor_stock,
                    COALESCE(SUM(precio_venta)  FILTER (WHERE estado IN ('reservado','vendido')), 0) AS valor_vendido
                FROM inventario
            """).fetchone()

            ventas_pagadas = conn.execute("""
                SELECT COALESCE(SUM(monto_final), 0) AS cobrado
                FROM ventas WHERE estado_pago = 'pagado'
            """).fetchone()

        return {
            "disponibles": row["disponibles"],
            "reservados": row["reservados"],
            "vendidos": row["vendidos"],
            "costo_stock_disponible": round(row["costo_stock"], 2),
            "valor_stock_disponible": round(row["valor_stock"], 2),
            "valor_vendido_potencial": round(row["valor_vendido"], 2),
            "cobrado_efectivo": round(ventas_pagadas["cobrado"], 2),
        }

    def resumen_live(self) -> str:
        """Genera un resumen legible del live actual."""
        v = self.valor_inventario()
        pendientes = self.listar_ventas(EstadoPago.PENDIENTE)

        lines = [
            "=" * 55,
            "  RESUMEN LIVE — TITO",
            "=" * 55,
            f"  Productos disponibles : {v['disponibles']}",
            f"  Productos reservados  : {v['reservados']}",
            f"  Productos vendidos    : {v['vendidos']}",
            "-" * 55,
            f"  Valor stock disponible: ${v['valor_stock_disponible']:,.0f}",
            f"  Ventas potenciales    : ${v['valor_vendido_potencial']:,.0f}",
            f"  Cobrado efectivo      : ${v['cobrado_efectivo']:,.0f}",
            "-" * 55,
        ]

        if pendientes:
            lines.append(f"  PENDIENTES DE PAGO ({len(pendientes)}):")
            for p in pendientes:
                lines.append(f"    #{p.id_venta} · {p.id_sku} · @{p.usuario_tiktok} · ${p.monto_final:,.0f}")

        lines.append("=" * 55)
        return "\n".join(lines)
