from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = ""

    # Whisper
    whisper_model_size: str = "medium"
    whisper_language: str = "es"

    # Processing
    chunk_duration_seconds: int = 1800  # 30 minutes

    # Paths
    transcriptions_dir: Path = Path("output/transcriptions")
    summaries_dir: Path = Path("output/summaries")

    # Gmail IMAP
    gmail_address: str = ""
    gmail_app_password: str = ""

    # TITO
    payment_tolerance: float = 500.0
    tito_db_path: Path = Path("tito.db")

    def ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        self.transcriptions_dir.mkdir(parents=True, exist_ok=True)
        self.summaries_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
