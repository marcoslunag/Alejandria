FROM python:3.11-slim

LABEL maintainer="Alejandria" \
      description="Alejandria Backend API - Tu biblioteca digital"

# Set working directory
WORKDIR /app

# Install system dependencies including Playwright browser dependencies
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

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps mega.py==1.0.8 bypass-ouo==0.1.1

# Install Playwright browsers to a fixed path (not ~/; accessible to all users)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# Copy application code
COPY . .

# Make scripts executable
RUN chmod +x start.sh entrypoint.sh

# Install gosu for privilege de-escalation in entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create non-root user and set up directories with correct ownership
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser && \
    mkdir -p /downloads /library /library/kindle /imports /stk-data /app/data && \
    chown -R appuser:appuser /downloads /library /imports /stk-data /app /app/data /ms-playwright

# Expose port
EXPOSE 7878

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7878/health || exit 1

# Entrypoint fixes volume permissions then drops to appuser
ENTRYPOINT ["bash", "entrypoint.sh"]
