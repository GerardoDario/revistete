from pathlib import Path
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AudioMetadata(BaseModel):
    """Metadata extracted from an audio file."""

    file_path: Path
    file_name: str = ""
    duration_seconds: float = Field(..., gt=0, description="Duration in seconds")
    sample_rate: int = Field(default=16000, description="Sample rate in Hz")
    channels: int = Field(default=1, ge=1)
    file_size_mb: float = Field(default=0.0, ge=0)
    created_at: datetime = Field(default_factory=datetime.now)

    @field_validator("file_path")
    @classmethod
    def validate_file_exists(cls, v: Path) -> Path:
        if not v.exists():
            raise ValueError(f"Audio file not found: {v}")
        return v

    def model_post_init(self, __context) -> None:
        if not self.file_name:
            self.file_name = self.file_path.stem

    @property
    def duration_formatted(self) -> str:
        hours = int(self.duration_seconds // 3600)
        minutes = int((self.duration_seconds % 3600) // 60)
        seconds = int(self.duration_seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
