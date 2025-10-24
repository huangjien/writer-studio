# Dockerfile for Writer Studio Novel Eval API
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy minimal files first for layer caching
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY tasks /app/tasks
COPY uv.lock /app/uv.lock

# Install project and runtime dependencies
# Include autogen and provider clients (openai, mcp, ollama) and sqlite-vec
RUN pip install --no-cache-dir . && \
    pip install --no-cache-dir "autogen-agentchat==0.7.5" "autogen-ext[openai,mcp,ollama]==0.7.5" "sqlite-vec==0.1.6"

EXPOSE 8000

# Data directory for SQLite persistence
RUN mkdir -p /data
VOLUME ["/data"]

ENV NOVEL_EVAL_LOG_LEVEL=INFO \
    NOVEL_EVAL_PROVIDER=openai \
    NOVEL_EVAL_MODEL=gpt-4o-mini \
    NOVEL_EVAL_LANG=zh-CN \
    NOVEL_EVAL_DB_PATH=/data/evals.db

CMD ["uvicorn", "writer_studio.api.server:app", "--host", "0.0.0.0", "--port", "8000"]