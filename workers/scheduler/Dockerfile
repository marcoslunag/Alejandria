FROM python:3.11-slim

LABEL maintainer="Alejandria" \
      description="Alejandria Scheduler Worker - Background task automation"

WORKDIR /app

# Install system dependencies (same as backend - needed for scrapers/downloaders)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    postgresql-client \
    curl \
    megatools \
    # Playwright/Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy backend requirements and install
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend/requirements.txt && \
    pip install --no-cache-dir --no-deps mega.py==1.0.8

# Install Playwright browsers to a fixed path (accessible to all users)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# Copy backend code (shared models, services, config)
COPY backend/ /app/backend/

# Copy scheduler worker
COPY workers/scheduler/ /app/workers/scheduler/

# Create non-root user and set up directories
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser && \
    mkdir -p /downloads /library /library/kindle && \
    chown -R appuser:appuser /downloads /library /app /ms-playwright

USER appuser

# Health check: verify the scheduler process is running
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f "scheduler/main.py" > /dev/null || exit 1

CMD ["python", "/app/workers/scheduler/main.py"]
