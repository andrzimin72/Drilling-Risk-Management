# =============================================================================
# Oil & Gas Risk Management System — Dockerfile
# Version: 2.0.0 (Enterprise Edition)
# =============================================================================
# Build:
#   docker build -t oil-gas-swarm:2.0.0 .
#
# Run (Dashboard only):
#   docker run -d -p 8501:8501 \
#     --env-file .env \
#     -v $(pwd)/.cache:/app/.cache \
#     --name oil-gas-swarm \
#     oil-gas-swarm:2.0.0
#
# Run (Dashboard + MCP Server):
#   docker run -d -p 8501:8501 -p 8342:8342 \
#     --env-file .env \
#     -v $(pwd)/.cache:/app/.cache \
#     --name oil-gas-swarm \
#     oil-gas-swarm:2.0.0
#
# Run with Docker Compose (recommended):
#   docker-compose up -d
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Base image with system dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies required for:
# - weasyprint (PDF export): libpango, libcairo, libgdk-pixbuf, libffi
# - pdfplumber: libjpeg, zlib
# - dlisio: build tools
# - General: git (for some dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PDF rendering libraries (for weasyprint)
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    libcairo2-dev \
    # Image processing (for pdfplumber, pypdfium2)
    libjpeg-dev \
    zlib1g-dev \
    # Build tools (for compiling Python extensions)
    build-essential \
    gcc \
    g++ \
    # Utilities
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Stage 2: Install Python dependencies
# ---------------------------------------------------------------------------
FROM base AS dependencies

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install optional PDF export backends
RUN pip install --no-cache-dir \
    weasyprint>=60.0 \
    fpdf2>=2.7.0

# ---------------------------------------------------------------------------
# Stage 3: Production image
# ---------------------------------------------------------------------------
FROM dependencies AS production

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy application code
COPY . .

# Create cache directory with proper permissions
RUN mkdir -p /app/.cache && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose ports
# 8501 — Streamlit Dashboard
# 8342 — MCP Server (Model Context Protocol)
EXPOSE 8501 8342

# Health check — verify Streamlit is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Set environment variables
ENV PYTHONPATH=/app \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Default command: run Streamlit dashboard
CMD ["streamlit", "run", "dashboard.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]

# ---------------------------------------------------------------------------
# Alternative entrypoints (uncomment to use):
# ---------------------------------------------------------------------------

# Run MCP Server instead of Dashboard:
# CMD ["python", "-m", "swarms.server"]

# Run tests:
# CMD ["pytest", "tests/", "-v", "--cov=skills", "--cov=swarms"]

# Run demo:
# CMD ["python", "-m", "swarms.demo"]

# Interactive shell (for debugging):
# CMD ["/bin/bash"]