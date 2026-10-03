FROM python:3.11-slim

WORKDIR /app

# Minimal system deps (no browser, no Playwright) — fits basic 512MB/1GB VPS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

ENV TIMEZONE=Asia/Kolkata

USER appuser

CMD ["python", "main.py"]
