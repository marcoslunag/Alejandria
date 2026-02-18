# Alejandria

<div align="center">

**Tu biblioteca digital personal para manga, comics y libros**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://reactjs.org/)

</div>

---

## Descripcion

**Alejandria** es una plataforma de gestion de biblioteca digital para manga, comics y libros. Descarga automaticamente contenido desde multiples fuentes, lo convierte al formato EPUB optimizado para Kindle y lo envia directamente a tus dispositivos.

### Por que Alejandria?

- **Todo en uno**: Manga, comics americanos y libros en una sola plataforma
- **Multi-usuario**: Cada usuario tiene su propia biblioteca y sesion Kindle aislada
- **Scraping automatico**: Busca en ZonaComics, CBRComics, MegaComics, Lectulandia, Epubera y mas
- **Bundles inteligentes**: Detecta colecciones (TPB, HC) y las descarga de una sola vez
- **Integracion Kindle**: Envio directo via STK (Send to Kindle API) con OAuth2 de Amazon por usuario
- **Conversion automatica**: CBZ/CBR → EPUB con KCC, dividiendo archivos grandes automaticamente

---

## Arquitectura

```
+------------------------------------------------------------------------+
|                              ALEJANDRIA                                |
+------------------------------------------------------------------------+
|                                                                        |
|  +---------------+    +-------------------+    +--------------------+  |
|  |   Frontend    |    |      Backend      |    |    KCC Worker      |  |
|  |  (React UI)   |--->|    (FastAPI)      |--->|  (CBZ → EPUB)      |  |
|  |   :8888       |    |     :9878         |    |                    |  |
|  +---------------+    +--------+----------+    +--------------------+  |
|                                |                        |              |
|                                v                        v              |
|                       +---------------+         +---------------+      |
|                       |  PostgreSQL   |         |   /library    |      |
|                       |   Database   |         |   /downloads  |      |
|                       +---------------+         +---------------+      |
|                                                                        |
|  +------------------+   +------------------+   +------------------+   |
|  |  Comic Scrapers  |   |  Book Scrapers   |   |  Manga Scrapers  |   |
|  | ZonaComics       |   | Lectulandia      |   | MangaYComics     |   |
|  | CBRComics        |   | Epubera          |   | TomosManga       |   |
|  | MegaComics       |   | Google Books     |   | AniList          |   |
|  +------------------+   +------------------+   +------------------+   |
|                                                                        |
|  +------------------+   +------------------+   +------------------+   |
|  | URL Resolvers    |   | File Hosts       |   | Kindle (STK)     |   |
|  | ouo.io (PW)      |   | MediaFire        |   | OAuth2 Amazon    |   |
|  | uii.io (captcha) |   | MEGA             |   | Por usuario      |   |
|  | cbrcomicsweb     |   | Google Drive     |   | Multi-device     |   |
|  +------------------+   +------------------+   +------------------+   |
|                                                                        |
+------------------------------------------------------------------------+
```

### Contenedores Docker

| Contenedor | Puerto | Funcion |
|------------|--------|---------|
| `frontend` | 8888 | Interfaz React |
| `backend` | 9878 | API FastAPI |
| `kcc-converter` | — | Conversion CBZ→EPUB |
| `scheduler` | — | Tareas automaticas |
| `postgres` | 5432 | Base de datos |

---

## Caracteristicas

### Manga
- Metadata desde AniList (portadas, sinopsis, autores, generos)
- Scraping desde MangaYComics y TomosManga
- Conversion CBZ → EPUB con KCC (modo manga, derecha a izquierda)
- Envio a Kindle via STK por usuario

### Comics Americanos
- Metadata desde ComicVine (con traduccion automatico ES→EN para busquedas)
- Scrapers:
  - **ZonaComics**: aiohttp + Playwright para resolver ouo.io automaticamente
  - **CBRComics**: aiohttp + resolucion de redirects `cbrcomicsweb.space` + decode base64
  - **MegaComics** (megacomicstv3.blogspot.com): aiohttp + tabla de rangos de issues
- Asignacion inteligente de links por issue/bundle
- Deteccion automatica de bundles (TPB, HC, "Completo")
- Descarga desde MediaFire (individual y carpetas), MEGA (individual y carpetas via megatools)
- Conversion CBZ/CBR → EPUB con KCC (modo comic, izquierda a derecha)

### Libros
- Metadata desde Google Books
- Scrapers: Lectulandia, Epubera (con Playwright para autenticacion)
- Formato EPUB directo (sin conversion necesaria)
- Envio a Kindle via STK por usuario

### Sistema Multi-Usuario
- Admin autogenerado con password aleatoria al primer inicio
- El admin solo gestiona usuarios (no tiene acceso a contenido)
- Cada usuario tiene su propia biblioteca aislada
- Cada usuario configura su propia cuenta Amazon para STK
- Cambio de password obligatorio en el primer login
- Roles: `admin` y `usuario`

### Automatizacion (Scheduler)
- Verificacion periodica de nuevos capitulos de manga
- Busqueda de fuentes para comics monitorizados
- Conversion automatica al detectar archivos descargados (via KCC Worker)
- Envio automatico a Kindle cuando hay EPUBs convertidos
- Reintentos de descargas fallidas

---

## Instalacion

### Requisitos

- Docker 20.10+
- Docker Compose v2+

### Inicio rapido

```bash
# 1. Clonar
git clone https://github.com/tu-usuario/alejandria.git
cd alejandria

# 2. Configurar
cp .env.example .env
nano .env  # Edita con tus API keys

# 3. Iniciar
docker compose up -d --build

# 4. Ver password del administrador
docker compose logs backend | grep "ADMIN PASSWORD"
```

**Acceso:**
- Frontend: http://tu-ip:8888
- API Docs: http://tu-ip:9878/docs

### Variables de entorno

```env
# Base de datos
POSTGRES_USER=alejandria
POSTGRES_PASSWORD=tu-password-seguro
POSTGRES_DB=alejandria

# KCC - Conversion
KCC_PROFILE=KPW5       # KPW5, KPW4, KO, K11, KS
KCC_FORMAT=EPUB

# Scheduler
CHECK_INTERVAL_HOURS=6

# API Keys (opcionales pero recomendadas)
GOOGLE_BOOKS_API_KEY=   # Para busqueda de libros
COMICVINE_API_KEY=      # Para metadata de comics
CAPTCHA_API_KEY=        # 2captcha, para resolver uii.io

# Logs
LOG_LEVEL=INFO
```

### Primer acceso

1. Abre `http://tu-ip:8888`
2. Inicia sesion con usuario `admin` y la password que aparece en los logs:
   ```bash
   docker compose logs backend | grep "ADMIN PASSWORD"
   ```
3. Crea los usuarios que necesites desde el panel de administracion
4. Cada usuario debe cambiar su password en el primer login

---

## Uso

### Anadir contenido

**Manga:**
1. Busca → pestana Manga → selecciona un resultado de AniList
2. El sistema busca automaticamente fuentes de descarga

**Comics:**
1. Busca → pestana Comics → selecciona un volumen de ComicVine
2. El scheduler busca fuentes en los scrapers automaticamente
3. Cuando aparezcan links, selecciona issues y descarga manualmente

**Libros:**
1. Busca → pestana Libros → selecciona de Google Books
2. El sistema busca en Lectulandia/Epubera automaticamente

### Configurar Kindle (por usuario)

1. Ve a **Ajustes**
2. Click en "Conectar con Amazon"
3. Abre la URL en tu navegador e inicia sesion en Amazon
4. Copia la URL completa de redireccion y pegala en el campo
5. Selecciona tu Kindle preferido
6. Activa "Envio automatico al Kindle" si lo deseas

---

## Estructura del proyecto

```
alejandria/
├── backend/
│   ├── app/
│   │   ├── api/v1/            # Endpoints REST
│   │   │   ├── auth.py        # Autenticacion, usuarios, admin
│   │   │   ├── manga.py
│   │   │   ├── comics.py
│   │   │   ├── books.py
│   │   │   ├── queue.py
│   │   │   └── kindle.py      # STK endpoints
│   │   ├── models/            # SQLAlchemy models
│   │   ├── services/
│   │   │   ├── comic_scrapers/    # ZonaComics, CBRComics, MegaComics
│   │   │   ├── book_scrapers/     # Lectulandia, Epubera
│   │   │   ├── comic_service.py   # Logica de comics y bundles
│   │   │   ├── scheduler.py       # Tareas automaticas
│   │   │   └── stk_kindle_sender.py  # STK por usuario
│   │   └── core/
│   │       ├── security.py    # bcrypt hash/verify
│   │       └── deps.py        # FastAPI dependencies
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── ContentDetailPage.jsx  # Layout unificado
│       │   ├── ContentCard.jsx        # Card por tipo
│       │   ├── ContentGrid.jsx        # Grid con skeletons
│       │   ├── ConfirmModal.jsx       # Modal de confirmacion
│       │   └── ErrorBoundary.jsx
│       └── pages/
│           ├── Library.jsx    # Manga
│           ├── Comics.jsx     # Comics
│           ├── Books.jsx      # Libros
│           ├── Queue.jsx      # Cola unificada
│           ├── Settings.jsx   # Por usuario (incluye STK)
│           ├── AdminUsers.jsx # Solo admin
│           └── ChangePassword.jsx
├── workers/
│   ├── kcc-converter/     # Conversion CBZ → EPUB
│   └── scheduler/         # Scheduler en contenedor separado
├── docker-compose.yml
└── .env.example
```

---

## API (endpoints principales)

### Autenticacion
| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/api/v1/auth/login` | Login, retorna JWT |
| POST | `/api/v1/auth/change-password` | Cambiar password |
| GET | `/api/v1/auth/users` | Listar usuarios (solo admin) |
| POST | `/api/v1/auth/users` | Crear usuario (solo admin) |

### Comics
| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/api/v1/comics/` | Listar biblioteca |
| POST | `/api/v1/comics/` | Anadir comic |
| GET | `/api/v1/comics/{id}` | Detalles |
| POST | `/api/v1/comics/{id}/issues/download` | Descargar issues |
| POST | `/api/v1/comics/{id}/issues/{issue_id}/send-to-kindle` | Enviar a Kindle |

### Kindle (STK)
| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/api/v1/kindle/stk/status` | Estado autenticacion del usuario |
| GET | `/api/v1/kindle/stk/signin-url` | URL OAuth2 de Amazon |
| POST | `/api/v1/kindle/stk/authorize` | Completar autenticacion |
| GET | `/api/v1/kindle/stk/devices` | Listar dispositivos Kindle |
| POST | `/api/v1/kindle/stk/send/{chapter_id}` | Enviar tomo a Kindle |
| POST | `/api/v1/kindle/stk/logout` | Desconectar cuenta Amazon |

Documentacion completa: http://localhost:9878/docs

---

## Comandos utiles

```bash
# Ver logs
docker compose logs backend --tail 100
docker compose logs kcc-converter --tail 100
docker compose logs scheduler --tail 100

# Reiniciar servicios
docker compose restart backend
docker compose restart scheduler

# Actualizar (rebuild)
git pull
docker compose up -d --build

# Ver password admin (si se perdio)
docker compose logs backend | grep -i "admin password"

# Consultar base de datos
docker compose exec -T postgres psql -U alejandria alejandria -c "SELECT username, is_admin FROM users;"

# Ver bundles de comics
docker compose exec -T postgres psql -U alejandria alejandria -c \
  "SELECT c.title, ci.issue_number, ci.bundle_title FROM comic_issues ci \
   JOIN comics c ON ci.comic_id = c.id WHERE ci.bundle_id IS NOT NULL LIMIT 20;"

# Backup
docker compose exec postgres pg_dump -U alejandria alejandria > backup_$(date +%Y%m%d).sql
```

---

## Solucion de problemas

### El admin no puede entrar
```bash
docker compose logs backend | grep -i "admin password"
```

### Descargas atascadas en "downloading"
```bash
docker compose exec -T postgres psql -U alejandria alejandria -c \
  "UPDATE download_queue SET status='queued' WHERE status='downloading';"
```

### Comics sin links de descarga
El scheduler busca automaticamente cada 6 horas. Para forzar:
```bash
docker compose restart scheduler
```

### STK "session expired"
Ve a Ajustes → desconectar cuenta Amazon → volver a conectar.

---

## Roadmap

### Completado
- [x] Manga (AniList + MangaYComics + KCC + STK)
- [x] Libros (Google Books + Lectulandia + Epubera + STK)
- [x] Comics americanos (ComicVine + ZonaComics + CBRComics + MegaComics)
- [x] Bundles inteligentes (TPB, HC, colecciones completas)
- [x] Resolucion de acortadores (ouo.io automatico, uii.io con captcha)
- [x] Descarga desde MEGA (individual y carpetas via megatools)
- [x] Sistema multi-usuario con roles
- [x] STK aislado por usuario (sesiones independientes)
- [x] Scheduler en contenedor separado
- [x] Notificaciones toast (reemplazando alert/confirm del navegador)
- [x] KCC en contenedor separado con cola de trabajos
- [x] Division automatica de archivos grandes (>180MB)

### Planificado
- [ ] Notificaciones (Telegram, Discord)
- [ ] Importacion desde Calibre
- [ ] Estadisticas de lectura
- [ ] Sincronizacion con AniList/MAL
- [ ] PWA / soporte offline

---

## Disclaimer

Este proyecto es solo para fines educativos y de uso personal. Respeta los derechos de autor y las leyes de tu pais.

---

<div align="center">

Hecho con amor para la comunidad

</div>
