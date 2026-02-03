# Alejandria

<div align="center">

**Tu biblioteca digital personal para manga, cómics y libros**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://reactjs.org/)

[Características](#-características) • [Instalación](#-instalación) • [Configuración](#-configuración) • [Uso](#-uso) • [API](#-api) • [Roadmap](#-roadmap)

</div>

---

## Descripción

**Alejandria** es una plataforma de gestión de biblioteca digital diseñada para manga, cómics y libros. Inspirada en herramientas como Radarr/Sonarr y Kaizoku, ofrece descarga automatizada, conversión a formatos Kindle y envío directo a tus dispositivos.

### ¿Por qué Alejandria?

- **Todo en uno**: Descarga, convierte y envía a tu Kindle automáticamente
- **Múltiples fuentes**: Soporte para TomosManga, MangaYComics y más
- **Integración AniList**: Busca y añade mangas directamente desde AniList
- **Archivos grandes**: Soporte para archivos >25MB usando STK (Send to Kindle API)
- **Auto-división**: Divide automáticamente tomos grandes en partes para cumplir límites
- **Interfaz moderna**: UI inspirada en Kaizoku con diseño oscuro y responsivo

---

## Características

### Biblioteca
- Gestión de biblioteca de manga/cómics
- Búsqueda en múltiples fuentes (TomosManga, MangaYComics, AniList)
- Metadatos automáticos desde AniList (portadas, sinopsis, autores)
- Estado de seguimiento por tomo (pendiente, descargado, convertido, enviado)

### Descargas
- Cola de descargas con prioridades
- Descargas concurrentes configurables
- Soporte para múltiples hosts (TeraBox, MediaFire, etc.)
- Reintentos automáticos en caso de error
- Cancelación de descargas en progreso

### Conversión
- Conversión automática a EPUB usando KCC (Kindle Comic Converter)
- División automática de tomos grandes (>200MB)
- Perfiles optimizados para diferentes Kindles (KPW5, KO, K11, etc.)
- Metadatos ComicInfo.xml embebidos

### Kindle
- **STK (Send to Kindle API)**: Envío directo con autenticación OAuth2
- Soporte para archivos hasta 200MB
- Soporte multi-dispositivo
- División automática de envíos por partes

### Automatización
- Verificación periódica de nuevos capítulos (configurable)
- Descarga automática de nuevos tomos
- Conversión automática al detectar nuevos archivos
- Envío automático al Kindle (opcional)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                         ALEJANDRIA                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Frontend   │    │   Backend    │    │  KCC Worker  │     │
│  │  (React UI)  │───▶│  (FastAPI)   │───▶│  (Converter) │     │
│  │   :8888      │    │    :9878     │    │              │     │
│  └──────────────┘    └──────┬───────┘    └──────────────┘     │
│                             │                    │              │
│                             ▼                    ▼              │
│                    ┌──────────────┐      ┌──────────────┐      │
│                    │  PostgreSQL  │      │   /manga     │      │
│                    │   Database   │      │   /kindle    │      │
│                    └──────────────┘      └──────────────┘      │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Scrapers   │    │ Downloaders  │    │ Kindle Send  │     │
│  │ TomosManga   │    │   TeraBox    │    │     STK      │     │
│  │ MangaYComics │    │  MediaFire   │    │   OAuth2     │     │
│  │   AniList    │    │   Generic    │    │              │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Instalación

### Requisitos del sistema

| Recurso | Mínimo | Recomendado |
|---------|--------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 2 GB | 4 GB |
| Disco | 20 GB | 100+ GB |
| SO | Linux (Docker) | Debian/Ubuntu |

**Software necesario:**
- Docker 20.10+
- Docker Compose v2+
- Git

**Cuentas opcionales:**
- Cuenta Amazon para STK (envío a Kindle)

---

### Instalación rápida (3 pasos)

```bash
# 1. Clonar repositorio
git clone https://github.com/tu-usuario/alejandria.git
cd alejandria

# 2. Configurar (edita .env con tus datos)
cp .env.example .env
nano .env

# 3. Iniciar
docker-compose up -d
```

**Acceso:**
- **Frontend**: http://tu-ip:8888
- **API Docs**: http://tu-ip:9878/docs

---

### Instalación en Proxmox LXC

#### Crear container LXC

```bash
# En el nodo Proxmox, crear container con plantilla Debian/Ubuntu
pct create 200 local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst \
  --hostname alejandria \
  --memory 4096 \
  --cores 4 \
  --rootfs local-lvm:32 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1 \
  --unprivileged 1

# Iniciar container
pct start 200

# Entrar al container
pct enter 200
```

> **Importante**: El flag `nesting=1` es necesario para Docker.

#### Instalar Docker en el LXC

```bash
# Actualizar sistema
apt update && apt upgrade -y

# Instalar dependencias
apt install -y ca-certificates curl gnupg git

# Añadir repositorio Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Instalar Docker
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verificar instalación
docker --version
docker compose version
```

#### Instalar Alejandria

```bash
# Clonar repositorio
cd /opt
git clone https://github.com/tu-usuario/alejandria.git
cd alejandria

# Configurar
cp .env.example .env
nano .env  # Editar con tus credenciales

# Construir e iniciar (primera vez tarda ~5-10 min)
docker compose up -d --build

# Ver logs
docker compose logs -f
```

#### Configurar inicio automático

```bash
# Crear servicio systemd
cat > /etc/systemd/system/alejandria.service << 'EOF'
[Unit]
Description=Alejandria - Tu biblioteca digital
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/alejandria
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Habilitar servicio
systemctl daemon-reload
systemctl enable alejandria
```

---

### Configuración del archivo .env

```env
# ============================================
# ALEJANDRIA - Configuración
# ============================================

# Base de datos (cambiar password en producción)
POSTGRES_USER=manga
POSTGRES_PASSWORD=tu-password-seguro
POSTGRES_DB=alejandria

# KCC - Conversión
KCC_PROFILE=KPW5    # Modelo Kindle: KPW5, KPW4, KO, K11, KS
KCC_FORMAT=EPUB     # EPUB (MOBI ya no soportado por Send to Kindle)

# Scheduler
CHECK_INTERVAL_HOURS=6

# Logging
LOG_LEVEL=INFO
```

---

## Configuración

### STK (Send to Kindle API)

El envío a Kindle se realiza mediante STK (Send to Kindle API) usando OAuth2 de Amazon.

1. En la interfaz web, ve a **Ajustes**
2. Click en "Conectar con Amazon"
3. Inicia sesión con tu cuenta Amazon
4. Copia la URL de redirección y pégala
5. Selecciona tu dispositivo Kindle preferido
6. Guarda la configuración

> **Nota**: STK soporta archivos hasta 200MB. Los archivos más grandes se dividen automáticamente.

### TeraBox (Descargas desde TeraBox)

Para descargar archivos desde TeraBox, necesitas configurar las cookies de tu cuenta:

1. **Crear cuenta en TeraBox** (si no tienes): https://www.terabox.com
2. **Obtener cookies**:
   - Instala una extensión de cookies en tu navegador (Cookie-Editor, etc.)
   - Inicia sesión en TeraBox
   - Exporta las cookies o cópialas desde DevTools (F12 > Application > Cookies)
3. **Configurar en `.env`**:

```env
# Formato: cookie1=valor1; cookie2=valor2; ...
TERABOX_COOKIE=ndus=TU_NDUS; browserid=TU_BROWSERID; csrfToken=TU_CSRF; lang=es; PANWEB=1
```

**Cookies importantes:**
| Cookie | Importancia |
|--------|-------------|
| `ndus` | **CRÍTICA** - Token de sesión |
| `browserid` | Alta |
| `csrfToken` | Media |

> **Nota**: El bypass usa el dominio alternativo `1024tera.com` para evitar la verificación de captcha.

### Perfiles KCC

| Perfil | Dispositivo |
|--------|-------------|
| KPW5 | Kindle Paperwhite 5 (2021) |
| KPW4 | Kindle Paperwhite 4 (2018) |
| KO | Kindle Oasis |
| K11 | Kindle 11 |
| KS | Kindle Scribe |

---

## Uso

### Añadir manga

1. **Desde búsqueda**: Busca en la barra superior, selecciona de AniList o TomosManga
2. **Desde URL**: Pega directamente la URL de TomosManga o MangaYComics
3. **Desde AniList**: Busca por nombre y se vincula automáticamente con las fuentes

### Descargar tomos

1. Ve a la página del manga
2. Selecciona los tomos que quieres descargar
3. Click en "Descargar seleccionados"
4. Monitorea el progreso en la Cola de Descargas

### Enviar a Kindle

- **Automático**: Configura envío automático en Configuración
- **Manual**: Click en el botón "Kindle" en cualquier tomo convertido

---

## API

### Endpoints principales

#### Manga
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/manga/` | Listar biblioteca |
| GET | `/api/v1/manga/search` | Buscar manga |
| POST | `/api/v1/manga/add/anilist` | Añadir desde AniList |
| POST | `/api/v1/manga/add/url` | Añadir desde URL |
| GET | `/api/v1/manga/{id}` | Detalles de manga |
| DELETE | `/api/v1/manga/{id}` | Eliminar manga |
| POST | `/api/v1/manga/{id}/refresh` | Actualizar capítulos |

#### Capítulos
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/manga/{id}/chapters` | Listar capítulos |
| POST | `/api/v1/manga/{id}/chapters/download` | Descargar capítulos |

#### Cola
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/queue/` | Ver cola de descargas |
| POST | `/api/v1/queue/{id}/cancel` | Cancelar descarga |
| POST | `/api/v1/queue/{id}/retry` | Reintentar descarga |
| DELETE | `/api/v1/queue/{id}/file` | Eliminar archivo |

#### Kindle (STK)
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/v1/kindle/stk/send/{id}` | Enviar a Kindle |
| GET | `/api/v1/kindle/stk/status` | Estado de autenticación |
| GET | `/api/v1/kindle/stk/devices` | Listar dispositivos |

Documentación completa en: http://localhost:9878/docs

---

## Estructura del Proyecto

```
alejandria/
├── backend/                    # API FastAPI
│   ├── app/
│   │   ├── api/v1/            # Endpoints REST
│   │   ├── models/            # Modelos SQLAlchemy
│   │   ├── schemas/           # Schemas Pydantic
│   │   ├── services/          # Lógica de negocio
│   │   │   ├── scraper.py     # Scraper genérico
│   │   │   ├── downloader.py  # Gestor de descargas
│   │   │   ├── scheduler.py   # Tareas programadas
│   │   │   └── stk_kindle_sender.py # Envío a Kindle via STK
│   │   └── main.py
│   └── Dockerfile
├── frontend/                   # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/        # Componentes reutilizables
│   │   ├── pages/             # Páginas principales
│   │   └── services/api.js    # Cliente API
│   └── Dockerfile
├── workers/
│   └── kcc-converter/         # Worker de conversión
│       ├── converter.py       # Lógica de conversión
│       └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Roadmap

### En desarrollo
- [ ] **Soporte para libros (EPUB/PDF)**
- [ ] **Soporte para cómics americanos**

### Planificado
- [ ] Notificaciones (Telegram, Discord, Email)
- [ ] Búsqueda en más fuentes (MangaDex, etc.)
- [ ] Importación masiva desde Calibre
- [ ] Estadísticas de lectura
- [ ] Sincronización con servicios de tracking (AniList, MAL)
- [ ] Modo offline / PWA
- [ ] Soporte multi-idioma

### Completado
- [x] Interfaz web moderna
- [x] Descarga automática desde TomosManga
- [x] Conversión a EPUB con KCC
- [x] Envío a Kindle via STK (hasta 200MB)
- [x] División automática de tomos grandes
- [x] Integración con AniList
- [x] Cola de descargas con cancelación
- [x] Soporte multi-dispositivo Kindle
- [x] **Bypass de TeraBox** via 1024tera.com

---

## Resolución de Problemas

### Error: "STK not authenticated"
Ve a Configuración > Kindle y completa la autenticación con Amazon.

### La conversión falla
1. Verifica que el worker KCC está corriendo: `docker-compose logs kcc-converter`
2. Comprueba que KindleGen está instalado en el worker

### Las descargas se quedan "downloading"
```bash
# Reiniciar descargas atascadas
curl -X POST http://localhost:9878/api/v1/queue/reset-stuck
```

### TeraBox: Error "errno 400141 - need verify"
Esto ocurre en el dominio principal de TeraBox. El bypass usa `1024tera.com` para evitarlo. Si persiste, las cookies han expirado - obtén nuevas.

### TeraBox: Las cookies expiraron
1. Vuelve a iniciar sesión en terabox.com
2. Exporta las nuevas cookies
3. Actualiza `TERABOX_COOKIE` en tu `.env`
4. Reinicia: `docker compose restart backend`

### Ver logs
```bash
# Todos los servicios
docker compose logs -f

# Solo backend
docker compose logs -f backend

# Solo conversor
docker compose logs -f kcc-converter
```

---

## Mantenimiento

### Comandos útiles

```bash
# Ver estado de containers
docker compose ps

# Reiniciar todos los servicios
docker compose restart

# Reiniciar un servicio específico
docker compose restart backend

# Actualizar a última versión
git pull
docker compose down
docker compose up -d --build

# Ver uso de recursos
docker stats

# Limpiar imágenes no usadas
docker system prune -a
```

### Backup de datos

```bash
# Backup de base de datos
docker compose exec postgres pg_dump -U manga alejandria > backup_$(date +%Y%m%d).sql

# Restaurar backup
docker compose exec -T postgres psql -U manga alejandria < backup.sql

# Backup de volúmenes (manga descargado)
docker run --rm -v alejandria_manga:/data -v $(pwd):/backup alpine tar czf /backup/manga_backup.tar.gz /data
```

### Actualización

```bash
cd /opt/alejandria  # o donde tengas el proyecto

# Guardar cambios locales si los hay
git stash

# Actualizar código
git pull

# Reconstruir containers
docker compose down
docker compose up -d --build

# Verificar que todo funciona
docker compose logs -f
```

---

## Puertos utilizados

| Puerto | Servicio | Descripción |
|--------|----------|-------------|
| 8888 | Frontend | Interfaz web |
| 9878 | Backend | API REST |
| 5432 | PostgreSQL | Base de datos (interno) |

---

## Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/NuevaCaracteristica`)
3. Commit tus cambios (`git commit -m 'Añade nueva característica'`)
4. Push a la rama (`git push origin feature/NuevaCaracteristica`)
5. Abre un Pull Request

---

## Licencia

Distribuido bajo la licencia MIT. Ver `LICENSE` para más información.

---

## Disclaimer

Este proyecto es solo para fines educativos y de uso personal. Respeta los derechos de autor y las leyes de tu país. Los desarrolladores no se hacen responsables del uso indebido de esta herramienta.

---

<div align="center">

Hecho con ❤️ para la comunidad

[Reportar Bug](https://github.com/tu-usuario/alejandria/issues) • [Solicitar Feature](https://github.com/tu-usuario/alejandria/issues)

</div>
