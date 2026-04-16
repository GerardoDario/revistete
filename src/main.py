import argparse
import logging
import sys
from pathlib import Path

from src.config import settings
from src.services.transcriber import TranscriberService
from src.services.summarizer import SummarizerService


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run_pipeline(audio_path: Path, skip_summary: bool = False) -> None:
    """Run the full transcription + summarization pipeline."""
    settings.ensure_dirs()

    # --- Transcription ---
    transcriber = TranscriberService()
    metadata = transcriber.get_audio_metadata(audio_path)

    print(f"\n{'='*60}")
    print(f"  Audio: {metadata.file_name}")
    print(f"  Duration: {metadata.duration_formatted}")
    print(f"  Size: {metadata.file_size_mb:.1f} MB")
    print(f"  Model: {settings.whisper_model_size}")
    print(f"{'='*60}\n")

    transcription = transcriber.transcribe(audio_path)
    saved_transcription = transcriber.save_transcription(transcription)

    print(f"\nTranscription saved:")
    for fmt, path in saved_transcription.items():
        print(f"  [{fmt}] {path}")

    # --- Summary ---
    if skip_summary:
        print("\nSummary skipped (--skip-summary).")
        return

    if not settings.openai_api_key:
        print("\nWarning: OPENAI_API_KEY not set. Skipping summary.")
        print("Set it in your .env file to generate sales summaries.")
        return

    summarizer = SummarizerService()
    summary = summarizer.summarize(transcription)
    saved_summary = summarizer.save_summary(summary)

    print(f"\nSummary saved:")
    for fmt, path in saved_summary.items():
        print(f"  [{fmt}] {path}")

    print(f"\n{summary.to_report()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Revístete - Speech to Text & Sales Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main audio/recording.mp3
  python -m src.main audio/recording.wav --skip-summary
  python -m src.main audio/recording.m4a --verbose
        """,
    )
    parser.add_argument(
        "audio",
        type=Path,
        help="Path to the audio file to transcribe",
    )
    parser.add_argument(
        "--skip-summary",
        action="store_true",
        help="Only transcribe, skip the sales summary",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.audio.exists():
        print(f"Error: File not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    run_pipeline(args.audio, skip_summary=args.skip_summary)


if __name__ == "__main__":
    main()
