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
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (only Chromium to save space)
RUN playwright install chromium

# Copy application code
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Create necessary directories
RUN mkdir -p /downloads /manga /manga/kindle

# Expose port
EXPOSE 7878

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7878/health || exit 1

# Run application with start script (handles migrations)
CMD ["./start.sh"]
