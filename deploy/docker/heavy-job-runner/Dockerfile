# Multi-stage build for Heavy Job Runner Docker image
# This image includes data processing libraries for resource-intensive workloads

# Stage 1: Builder stage
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy package files
COPY pyproject.toml /tmp/
COPY src /tmp/src/
COPY README.md /tmp/
COPY LICENSE /tmp/
COPY MANIFEST.in /tmp/

WORKDIR /tmp

# Install the package with job-runner dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e ".[job-runner]"

# Stage 2: Runtime stage
FROM python:3.11-slim

# Add labels for version and component identification
LABEL maintainer="LLM Python Executor Team"
LABEL component="heavy-job-runner"
LABEL version="0.1.0"
LABEL description="Heavy Job Runner for resource-intensive Python code execution"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (UID 1000) for security
RUN groupadd -g 1000 jobrunner && \
    useradd -r -u 1000 -g jobrunner -m -s /bin/bash jobrunner

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy source code
COPY --chown=jobrunner:jobrunner src /app/src
COPY --chown=jobrunner:jobrunner pyproject.toml /app/
COPY --chown=jobrunner:jobrunner README.md /app/
COPY --chown=jobrunner:jobrunner LICENSE /app/
COPY --chown=jobrunner:jobrunner MANIFEST.in /app/

# Set working directory
WORKDIR /app

# Set PATH to use virtual environment
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Create temporary directory with proper permissions
RUN mkdir -p /tmp/heavy_job && chown -R jobrunner:jobrunner /tmp/heavy_job

# Switch to non-root user
USER jobrunner

# Set entrypoint to run the job runner
ENTRYPOINT ["python", "-m", "llm_executor.job_runner.runner"]

# Health check (optional - for debugging)
# The job runner is ephemeral, so health checks are not typically needed
# But we can verify the Python environment is working
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=1 \
    CMD python -c "import sys; sys.exit(0)"
