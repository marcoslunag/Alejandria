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

# Instalar KindleGen (necesario para MOBI)
RUN cd /tmp && \
    wget -q https://archive.org/download/kindlegen_linux_2_6_i386_v2_9/kindlegen_linux_2.6_i386_v2_9.tar.gz && \
    tar -xzf kindlegen_linux_2.6_i386_v2_9.tar.gz && \
    mv kindlegen /usr/local/bin/ && \
    chmod +x /usr/local/bin/kindlegen && \
    rm -rf kindlegen* docs EULA.txt

# Verificar instalación
RUN which 7z && which unrar && which ebook-convert && which kindlegen

# Instalar dependencias Python
RUN pip install --no-cache-dir \
    packaging \
    git+https://github.com/ciromattia/kcc.git \
    watchdog \
    python-dotenv \
    Pillow

# Crear directorios necesarios
RUN mkdir -p /downloads /manga/kindle && chmod 777 /downloads /manga/kindle

# Copiar script
COPY converter.py .

# Variables de entorno por defecto
ENV WATCH_DIR=/downloads
ENV OUTPUT_DIR=/manga/kindle
ENV KCC_PROFILE=KPW5
ENV KCC_FORMAT=MOBI
ENV KCC_QUALITY=95
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "converter.py"]