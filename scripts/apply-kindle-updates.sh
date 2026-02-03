#!/bin/bash
echo "===================================="
echo "Aplicando actualizaciones de Kindle"
echo "===================================="

cd "$(dirname "$0")/.."

echo ""
echo "[1/4] Aplicando migracion de base de datos..."
docker exec -i alejandria-db psql -U manga -d alejandria -c "ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS kcc_profile VARCHAR(20) DEFAULT 'KPW5';"

echo ""
echo "[2/4] Reconstruyendo backend..."
docker-compose build backend

echo ""
echo "[3/4] Reconstruyendo kcc-converter..."
docker-compose build kcc-converter

echo ""
echo "[4/4] Reiniciando servicios..."
docker-compose up -d backend kcc-converter

echo ""
echo "===================================="
echo "Actualizaciones aplicadas!"
echo "===================================="
echo ""
echo "Cambios realizados:"
echo "- Sistema de lock files para sincronizacion de descargas"
echo "- Division automatica de archivos grandes (max 180MB por parte)"
echo "- Selector de modelo Kindle en Settings"
echo "- Seccion de Estado de Kindle en Settings"
echo "- Formato EPUB optimizado para STK (Send to Kindle)"
echo ""
