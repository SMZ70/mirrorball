# ── Stage 1: dependency installer ────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Cache-friendly: deps before source, so a code edit does not re-resolve them
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY mirrorball/ ./mirrorball/
RUN uv sync --frozen --no-dev

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

WORKDIR /app

# openssl is not an optimisation here, it is the DTLS stack: mirrorball streams to the
# bridge by piping frames through `openssl s_client`. Without this binary the
# panel loads and ▶ fails. See mirrorball/drivers/dtls.py for why it is not a library.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/mirrorball /app/mirrorball
COPY web/ /app/web/

RUN useradd -m -u 1000 mirrorball && chown -R mirrorball /app
USER mirrorball

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MIRRORBALL_HOST=0.0.0.0 \
    MIRRORBALL_PORT=8090

EXPOSE 8090

# bridge.json (credentials) and shows/ (saved shows) are mounted in, never baked:
# the image stays free of anything installation-specific, and the repo stays
# publishable.
ENTRYPOINT ["python", "-m", "mirrorball"]
