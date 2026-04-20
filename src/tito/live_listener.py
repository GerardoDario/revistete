import logging
import re
from pathlib import Path

from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent

from src.db.database import Database
from src.db.models import EstadoProducto

logger = logging.getLogger(__name__)

# Patrón que detecta mensajes como: "Mío 105", "mio ABR-001", "MIO 3A"
# Captura el SKU como todo lo que sigue después de "mio" (case-insensitive)
PATTERN_MIO = re.compile(r"^\s*m[iíi]o\s+([A-Za-z0-9\-]+)\s*$", re.IGNORECASE)


class TitoLiveListener:
    """
    Escucha el chat de un TikTok Live y registra ventas automáticamente
    cuando detecta el patrón 'Mío [SKU]'.
    """

    def __init__(self, tiktok_user: str, db_path: Path = Path("tito.db")) -> None:
        """
        Args:
            tiktok_user: Usuario de TikTok del live (con o sin '@').
                         Ejemplo: '@mi_tienda' o 'mi_tienda'
            db_path:     Ruta al archivo SQLite de TITO.
        """
        self.tiktok_user = tiktok_user
        self.db = Database(db_path)
        self.client = TikTokLiveClient(unique_id=tiktok_user)
        self._register_events()

    def _register_events(self) -> None:
        """Registra los handlers de eventos del live."""

        @self.client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent) -> None:
            print(f"\n[TITO] Conectado al live de @{event.unique_id}")
            print(f"[TITO] Room ID: {self.client.room_id}")
            print(f"[TITO] Escuchando mensajes con patron 'Mio [SKU]'...\n")

        @self.client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent) -> None:
            print("\n[TITO] Desconectado del live.")
            self._print_resumen()

        @self.client.on(CommentEvent)
        async def on_comment(event: CommentEvent) -> None:
            await self._handle_comment(
                usuario=event.user.unique_id or event.user.nickname,
                nickname=event.user.nickname,
                mensaje=event.comment,
            )

    async def _handle_comment(
        self, usuario: str, nickname: str, mensaje: str
    ) -> None:
        """Procesa un comentario buscando el patrón de compra."""
        match = PATTERN_MIO.match(mensaje.strip())
        if not match:
            return

        sku = match.group(1).upper()
        logger.debug("Patron detectado: '%s' por @%s -> SKU: %s", mensaje.strip(), usuario, sku)

        producto = self.db.obtener_producto(sku)

        if producto is None:
            print(f"[TITO] @{nickname}: SKU '{sku}' no existe en el inventario.")
            return

        if producto.estado != EstadoProducto.DISPONIBLE:
            print(
                f"[TITO] @{nickname}: SKU '{sku}' no disponible "
                f"(estado actual: {producto.estado.value})."
            )
            return

        try:
            venta = self.db.reservar_producto(sku, f"@{usuario}")
            print(
                f"[TITO] SKU {sku} asignado a @{usuario} "
                f"| Venta #{venta.id_venta} | ${venta.monto_final:,.0f} | PENDIENTE"
            )
        except ValueError as e:
            print(f"[TITO] Error al reservar SKU '{sku}' para @{usuario}: {e}")

    def _print_resumen(self) -> None:
        """Imprime el resumen del live al desconectarse."""
        try:
            print(self.db.resumen_live())
        except Exception as e:
            logger.error("Error generando resumen: %s", e)

    def run(self) -> None:
        """Inicia la conexión al live de forma bloqueante."""
        print(f"[TITO] Conectando al live de {self.tiktok_user}...")
        self.client.run()

    async def start(self) -> None:
        """Inicia la conexión al live de forma no bloqueante (para uso con asyncio)."""
        await self.client.start()
