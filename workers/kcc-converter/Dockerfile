FROM python:3.11-slim-bookworm

LABEL maintainer="Alejandria" \
      description="Alejandria KCC Converter Worker"

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libjpeg62-turbo-dev \
    libpng-dev \
    zlib1g-dev \
    libpoppler-cpp-dev \
    libgl1 \
    libglib2.0-0 \
    p7zip-full \
    wget \
    calibre \
    gcc \
    g++ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Instalar unrar oficial (descarga estática)
RUN cd /tmp && \
    wget https://www.rarlab.com/rar/rarlinux-x64-612.tar.gz && \
    tar -xzf rarlinux-x64-612.tar.gz && \
    cp rar/unrar /usr/local/bin/ && \
    chmod +x /usr/local/bin/unrar && \
    rm -rf rar*

# Verificar instalación
RUN which 7z && which unrar && which ebook-convert

# Instalar dependencias Python
RUN pip install --no-cache-dir \
    packaging \
    git+https://github.com/ciromattia/kcc.git \
    watchdog \
    python-dotenv \
    Pillow

# Crear directorios y usuario no-root
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser && \
    mkdir -p /downloads /library/kindle && \
    chown -R appuser:appuser /downloads /library /app

# Copiar script (como root todavía para que COPY funcione, luego chown)
COPY converter.py .
RUN chown appuser:appuser /app/converter.py

USER appuser

# Variables de entorno por defecto
ENV WATCH_DIR=/downloads
ENV OUTPUT_DIR=/library/kindle
ENV KCC_PROFILE=KPW5
ENV KCC_FORMAT=EPUB
ENV KCC_QUALITY=95
ENV PYTHONUNBUFFERED=1

# Health check: verificar que el proceso converter sigue activo
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f "converter.py" > /dev/null || exit 1

CMD ["python", "-u", "converter.py"]