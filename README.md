# Alejandria

<div align="center">

**Tu biblioteca digital personal para manga, comics y libros**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://reactjs.org/)

[Caracteristicas](#-caracteristicas) - [Instalacion](#-instalacion) - [Configuracion](#-configuracion) - [Uso](#-uso) - [API](#-api) - [Roadmap](#-roadmap)

</div>

---

## Descripcion

**Alejandria** es una plataforma de gestion de biblioteca digital disenada para manga, comics y libros. Inspirada en herramientas como Radarr/Sonarr y Kaizoku, ofrece descarga automatizada, conversion a formatos Kindle y envio directo a tus dispositivos.

### Por que Alejandria?

- **Todo en uno**: Descarga, convierte y envia a tu Kindle automaticamente
- **Multiples fuentes**: Soporte para TomosManga, MangaYComics, Google Books, Lectulandia y mas
- **Integracion AniList**: Busca y anade mangas directamente desde AniList
- **Libros EPUB**: Busqueda en Google Books y descarga desde scrapers de libros
- **Archivos grandes**: Soporte para archivos >25MB usando STK (Send to Kindle API)
- **Auto-division**: Divide automaticamente tomos grandes en partes para cumplir limites
- **Interfaz moderna**: UI inspirada en Kaizoku con diseno oscuro y responsivo

---

## Caracteristicas

### Biblioteca de Manga
- Gestion de biblioteca de manga
- Busqueda en multiples fuentes (TomosManga, MangaYComics, AniList)
- Metadatos automaticos desde AniList (portadas, sinopsis, autores)
- Estado de seguimiento por tomo (pendiente, descargado, convertido, enviado)

### Biblioteca de Libros
- Busqueda en Google Books con metadatos completos
- Descarga de EPUBs desde Lectulandia
- Integracion con el sistema de cola de descargas
- Envio a Kindle mediante STK
- Interfaz visual con esquema de color verde (diferenciado del manga)

### Descargas
- Cola de descargas unificada para manga y libros
- Indicadores visuales diferenciados (azul para manga, verde para libros)
- Descargas concurrentes configurables
- Soporte para multiples hosts (TeraBox, MediaFire, Krakenfiles, etc.)
- Reintentos automaticos en caso de error
- Cancelacion de descargas en progreso

### Conversion
- Conversion automatica a EPUB usando KCC (Kindle Comic Converter)
- Division automatica de tomos grandes (>200MB)
- Perfiles optimizados para diferentes Kindles (KPW5, KO, K11, etc.)
- Metadatos ComicInfo.xml embebidos

### Kindle
- **STK (Send to Kindle API)**: Envio directo con autenticacion OAuth2
- Soporte para archivos hasta 200MB
- Soporte multi-dispositivo
- Division automatica de envios por partes
- Boton de envio integrado en cola de descargas

### Automatizacion
- Verificacion periodica de nuevos capitulos (configurable)
- Descarga automatica de nuevos tomos
- Conversion automatica al detectar nuevos archivos
- Envio automatico al Kindle (opcional)

---

## Arquitectura

```
+------------------------------------------------------------------+
|                         ALEJANDRIA                                |
+------------------------------------------------------------------+
|                                                                   |
|  +---------------+    +---------------+    +---------------+      |
|  |   Frontend    |    |   Backend     |    |  KCC Worker   |      |
|  |  (React UI)   |--->|  (FastAPI)    |--->|  (Converter)  |      |
|  |   :8888       |    |    :9878      |    |               |      |
|  +---------------+    +-------+-------+    +---------------+      |
|                               |                    |               |
|                               v                    v               |
|                      +---------------+      +---------------+     |
|                      |  PostgreSQL   |      |   /manga      |     |
|                      |   Database    |      |   /kindle     |     |
|                      +---------------+      |   /downloads  |     |
|                                             +---------------+     |
|                                                                   |
|  +---------------+    +---------------+    +---------------+      |
|  |   Scrapers    |    | Downloaders   |    | Kindle Send   |      |
|  | TomosManga    |    |   TeraBox     |    |     STK       |      |
|  | MangaYComics  |    |  MediaFire    |    |   OAuth2      |      |
|  | Lectulandia   |    | Krakenfiles   |    |               |      |
|  | Google Books  |    |   Generic     |    |               |      |
|  +---------------+    +---------------+    +---------------+      |
|                                                                   |
+-------------------------------------------------------------------+
```

---

## Instalacion

### Requisitos del sistema

| Recurso | Minimo | Recomendado |
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
- Cuenta Amazon para STK (envio a Kindle)
- API Key de Google Books (opcional, para mas resultados)

---

### Instalacion rapida (3 pasos)

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

### Instalacion en Proxmox LXC

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

# Anadir repositorio Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Instalar Docker
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verificar instalacion
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

---

### Configuracion del archivo .env

```env
# ============================================
# ALEJANDRIA - Configuracion
# ============================================

# Base de datos (cambiar password en produccion)
POSTGRES_USER=manga
POSTGRES_PASSWORD=tu-password-seguro
POSTGRES_DB=alejandria

# KCC - Conversion
KCC_PROFILE=KPW5    # Modelo Kindle: KPW5, KPW4, KO, K11, KS
KCC_FORMAT=EPUB     # EPUB (MOBI ya no soportado por Send to Kindle)

# Scheduler
CHECK_INTERVAL_HOURS=6

# Logging
LOG_LEVEL=INFO

# Google Books API (opcional - para mas resultados de busqueda)
GOOGLE_BOOKS_API_KEY=

# Captcha resolver (opcional - para shorteners con captcha)
CAPTCHA_API_KEY=
```

---

## Configuracion

### STK (Send to Kindle API)

El envio a Kindle se realiza mediante STK (Send to Kindle API) usando OAuth2 de Amazon.

1. En la interfaz web, ve a **Ajustes**
2. Click en "Conectar con Amazon"
3. Inicia sesion con tu cuenta Amazon
4. Copia la URL de redireccion y pegala
5. Selecciona tu dispositivo Kindle preferido
6. Guarda la configuracion

> **Nota**: STK soporta archivos hasta 200MB. Los archivos mas grandes se dividen automaticamente.

### TeraBox (Descargas desde TeraBox)

Para descargar archivos desde TeraBox, necesitas configurar las cookies de tu cuenta:

1. **Crear cuenta en TeraBox** (si no tienes): https://www.terabox.com
2. **Obtener cookies**:
   - Instala una extension de cookies en tu navegador (Cookie-Editor, etc.)
   - Inicia sesion en TeraBox
   - Exporta las cookies o copialas desde DevTools (F12 > Application > Cookies)
3. **Configurar en `.env`**:

```env
# Formato: cookie1=valor1; cookie2=valor2; ...
TERABOX_COOKIE=ndus=TU_NDUS; browserid=TU_BROWSERID; csrfToken=TU_CSRF; lang=es; PANWEB=1
```

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

### Anadir manga

1. **Desde busqueda**: Busca en la barra superior, selecciona de AniList o TomosManga
2. **Desde URL**: Pega directamente la URL de TomosManga o MangaYComics
3. **Desde AniList**: Busca por nombre y se vincula automaticamente con las fuentes

### Anadir libros

1. **Desde busqueda**: Cambia a la pestana "Libros" en la busqueda
2. **Google Books**: Busca por titulo o autor, metadatos se importan automaticamente
3. **Scrapers**: Los libros se buscan automaticamente en Lectulandia para descarga

### Descargar

1. Ve a la pagina del manga o libro
2. Selecciona los tomos/archivos que quieres descargar
3. Click en "Descargar seleccionados"
4. Monitorea el progreso en la Cola de Descargas

### Enviar a Kindle

- **Manual**: Click en el boton "Kindle" en cualquier tomo/libro descargado
- **Desde cola**: Boton de Kindle disponible para items completados

---

## API

### Endpoints principales

#### Manga
| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/api/v1/manga/` | Listar biblioteca |
| GET | `/api/v1/manga/search` | Buscar manga |
| POST | `/api/v1/manga/add/anilist` | Anadir desde AniList |
| POST | `/api/v1/manga/add/url` | Anadir desde URL |
| GET | `/api/v1/manga/{id}` | Detalles de manga |
| DELETE | `/api/v1/manga/{id}` | Eliminar manga |
| POST | `/api/v1/manga/{id}/refresh` | Actualizar capitulos |

#### Libros
| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/api/v1/books/library` | Listar biblioteca |
| GET | `/api/v1/books/search` | Buscar libros |
| POST | `/api/v1/books/from-google-books` | Anadir desde Google Books |
| GET | `/api/v1/books/{id}` | Detalles del libro |
| GET | `/api/v1/books/{id}/stats` | Estadisticas del libro |
| DELETE | `/api/v1/books/{id}` | Eliminar libro |
| POST | `/api/v1/books/{id}/chapters/download` | Descargar archivos |
| POST | `/api/v1/books/{id}/chapters/{chapter_id}/send-to-kindle` | Enviar a Kindle |

#### Cola
| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/api/v1/queue/` | Ver cola de descargas |
| POST | `/api/v1/queue/{id}/cancel` | Cancelar descarga |
| POST | `/api/v1/queue/{id}/retry` | Reintentar descarga |
| DELETE | `/api/v1/queue/{id}/file` | Eliminar archivo |

#### Kindle (STK)
| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/api/v1/kindle/stk/send/{id}` | Enviar a Kindle |
| GET | `/api/v1/kindle/stk/status` | Estado de autenticacion |
| GET | `/api/v1/kindle/stk/devices` | Listar dispositivos |

Documentacion completa en: http://localhost:9878/docs

---

## Estructura del Proyecto

```
alejandria/
├── backend/                    # API FastAPI
│   ├── app/
│   │   ├── api/v1/            # Endpoints REST
│   │   │   ├── manga.py       # Endpoints de manga
│   │   │   ├── books.py       # Endpoints de libros
│   │   │   ├── queue.py       # Cola de descargas
│   │   │   └── kindle.py      # Envio a Kindle
│   │   ├── models/            # Modelos SQLAlchemy
│   │   ├── schemas/           # Schemas Pydantic
│   │   ├── services/          # Logica de negocio
│   │   │   ├── scraper.py     # Scraper generico
│   │   │   ├── downloader.py  # Gestor de descargas
│   │   │   ├── book_scrapers/ # Scrapers de libros
│   │   │   ├── google_books.py # API Google Books
│   │   │   ├── scheduler.py   # Tareas programadas
│   │   │   └── stk_kindle_sender.py # Envio a Kindle via STK
│   │   └── main.py
│   └── Dockerfile
├── frontend/                   # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/        # Componentes reutilizables
│   │   │   ├── ChapterList.jsx
│   │   │   ├── BookChapterList.jsx
│   │   │   ├── SendToKindleButton.jsx
│   │   │   └── BookSendToKindleButton.jsx
│   │   ├── pages/             # Paginas principales
│   │   │   ├── Library.jsx    # Biblioteca de manga
│   │   │   ├── Books.jsx      # Biblioteca de libros
│   │   │   ├── Queue.jsx      # Cola de descargas
│   │   │   └── Settings.jsx   # Configuracion
│   │   └── services/api.js    # Cliente API
│   └── Dockerfile
├── workers/
│   └── kcc-converter/         # Worker de conversion
│       ├── converter.py       # Logica de conversion
│       └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Roadmap

### En desarrollo
- [ ] Soporte para comics americanos (ComicVine)

### Planificado
- [ ] Notificaciones (Telegram, Discord, Email)
- [ ] Busqueda en mas fuentes (MangaDex, etc.)
- [ ] Importacion masiva desde Calibre
- [ ] Estadisticas de lectura
- [ ] Sincronizacion con servicios de tracking (AniList, MAL)
- [ ] Modo offline / PWA
- [ ] Soporte multi-idioma

### Completado
- [x] Interfaz web moderna
- [x] Descarga automatica desde TomosManga
- [x] Conversion a EPUB con KCC
- [x] Envio a Kindle via STK (hasta 200MB)
- [x] Division automatica de tomos grandes
- [x] Integracion con AniList
- [x] Cola de descargas con cancelacion
- [x] Soporte multi-dispositivo Kindle
- [x] Bypass de TeraBox via 1024tera.com
- [x] **Soporte para libros (EPUB)** - Busqueda Google Books + Lectulandia
- [x] **Cola unificada** - Manga y libros en la misma vista

---

## Resolucion de Problemas

### Error: "STK not authenticated"
Ve a Configuracion > Kindle y completa la autenticacion con Amazon.

### La conversion falla
1. Verifica que el worker KCC esta corriendo: `docker-compose logs kcc-converter`
2. Comprueba que KindleGen esta instalado en el worker

### Las descargas se quedan "downloading"
```bash
# Reiniciar descargas atascadas
curl -X POST http://localhost:9878/api/v1/queue/reset-stuck
```

### TeraBox: Error "errno 400141 - need verify"
Esto ocurre en el dominio principal de TeraBox. El bypass usa `1024tera.com` para evitarlo. Si persiste, las cookies han expirado - obten nuevas.

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

### Comandos utiles

```bash
# Ver estado de containers
docker compose ps

# Reiniciar todos los servicios
docker compose restart

# Reiniciar un servicio especifico
docker compose restart backend

# Actualizar a ultima version
git pull
docker compose down
docker compose up -d --build

# Ver uso de recursos
docker stats

# Limpiar imagenes no usadas
docker system prune -a
```

### Backup de datos

```bash
# Backup de base de datos
docker compose exec postgres pg_dump -U manga alejandria > backup_$(date +%Y%m%d).sql

# Restaurar backup
docker compose exec -T postgres psql -U manga alejandria < backup.sql
```

---

## Puertos utilizados

| Puerto | Servicio | Descripcion |
|--------|----------|-------------|
| 8888 | Frontend | Interfaz web |
| 9878 | Backend | API REST |
| 5432 | PostgreSQL | Base de datos (interno) |

---

## Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/NuevaCaracteristica`)
3. Commit tus cambios (`git commit -m 'Anade nueva caracteristica'`)
4. Push a la rama (`git push origin feature/NuevaCaracteristica`)
5. Abre un Pull Request

---

## Licencia

Distribuido bajo la licencia MIT. Ver `LICENSE` para mas informacion.

---

## Disclaimer

Este proyecto es solo para fines educativos y de uso personal. Respeta los derechos de autor y las leyes de tu pais. Los desarrolladores no se hacen responsables del uso indebido de esta herramienta.

---

<div align="center">

Hecho con amor para la comunidad

[Reportar Bug](https://github.com/tu-usuario/alejandria/issues) - [Solicitar Feature](https://github.com/tu-usuario/alejandria/issues)

</div>
