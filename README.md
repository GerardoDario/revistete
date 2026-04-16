# Revístete - Speech to Text & Sales Analyzer

Herramienta para transcribir grabaciones de voz largas (~2 horas) y generar resúmenes de ventas automáticos.

## Características

- **Transcripción de audio largo**: Divide automáticamente grabaciones largas en chunks para procesamiento eficiente
- **Múltiples formatos de salida**: JSON, texto plano y subtítulos SRT
- **Análisis de ventas con IA**: Extrae productos vendidos, cantidades y precios usando GPT-4o-mini
- **Modelos Pydantic**: Validación estricta de datos en toda la pipeline
- **Configurable**: Variables de entorno para modelo Whisper, idioma, duración de chunks, etc.

## Requisitos previos

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/download.html) (requerido por `pydub` para procesar audio)
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes recomendado)

## Instalación

### 1. Instalar uv (una sola vez)

```powershell
# Windows (PowerShell)
winget install astral-sh.uv

# o con pip
pip install uv
```

### 2. Instalar FFmpeg (una sola vez)

```powershell
# Windows (winget)
winget install Gyan.FFmpeg

# o con Chocolatey
choco install ffmpeg
```

### 3. Configurar el proyecto

```bash
# Clonar el repositorio
git clone <repo-url>
cd Revistete

# Crear entorno virtual e instalar dependencias (todo en uno)
uv sync

# Activar el entorno virtual
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Configurar variables de entorno
copy .env.example .env
# Editar .env con tu OPENAI_API_KEY
```

## Uso

```bash
# Transcribir y generar resumen de ventas
python -m src.main audio/grabacion.mp3

# Solo transcribir (sin resumen)
python -m src.main audio/grabacion.wav --skip-summary

# Con logging detallado
python -m src.main audio/grabacion.m4a --verbose
```

## Estructura del proyecto

```
Revistete/
├── src/
│   ├── models/          # Modelos Pydantic
│   │   ├── audio.py         # AudioMetadata
│   │   ├── transcription.py # TranscriptionSegment, TranscriptionResult
│   │   └── summary.py       # SaleItem, SalesSummary
│   ├── services/        # Lógica de negocio
│   │   ├── transcriber.py   # Transcripción con faster-whisper
│   │   └── summarizer.py    # Resumen con OpenAI
│   ├── config.py        # Settings (pydantic-settings)
│   └── main.py          # Entry point CLI
├── audio/               # Archivos de audio (gitignored)
├── output/
│   ├── transcriptions/  # Transcripciones generadas
│   └── summaries/       # Resúmenes de ventas
├── .env.example
├── requirements.txt
└── README.md
```

## Archivos de salida

### Transcripción
- `output/transcriptions/{nombre}_transcription.json` — Datos completos con segmentos y timestamps
- `output/transcriptions/{nombre}_transcription.txt` — Texto plano
- `output/transcriptions/{nombre}_transcription.srt` — Subtítulos SRT

### Resumen de ventas
- `output/summaries/{nombre}_summary.json` — Datos estructurados de ventas
- `output/summaries/{nombre}_summary.txt` — Reporte legible

## Configuración

| Variable | Descripción | Default |
|---|---|---|
| `OPENAI_API_KEY` | API Key de OpenAI (requerida para resumen) | — |
| `WHISPER_MODEL_SIZE` | Tamaño del modelo Whisper | `medium` |
| `WHISPER_LANGUAGE` | Idioma de transcripción | `es` |
| `CHUNK_DURATION_SECONDS` | Duración de cada chunk (segundos) | `1800` |
| `TRANSCRIPTIONS_DIR` | Directorio de transcripciones | `output/transcriptions` |
| `SUMMARIES_DIR` | Directorio de resúmenes | `output/summaries` |

## Modelos Whisper disponibles

| Modelo | VRAM | Velocidad | Precisión |
|---|---|---|---|
| `tiny` | ~1 GB | Muy rápido | Baja |
| `base` | ~1 GB | Rápido | Media-baja |
| `small` | ~2 GB | Medio | Media |
| `medium` | ~5 GB | Lento | Alta |
| `large-v3` | ~10 GB | Muy lento | Muy alta |
