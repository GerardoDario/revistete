import email
import email.header
import imaplib
import logging
import quopri
from base64 import b64decode
from dataclasses import dataclass, field
from datetime import datetime
from email.message import Message
from pathlib import Path

from src.config import settings
from src.db.database import Database
from src.db.models import EstadoPago, Inventario, Venta
from src.tito.payment_parser import ParsedPayment, parse_email

logger = logging.getLogger(__name__)

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993

SEARCH_KEYWORDS = ["Transferencia", "Comprobante", "Recibida", "Recibiste", "Pago recibido"]


@dataclass
class PaymentMatch:
    """Resultado de un matching entre un correo y una venta pendiente."""
    venta: Venta
    payment: ParsedPayment
    utilidad_neta: float
    confirmada: bool = False


@dataclass
class CheckResult:
    """Resultado completo de una revisión de correos."""
    correos_revisados: int = 0
    correos_con_pago: int = 0
    matches: list[PaymentMatch] = field(default_factory=list)
    sin_match: list[ParsedPayment] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_report(self) -> str:
        lines = [
            "=" * 60,
            "  REPORTE DE CONFIRMACION DE PAGOS — TITO",
            "=" * 60,
            f"  Fecha       : {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Correos leidos : {self.correos_revisados}",
            f"  Con pago detectado: {self.correos_con_pago}",
            f"  Pagos confirmados: {len(self.matches)}",
            f"  Sin coincidencia : {len(self.sin_match)}",
            "-" * 60,
        ]

        if self.matches:
            lines.append("\nPAGOS CONFIRMADOS:")
            for m in self.matches:
                lines.append(
                    f"  Venta #{m.venta.id_venta} | {m.venta.id_sku} | "
                    f"@{m.venta.usuario_tiktok} | ${m.venta.monto_final:,.0f} | "
                    f"Emisor: {m.payment.emisor} ({m.payment.banco_origen})"
                )
                lines.append(f"    Utilidad neta: ${m.utilidad_neta:,.0f}")

        if self.sin_match:
            lines.append("\nPAGOS SIN COINCIDENCIA (revision manual):")
            for p in self.sin_match:
                lines.append(f"  ${p.monto:,.0f} de {p.emisor} ({p.banco_origen})")
                lines.append(f"    Asunto: {p.raw_subject}")

        if self.errores:
            lines.append("\nERRORES:")
            for e in self.errores:
                lines.append(f"  ! {e}")

        lines.append("=" * 60)
        return "\n".join(lines)


class EmailChecker:
    """
    Revisa Gmail buscando comprobantes de pago y confirma ventas en TITO.
    Usa IMAP con App Password de Google (no requiere OAuth).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        if not settings.gmail_address or not settings.gmail_app_password:
            raise ValueError(
                "GMAIL_ADDRESS y GMAIL_APP_PASSWORD son requeridos en .env\n"
                "Genera una App Password en: https://myaccount.google.com/apppasswords"
            )
        self.address = settings.gmail_address
        self.password = settings.gmail_app_password
        self.tolerance = settings.payment_tolerance
        self.db = Database(db_path or settings.tito_db_path)

    # ------------------------------------------------------------------
    # IMAP helpers
    # ------------------------------------------------------------------

    def _connect(self) -> imaplib.IMAP4_SSL:
        """Abre conexión IMAP y hace login."""
        conn = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
        conn.login(self.address, self.password)
        return conn

    def _fetch_unread(self, conn: imaplib.IMAP4_SSL) -> list[bytes]:
        """Retorna lista de IDs de correos no leídos que coincidan con keywords."""
        conn.select("INBOX")
        all_ids: set[bytes] = set()

        for keyword in SEARCH_KEYWORDS:
            _, data = conn.search(None, f'(UNSEEN SUBJECT "{keyword}")')
            if data and data[0]:
                for uid in data[0].split():
                    all_ids.add(uid)

        return list(all_ids)

    def _decode_header(self, raw: str) -> str:
        """Decodifica headers de correo (soporta UTF-8, Latin-1, etc.)."""
        parts = email.header.decode_header(raw)
        result = []
        for part, enc in parts:
            if isinstance(part, bytes):
                result.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)

    def _get_body(self, msg: Message) -> str:
        """Extrae el cuerpo en texto plano de un correo (multipart o simple)."""
        body_parts = []

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition", ""))
                if ct == "text/plain" and "attachment" not in cd:
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_parts.append(payload.decode(charset, errors="replace"))
        else:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                body_parts.append(payload.decode(charset, errors="replace"))

        return "\n".join(body_parts)

    def _parse_message(self, conn: imaplib.IMAP4_SSL, uid: bytes) -> ParsedPayment | None:
        """Descarga y parsea un correo individual."""
        _, data = conn.fetch(uid, "(RFC822)")
        if not data or not data[0]:
            return None

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = self._decode_header(msg.get("Subject", ""))
        body = self._get_body(msg)

        return parse_email(subject, body)

    def _mark_as_read(self, conn: imaplib.IMAP4_SSL, uid: bytes) -> None:
        conn.store(uid, "+FLAGS", "\\Seen")

    # ------------------------------------------------------------------
    # Matching de pagos con ventas pendientes
    # ------------------------------------------------------------------

    def _find_match(
        self, payment: ParsedPayment, pending: list[Venta]
    ) -> Venta | None:
        """
        Busca la venta pendiente cuyo monto coincida con el pago,
        dentro del margen de tolerancia configurado.
        Prioriza la coincidencia más exacta.
        """
        best: Venta | None = None
        best_diff = float("inf")

        for venta in pending:
            diff = abs(venta.monto_final - payment.monto)
            if diff <= self.tolerance and diff < best_diff:
                best = venta
                best_diff = diff

        return best

    def _get_utilidad(self, venta: Venta) -> float:
        """Calcula la utilidad neta de una venta (precio_venta - costo_compra)."""
        producto = self.db.obtener_producto(venta.id_sku)
        if producto is None:
            return 0.0
        return producto.precio_venta - producto.costo_compra

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    def check(self, mark_as_read: bool = True) -> CheckResult:
        """
        Revisa Gmail, extrae pagos, los cruza con ventas pendientes
        y confirma automáticamente las que coincidan.

        Args:
            mark_as_read: Si True, marca los correos procesados como leídos.

        Returns:
            CheckResult con el detalle completo de la operación.
        """
        result = CheckResult()
        pending_ventas = self.db.listar_ventas(EstadoPago.PENDIENTE)

        if not pending_ventas:
            logger.info("No hay ventas pendientes. Nada que confirmar.")
            return result

        logger.info(
            "Revisando Gmail para %d ventas pendientes...",
            len(pending_ventas),
        )

        try:
            conn = self._connect()
        except imaplib.IMAP4.error as e:
            result.errores.append(f"Error de conexion IMAP: {e}")
            return result

        try:
            uids = self._fetch_unread(conn)
            result.correos_revisados = len(uids)
            logger.info("Correos no leidos encontrados: %d", len(uids))

            already_matched: set[int] = set()

            for uid in uids:
                try:
                    payment = self._parse_message(conn, uid)
                except Exception as e:
                    result.errores.append(f"Error parseando correo {uid}: {e}")
                    continue

                if payment is None:
                    continue

                result.correos_con_pago += 1
                logger.info(
                    "Pago detectado: $%.0f de %s (%s)",
                    payment.monto,
                    payment.emisor,
                    payment.banco_origen,
                )

                # Excluir ventas ya matcheadas en esta sesión
                available = [v for v in pending_ventas if v.id_venta not in already_matched]
                match_venta = self._find_match(payment, available)

                if match_venta is None:
                    result.sin_match.append(payment)
                    logger.warning(
                        "Sin coincidencia para pago de $%.0f (tolerancia: $%.0f)",
                        payment.monto,
                        self.tolerance,
                    )
                    continue

                try:
                    venta_pagada = self.db.confirmar_pago(match_venta.id_venta)
                    utilidad = self._get_utilidad(venta_pagada)
                    already_matched.add(match_venta.id_venta)

                    match_result = PaymentMatch(
                        venta=venta_pagada,
                        payment=payment,
                        utilidad_neta=utilidad,
                        confirmada=True,
                    )
                    result.matches.append(match_result)

                    print(
                        f"[TITO] Pago confirmado: Venta #{venta_pagada.id_venta} | "
                        f"{venta_pagada.id_sku} | @{venta_pagada.usuario_tiktok} | "
                        f"${venta_pagada.monto_final:,.0f} | "
                        f"Utilidad: ${utilidad:,.0f}"
                    )

                    if mark_as_read:
                        self._mark_as_read(conn, uid)

                except ValueError as e:
                    result.errores.append(str(e))

        finally:
            try:
                conn.logout()
            except Exception:
                pass

        return result
