# Backend Dockerfile (FastAPI + bot)
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Install deps first (layer caching)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy code
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Default: run FastAPI. Bot uses a different command.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
