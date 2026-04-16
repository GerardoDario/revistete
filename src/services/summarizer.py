import json
import logging
from pathlib import Path

from openai import OpenAI

from src.config import settings
from src.models import SaleItem, SalesSummary, TranscriptionResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un asistente experto en análisis de ventas. Tu tarea es analizar la 
transcripción de una grabación de voz y extraer un resumen detallado de todos los productos 
o artículos que se vendieron.

Debes responder EXCLUSIVAMENTE con un JSON válido con la siguiente estructura:
{
  "items": [
    {
      "product": "nombre del producto",
      "quantity": 1,
      "unit_price": 100.00,
      "total_price": 100.00,
      "notes": "observaciones relevantes"
    }
  ],
  "general_observations": "resumen general de las ventas y observaciones importantes"
}

Reglas:
- Si no se menciona el precio, pon null en unit_price y total_price.
- Si no se menciona la cantidad, asume 1.
- Incluye TODOS los productos o artículos mencionados como vendidos.
- Las observaciones deben incluir contexto relevante (descuentos, devoluciones, acuerdos, etc.).
- Responde SOLO con el JSON, sin texto adicional.
"""


class SummarizerService:
    """Service for generating sales summaries from transcriptions using OpenAI."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. Set it in your .env file."
            )
        self.client = OpenAI(api_key=settings.openai_api_key)

    def _chunk_text(self, text: str, max_chars: int = 12000) -> list[str]:
        """Split text into chunks that fit within the model context."""
        if len(text) <= max_chars:
            return [text]

        words = text.split()
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for word in words:
            if current_len + len(word) + 1 > max_chars:
                chunks.append(" ".join(current))
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len += len(word) + 1

        if current:
            chunks.append(" ".join(current))

        return chunks

    def summarize(self, transcription: TranscriptionResult) -> SalesSummary:
        """
        Analyze a transcription and extract a sales summary.

        Args:
            transcription: The transcription result to analyze.

        Returns:
            SalesSummary with extracted sale items and observations.
        """
        text = transcription.to_plain_text()
        chunks = self._chunk_text(text)
        all_items: list[SaleItem] = []
        observations: list[str] = []

        for i, chunk in enumerate(chunks):
            logger.info(
                "Analyzing chunk %d/%d with OpenAI...",
                i + 1,
                len(chunks),
            )

            user_content = (
                f"Analiza la siguiente transcripción (parte {i + 1} de {len(chunks)}) "
                f"y extrae los productos vendidos:\n\n{chunk}"
            )

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content or "{}"
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response for chunk %d", i + 1)
                continue

            for item_data in data.get("items", []):
                try:
                    all_items.append(SaleItem(**item_data))
                except Exception as e:
                    logger.warning("Skipping invalid item: %s — %s", item_data, e)

            obs = data.get("general_observations", "")
            if obs:
                observations.append(obs)

        summary = SalesSummary(
            audio_file=transcription.audio_file,
            items=all_items,
            general_observations=" | ".join(observations),
        )
        summary.compute_totals()

        logger.info(
            "Summary complete: %d items, total sold: %d",
            len(all_items),
            summary.total_items_sold,
        )
        return summary

    def save_summary(self, summary: SalesSummary) -> dict[str, Path]:
        """
        Save summary to multiple formats.

        Returns:
            Dictionary with format names as keys and file paths as values.
        """
        settings.ensure_dirs()
        stem = Path(summary.audio_file).stem
        saved: dict[str, Path] = {}

        # JSON (structured data)
        json_path = settings.summaries_dir / f"{stem}_summary.json"
        json_path.write_text(
            summary.model_dump_json(indent=2),
            encoding="utf-8",
        )
        saved["json"] = json_path

        # Human-readable report
        report_path = settings.summaries_dir / f"{stem}_summary.txt"
        report_path.write_text(summary.to_report(), encoding="utf-8")
        saved["report"] = report_path

        logger.info("Summary saved to: %s", list(saved.values()))
        return saved
