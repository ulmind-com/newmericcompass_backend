# Newmeric Compass backend -- FastAPI + MongoDB, managed with uv.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App source
COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Most PaaS providers inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
