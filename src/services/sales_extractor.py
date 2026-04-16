import json
import logging
import re
from pathlib import Path

from openai import OpenAI

from src.config import settings
from src.models.sale_event import SaleEvent, SalesExtractionResult
from src.models.transcription import TranscriptionResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un asistente experto en analizar transcripciones de lives de venta de ropa en TikTok/Instagram en español latinoamericano.

Tu tarea es extraer TODAS las ventas confirmadas del texto. Una venta ocurre cuando:
1. Se menciona un CÓDIGO de prenda (número o combinación, ej: "código 8", "el 12", "código 3A")
2. Se menciona quién se lo lleva (ej: "se lo lleva Libby", "vendido para Carla", "es tuyo María")
3. Se menciona un precio (ej: "está en 15", "vale 12", "precio 8 mil")

Responde EXCLUSIVAMENTE con un JSON válido:
{
  "sales": [
    {
      "code": "8",
      "buyer": "Libby",
      "price": 15000,
      "description": "abrigo de marca Only talla L",
      "raw_context": "fragmento exacto del texto donde se detectó"
    }
  ],
  "unmatched_buyers": ["nombre de quien dijo querer algo pero no se confirmó código"],
  "unmatched_codes": ["códigos mencionados sin comprador confirmado"]
}

Reglas importantes:
- price debe ser el número tal como se menciona (si dice "15" asume que es el precio completo tal como se dijo)
- Si no se menciona precio, pon null
- Si no se identifica comprador, pon ""
- Incluye SOLO ventas confirmadas, no intenciones
- El campo raw_context debe ser el fragmento de texto relevante (máx 100 caracteres)
- Responde SOLO con el JSON, sin texto adicional
"""


class SalesExtractorService:
    """
    Extracts detailed sale events from a live-selling transcription.
    Uses a sliding window over segments to maintain context.
    """

    WINDOW_SIZE = 30
    STRIDE = 20

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required. Set it in your .env file.")
        self.client = OpenAI(api_key=settings.openai_api_key)

    def _build_windows(self, transcription: TranscriptionResult) -> list[dict]:
        """
        Build overlapping windows of segments to preserve context across
        keyword boundaries (e.g. code mentioned 5 segments before the buyer name).
        """
        segments = transcription.segments
        windows = []
        for i in range(0, len(segments), self.STRIDE):
            batch = segments[i: i + self.WINDOW_SIZE]
            if not batch:
                break
            text = " ".join(s.text.strip() for s in batch)
            windows.append({
                "text": text,
                "start": batch[0].start,
                "end": batch[-1].end,
                "index": i,
            })
        return windows

    def _call_llm(self, window_text: str, window_index: int) -> dict:
        """Send a single window to OpenAI and return parsed JSON."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Analiza este fragmento de transcripción:\n\n{window_text}"},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception as e:
            logger.warning("LLM call failed for window %d: %s", window_index, e)
            return {}

    def _deduplicate(self, sales: list[SaleEvent]) -> list[SaleEvent]:
        """
        Remove duplicate sales detected in overlapping windows.
        Two sales are considered duplicates if they share the same code AND buyer.
        """
        seen: set[tuple] = set()
        unique: list[SaleEvent] = []
        for sale in sales:
            key = (sale.code.strip().lower(), sale.buyer.strip().lower())
            if key not in seen:
                seen.add(key)
                unique.append(sale)
        return unique

    def extract(self, transcription: TranscriptionResult) -> SalesExtractionResult:
        """
        Run the full sales extraction pipeline over a transcription.

        Args:
            transcription: The TranscriptionResult to analyze.

        Returns:
            SalesExtractionResult with all detected sale events.
        """
        windows = self._build_windows(transcription)
        all_sales: list[SaleEvent] = []
        all_unmatched_buyers: set[str] = set()
        all_unmatched_codes: set[str] = set()

        logger.info("Extracting sales from %d windows...", len(windows))

        for win in windows:
            logger.info(
                "Processing window %d (%.0fs - %.0fs)...",
                win["index"],
                win["start"],
                win["end"],
            )
            data = self._call_llm(win["text"], win["index"])

            for item in data.get("sales", []):
                try:
                    sale = SaleEvent(
                        code=str(item.get("code", "")).strip(),
                        buyer=str(item.get("buyer", "")).strip(),
                        price=item.get("price"),
                        description=str(item.get("description", "")).strip(),
                        raw_context=str(item.get("raw_context", "")).strip(),
                        timestamp_start=win["start"],
                    )
                    if sale.code:
                        all_sales.append(sale)
                except Exception as e:
                    logger.warning("Skipping invalid sale item: %s — %s", item, e)

            for buyer in data.get("unmatched_buyers", []):
                if buyer:
                    all_unmatched_buyers.add(str(buyer).strip())

            for code in data.get("unmatched_codes", []):
                if code:
                    all_unmatched_codes.add(str(code).strip())

        unique_sales = self._deduplicate(all_sales)

        result = SalesExtractionResult(
            audio_file=transcription.audio_file,
            sales=unique_sales,
            unmatched_buyers=sorted(all_unmatched_buyers),
            unmatched_codes=sorted(all_unmatched_codes),
        )
        result.compute_totals()

        logger.info(
            "Extraction complete: %d unique sales detected.",
            result.total_sales,
        )
        return result

    def save(self, result: SalesExtractionResult) -> dict[str, Path]:
        """Save extraction result to JSON and readable report."""
        settings.ensure_dirs()
        stem = Path(result.audio_file).stem
        saved: dict[str, Path] = {}

        json_path = settings.summaries_dir / f"{stem}_sales_events.json"
        json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        saved["json"] = json_path

        report_path = settings.summaries_dir / f"{stem}_sales_report.txt"
        report_path.write_text(result.to_report(), encoding="utf-8")
        saved["report"] = report_path

        logger.info("Sales extraction saved to: %s", list(saved.values()))
        return saved
