"""
TITO - Listener de ventas en TikTok Live.

Uso:
    uv run python scripts/tito_live.py @mi_tienda
    uv run python scripts/tito_live.py @mi_tienda --db ruta/custom.db
    uv run python scripts/tito_live.py @mi_tienda --verbose
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tito.live_listener import TitoLiveListener


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TITO - Detector de ventas en TikTok Live",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  uv run python scripts/tito_live.py @mi_tienda
  uv run python scripts/tito_live.py mi_tienda --db tito.db
  uv run python scripts/tito_live.py @mi_tienda --verbose

Patron de compra reconocido en el chat:
  "Mio 105"     -> reserva SKU 105
  "Mio ABR-001" -> reserva SKU ABR-001
        """,
    )
    parser.add_argument(
        "usuario",
        help="Usuario de TikTok del live (ej: @mi_tienda o mi_tienda)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("tito.db"),
        help="Ruta al archivo de base de datos SQLite (default: tito.db)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar logs de debug",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    listener = TitoLiveListener(
        tiktok_user=args.usuario,
        db_path=args.db,
    )
    listener.run()


if __name__ == "__main__":
    main()
