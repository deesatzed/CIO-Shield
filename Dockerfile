FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[dev]"

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

CMD ["python", "-m", "cognitiveio.cli", "run", "--mode", "headless"]
