# syntax=docker/dockerfile:1
# Multi-stage build. Default image installs the runtime (no heavy ML); set INSTALL_ML=true to
# bake in PyMuPDF/OpenCV/PaddleOCR/OpenCLIP for the production worker backends.
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
# libGL/glib are needed by opencv even in headless builds; curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
ARG INSTALL_ML=false
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && \
    if [ "$INSTALL_ML" = "true" ]; then pip install ".[ml]"; else pip install "."; fi

FROM base AS runtime
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
# Run as non-root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
# Default command runs the API; compose overrides for the worker and migrate jobs.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
