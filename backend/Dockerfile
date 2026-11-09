# Small production image. The same image runs the API and the queue worker:
#   API:    the default command
#   worker: python -m app.worker
FROM python:3.12-slim

# uv from PyPI rather than ghcr.io, so the image also builds on IPv6-only hosts.
RUN pip install --no-cache-dir "uv==0.13.*"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8080 \
    DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

RUN useradd --create-home appuser && mkdir -p /data && chown appuser /data
USER appuser

EXPOSE 8080
CMD ["sh", "-c", "/app/.venv/bin/uvicorn --factory app.main:create_app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
