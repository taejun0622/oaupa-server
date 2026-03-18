FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY app/__init__.py app/__init__.py
RUN pip install --no-cache-dir .

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/
COPY scripts/ scripts/

ENV PORT=8000
EXPOSE ${PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
