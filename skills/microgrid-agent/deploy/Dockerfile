# =============================================================================
# Microgrid Agent — Docker image for CI/simulation (not for RPi deployment)
# =============================================================================
# This Dockerfile runs the agent in simulation mode for testing purposes.
# For Raspberry Pi deployment, use scripts/install.sh instead.
#
# Build:
#   docker build -t microgrid-agent -f deploy/Dockerfile .
#
# Run:
#   docker run --rm -it microgrid-agent
#   docker run --rm -it -v $(pwd)/config/site.toml:/app/config/site.toml microgrid-agent
# =============================================================================

FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        libmodbus-dev \
        sqlite3 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specification first for caching
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
        pymodbus>=3.5 \
        paho-mqtt>=2.0 \
        scipy>=1.11 \
        toml>=0.10 \
        aiosqlite>=0.19 \
        aiohttp>=3.9 \
        openpyxl>=3.1

# Copy application source
COPY src/ ./src/
COPY config/ ./config/
COPY schema/ ./schema/
COPY main.py ./main.py

# Create data directories
RUN mkdir -p /app/data/db /app/data/models /app/data/sync-queue /app/data/logs

# Initialize the knowledge graph database
RUN sqlite3 /app/data/db/knowledge.db < /app/schema/knowledge-graph.sql

# Environment defaults
ENV MICROGRID_CONFIG_DIR=/app/config
ENV MICROGRID_DATA_DIR=/app/data
ENV MICROGRID_LOG_LEVEL=DEBUG
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

EXPOSE 8080

ENTRYPOINT ["python", "main.py", "--config", "config/site.example.toml", "--simulate"]
