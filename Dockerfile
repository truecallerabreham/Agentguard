# =============================================================================
# STAGE 1: Build & Dependencies
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create isolated virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install package dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Copy and install AgentGuard package
COPY src/ ./src/
RUN pip install --no-cache-dir .

# =============================================================================
# STAGE 2: Hardened Production Runtime
# =============================================================================
FROM python:3.11-slim-bookworm AS runtime

# Security: Install only curl for health checks, remove package lists
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root system user (UID 10001)
RUN groupadd -g 10001 agentguard && \
    useradd -u 10001 -g agentguard -m -s /bin/sh agentguard

# Copy virtualenv from builder stage
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    AGENTGUARD_TRANSPORT="http" \
    AGENTGUARD_HTTP_HOST="0.0.0.0" \
    AGENTGUARD_HTTP_PORT="8080"

# Application directory
WORKDIR /app

# Copy application configuration and source code with proper ownership
COPY --chown=agentguard:agentguard config/ ./config/
COPY --chown=agentguard:agentguard src/ ./src/

# Create logs directory owned by non-root user
RUN mkdir -p /app/logs && chown -R agentguard:agentguard /app/logs

# Switch to unprivileged non-root user
USER agentguard

# Expose HTTP / SSE transport port
EXPOSE 8080

# Health check probe against /healthz
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Default command launches the authenticated MCP server
ENTRYPOINT ["python", "-m", "agentguard.server"]
