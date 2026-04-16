import json
import logging
from pathlib import Path

import faster_whisper
from pydub import AudioSegment

from src.config import settings
from src.models import AudioMetadata, TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)


class TranscriberService:
    """Service for transcribing long audio files using faster-whisper."""

    def __init__(self) -> None:
        self.model_size = settings.whisper_model_size
        self.language = settings.whisper_language
        self.chunk_duration = settings.chunk_duration_seconds
        self._model: faster_whisper.WhisperModel | None = None

    @property
    def model(self) -> faster_whisper.WhisperModel:
        if self._model is None:
            logger.info("Loading Whisper model '%s'...", self.model_size)
            self._model = faster_whisper.WhisperModel(
                self.model_size,
                device="auto",
                compute_type="auto",
            )
            logger.info("Model loaded successfully.")
        return self._model

    def get_audio_metadata(self, file_path: Path) -> AudioMetadata:
        """Extract metadata from an audio file."""
        audio = AudioSegment.from_file(str(file_path))
        return AudioMetadata(
            file_path=file_path,
            duration_seconds=len(audio) / 1000.0,
            sample_rate=audio.frame_rate,
            channels=audio.channels,
            file_size_mb=file_path.stat().st_size / (1024 * 1024),
        )

    def _split_audio(self, file_path: Path) -> list[Path]:
        """Split a long audio file into chunks for processing."""
        audio = AudioSegment.from_file(str(file_path))
        duration_ms = len(audio)
        chunk_ms = self.chunk_duration * 1000

        if duration_ms <= chunk_ms:
            return [file_path]

        chunks_dir = file_path.parent / f".chunks_{file_path.stem}"
        chunks_dir.mkdir(exist_ok=True)

        chunk_paths: list[Path] = []
        for i, start in enumerate(range(0, duration_ms, chunk_ms)):
            end = min(start + chunk_ms, duration_ms)
            chunk = audio[start:end]
            chunk_path = chunks_dir / f"chunk_{i:04d}.wav"
            chunk.export(str(chunk_path), format="wav")
            chunk_paths.append(chunk_path)
            logger.info(
                "Chunk %d: %.1fs - %.1fs",
                i,
                start / 1000,
                end / 1000,
            )

        return chunk_paths

    def _cleanup_chunks(self, file_path: Path) -> None:
        """Remove temporary chunk files."""
        chunks_dir = file_path.parent / f".chunks_{file_path.stem}"
        if chunks_dir.exists():
            import shutil
            shutil.rmtree(chunks_dir)
            logger.info("Cleaned up temporary chunks.")

    def transcribe(self, file_path: Path) -> TranscriptionResult:
        """
        Transcribe an audio file. Automatically splits long files into chunks.

        Args:
            file_path: Path to the audio file.

        Returns:
            TranscriptionResult with segments and full text.
        """
        file_path = Path(file_path)
        metadata = self.get_audio_metadata(file_path)
        logger.info(
            "Starting transcription of '%s' (duration: %s)",
            file_path.name,
            metadata.duration_formatted,
        )

        chunk_paths = self._split_audio(file_path)
        all_segments: list[TranscriptionSegment] = []
        time_offset = 0.0
        segment_id = 0

        for chunk_idx, chunk_path in enumerate(chunk_paths):
            logger.info(
                "Transcribing chunk %d/%d ...",
                chunk_idx + 1,
                len(chunk_paths),
            )

            segments, info = self.model.transcribe(
                str(chunk_path),
                language=self.language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=400,
                ),
            )

            for seg in segments:
                ts = TranscriptionSegment(
                    id=segment_id,
                    start=seg.start + time_offset,
                    end=seg.end + time_offset,
                    text=seg.text,
                )
                all_segments.append(ts)
                segment_id += 1

            if chunk_path != file_path:
                audio_chunk = AudioSegment.from_file(str(chunk_path))
                time_offset += len(audio_chunk) / 1000.0

        self._cleanup_chunks(file_path)

        full_text = " ".join(seg.text.strip() for seg in all_segments)

        result = TranscriptionResult(
            audio_file=file_path.name,
            language=self.language,
            duration_seconds=metadata.duration_seconds,
            segments=all_segments,
            full_text=full_text,
            model_used=self.model_size,
        )

        logger.info(
            "Transcription complete: %d segments, %d characters.",
            result.segment_count,
            len(full_text),
        )
        return result

    def save_transcription(self, result: TranscriptionResult) -> dict[str, Path]:
        """
        Save transcription to multiple formats.

        Returns:
            Dictionary with format names as keys and file paths as values.
        """
        settings.ensure_dirs()
        stem = Path(result.audio_file).stem
        saved: dict[str, Path] = {}

        # JSON (complete data)
        json_path = settings.transcriptions_dir / f"{stem}_transcription.json"
        json_path.write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )
        saved["json"] = json_path

        # Plain text
        txt_path = settings.transcriptions_dir / f"{stem}_transcription.txt"
        txt_path.write_text(result.to_plain_text(), encoding="utf-8")
        saved["txt"] = txt_path

        # SRT subtitles
        srt_path = settings.transcriptions_dir / f"{stem}_transcription.srt"
        srt_path.write_text(result.to_srt(), encoding="utf-8")
        saved["srt"] = srt_path

        logger.info("Transcription saved to: %s", list(saved.values()))
        return saved
