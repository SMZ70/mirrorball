# ── Stage 1: dependency installer ────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Cache-friendly: deps before source, so a code edit does not re-resolve them
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY mmdj/ ./mmdj/
RUN uv sync --frozen --no-dev

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

WORKDIR /app

# openssl is not an optimisation here, it is the DTLS stack: mmdj streams to the
# bridge by piping frames through `openssl s_client`. Without this binary the
# panel loads and ▶ fails. See mmdj/drivers/dtls.py for why it is not a library.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/mmdj /app/mmdj
COPY web/ /app/web/

RUN useradd -m -u 1000 mmdj && chown -R mmdj /app
USER mmdj

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MMDJ_HOST=0.0.0.0 \
    MMDJ_PORT=8090

EXPOSE 8090

# bridge.json (credentials) and shows/ (saved shows) are mounted in, never baked:
# the image stays free of anything specific to this house, and the repo stays
# publishable.
ENTRYPOINT ["python", "-m", "mmdj"]
