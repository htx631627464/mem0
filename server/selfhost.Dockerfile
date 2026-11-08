# Self-hosted image with the in-repo mem0 SDK baked in.
#
# Unlike dev.Dockerfile (PyPI mem0ai + bind-mounted source), this image installs
# the repository's mem0/ package — including the customized Chinese extraction
# prompts (mem0/configs/prompts.py) — so no runtime pip install or
# /mem0-patches overlay is needed at container start.
#
# Build context: repository root (docker-compose uses context: ..).

FROM python:3.12-slim

# Allow CI/deployments behind slow networks to point pip at a mirror,
# e.g. --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

# 1) Server dependencies first (stable layer).
COPY server/requirements.txt /tmp/server-requirements.txt
RUN pip install -r /tmp/server-requirements.txt

# 2) The in-repo mem0 SDK source. Install with --no-deps: its runtime deps
#    (openai, sqlalchemy, pytz, ...) are already covered by the layers above,
#    and we want the SDK version to come from this checkout, not from PyPI.
COPY pyproject.toml README.md /tmp/mem0-pkg/
COPY mem0 /tmp/mem0-pkg/mem0
RUN pip install --no-deps /tmp/mem0-pkg && rm -rf /tmp/mem0-pkg

# 3) Server code.
COPY server /app/server
WORKDIR /app/server

# history dir is bind-mounted at runtime; the default config writes
# /app/history/history.db (see server/config_builder.py).
RUN mkdir -p /app/history

EXPOSE 8000

# Apply pending DB migrations for the app database, then serve.
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
