"""
TITO - Confirmador automatico de pagos via Gmail.

Revisa correos no leidos con comprobantes de transferencias,
los cruza con ventas pendientes en SQLite y confirma los pagos.

Uso:
    uv run python scripts/tito_check_payments.py
    uv run python scripts/tito_check_payments.py --no-mark-read
    uv run python scripts/tito_check_payments.py --db tito.db --verbose
    uv run python scripts/tito_check_payments.py --loop 60
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tito.email_checker import EmailChecker


def run_once(db_path: Path, mark_as_read: bool, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        checker = EmailChecker(db_path=db_path)
    except ValueError as e:
        print(f"[TITO] Error de configuracion: {e}", file=sys.stderr)
        sys.exit(1)

    result = checker.check(mark_as_read=mark_as_read)
    print(result.to_report())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TITO - Confirmacion automatica de pagos via Gmail",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuracion requerida en .env:
  GMAIL_ADDRESS=tu_correo@gmail.com
  GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
  PAYMENT_TOLERANCE=500

Genera tu App Password en:
  https://myaccount.google.com/apppasswords

Ejemplos:
  uv run python scripts/tito_check_payments.py
  uv run python scripts/tito_check_payments.py --loop 120
  uv run python scripts/tito_check_payments.py --no-mark-read --verbose
        """,
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Ruta al archivo SQLite de TITO (default: valor en .env o tito.db)",
    )
    parser.add_argument(
        "--no-mark-read",
        action="store_true",
        help="No marcar correos como leidos (util para pruebas)",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        metavar="SEGUNDOS",
        help="Revisar correos cada N segundos de forma continua",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar logs de debug",
    )

    args = parser.parse_args()
    mark_as_read = not args.no_mark_read

    if args.loop > 0:
        print(f"[TITO] Modo continuo: revisando correos cada {args.loop}s (Ctrl+C para detener)")
        try:
            while True:
                run_once(args.db, mark_as_read, args.verbose)
                print(f"\n[TITO] Proxima revision en {args.loop}s...\n")
                time.sleep(args.loop)
        except KeyboardInterrupt:
            print("\n[TITO] Detenido.")
    else:
        run_once(args.db, mark_as_read, args.verbose)


if __name__ == "__main__":
    main()
