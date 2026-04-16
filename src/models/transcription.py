from datetime import datetime

from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    """A single segment of a transcription with timestamps."""

    id: int = Field(..., ge=0)
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., ge=0, description="End time in seconds")
    text: str

    @property
    def start_formatted(self) -> str:
        return self._format_time(self.start)

    @property
    def end_formatted(self) -> str:
        return self._format_time(self.end)

    @staticmethod
    def _format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


class TranscriptionResult(BaseModel):
    """Complete transcription result for an audio file."""

    audio_file: str
    language: str = "es"
    duration_seconds: float = Field(..., ge=0)
    segments: list[TranscriptionSegment] = Field(default_factory=list)
    full_text: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    model_used: str = "medium"

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def to_srt(self) -> str:
        """Export transcription as SRT subtitle format."""
        lines = []
        for seg in self.segments:
            lines.append(str(seg.id + 1))
            lines.append(f"{seg.start_formatted} --> {seg.end_formatted}")
            lines.append(seg.text.strip())
            lines.append("")
        return "\n".join(lines)

    def to_plain_text(self) -> str:
        """Export transcription as plain text."""
        return self.full_text if self.full_text else " ".join(
            seg.text.strip() for seg in self.segments
        )
