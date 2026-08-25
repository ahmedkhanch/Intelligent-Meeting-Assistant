# CRM Vocal — dev image (shared by the backend and tools services).
# FastAPI + the CLI scripts/tests. ffmpeg + edge-tts are bundled so
# scripts/generate_meeting_audio.py works inside the container.

FROM python:3.13-slim

WORKDIR /app

# System deps: ffmpeg (audio generation/stitching) + curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps: core app + dev/tools extras
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir edge-tts pydub

# App source is bind-mounted at runtime (dev hot reload), so nothing is COPY'd here.

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
