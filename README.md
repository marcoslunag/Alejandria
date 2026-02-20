# Alejandria

<div align="center">

**Tu biblioteca digital personal · Manga · Comics · Libros · Kindle**

[![Version](https://img.shields.io/badge/version-3.1.0-blue.svg)](https://github.com/tu-usuario/alejandria/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org/)

</div>

---

## Que es Alejandria?

**Alejandria** automatiza tu biblioteca digital de cabo a rabo: busca en los scrapers, descarga, convierte a EPUB optimizado para Kindle y lo envia directamente a tu dispositivo. Tu solo añades el titulo; el sistema hace el resto.

- **Manga** — metadata AniList, descarga desde TomosManga + MangaYComics (paralelo), lector web integrado
- **Comics americanos** — metadata ComicVine (busqueda ES→EN automatica), scrapers ZonaComics, CBRComics, MegaComics
- **Libros** — metadata Google Books, EPUB desde Lectulandia y Epubera
- **Kindle** — conversion CBZ/CBR → EPUB con KCC y envio via Send-to-Kindle por usuario

---

## Caracteristicas principales

### Descarga inteligente
- Busca en multiples scrapers en paralelo con fallback automatico
- Resolucion de acortadores: ouo.io en background, uii.io con captcha opcional
- Descarga desde MediaFire (individual y carpetas), MEGA (individual y carpetas via megatools CLI), Google Drive, Krakenfiles y mas
- Bundles inteligentes: detecta TPB, HC y colecciones completas y las descarga de una vez

### Conversion y envio
- Conversion CBZ/CBR/RAR → EPUB con [KCC](https://github.com/ciromattia/kcc) (modo comic o manga)
- Division automatica de archivos > 180 MB en partes
- Envio directo a Kindle via STK (Send to Kindle API de Amazon) con OAuth2 por usuario

### Multi-usuario
- Admin con password aleatoria generada al primer arranque
- Cada usuario tiene su biblioteca aislada y su propia cuenta Amazon/Kindle
- Roles: admin (gestiona usuarios) y usuario (gestiona su contenido)
- Rate limiting en login: 10 intentos / 15 min por IP

### Automatizacion
- Scheduler en contenedor separado: comprueba nuevos capitulos, descarga, convierte y envia
- Cola de trabajos con reintentos automaticos
- Lock files para evitar colisiones entre el downloader y el conversor KCC

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                          ALEJANDRIA                             │
├──────────────┬──────────────────────┬───────────────────────────┤
│  Frontend    │      Backend         │      Workers              │
│  React/Vite  │  FastAPI + SQLAlchemy│  KCC Converter            │
│  :8888       │  :9878               │  Scheduler                │
├──────────────┴──────────┬───────────┴───────────────────────────┤
│                         │                                        │
│              PostgreSQL │  /downloads  /library/kindle          │
│                         │                                        │
├─────────────────────────┴───────────────────────────────────────┤
│  Scrapers externos                                              │
│  ZonaComics · CBRComics · MegaComics · MangaYComics             │
│  Lectulandia · Epubera · AniList · ComicVine · Google Books     │
└─────────────────────────────────────────────────────────────────┘
```

| Contenedor | Puerto externo | Funcion |
|---|---|---|
| `frontend` | 8888 | UI React |
| `backend` | 9878 | API FastAPI |
| `postgres` | — (solo interno) | Base de datos |
| `kcc-converter` | — | Conversion CBZ → EPUB |
| `scheduler` | — | Tareas automaticas en background |

---

## Instalacion

### Requisitos

- [Docker](https://docs.docker.com/get-docker/) 20.10 o superior
- [Docker Compose](https://docs.docker.com/compose/install/) v2+
- 2 GB de RAM libre (4 GB recomendados si usas muchos scrapers a la vez)
- Espacio en disco para tu biblioteca (recomendado: SSD con al menos 20 GB libres)

### Inicio rapido

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/alejandria.git
cd alejandria

# 2. Crear y configurar el fichero de entorno
cp .env.example .env
# Edita .env con tus API keys (ver seccion siguiente)

# 3. Arrancar todos los servicios
docker compose up -d --build

# 4. Obtener la password del administrador (solo aparece la primera vez)
docker compose logs backend | grep "ADMIN PASSWORD"
```

**Acceder a la aplicacion:**
- Interfaz web: `http://localhost:8888`
- (En servidor): `http://<ip-del-servidor>:8888`

> **Nota:** La password del admin solo aparece en los logs **una vez**, la primera vez que arranca la aplicacion. Guardala bien.

---

## Configuracion

Copia `.env.example` a `.env` y rellena los valores que necesites:

```bash
cp .env.example .env
```

### Variables disponibles

| Variable | Obligatoria | Descripcion |
|---|---|---|
| `SECRET_KEY` | **Si** | Clave secreta para JWT. Genera una con: `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | **Si** | Password de PostgreSQL. Usa una contrasena fuerte |
| `POSTGRES_USER` | No | Usuario de BD (default: `alejandria`) |
| `POSTGRES_DB` | No | Nombre de BD (default: `alejandria`) |
| `COMICVINE_API_KEY` | Recomendada | Para metadata de comics. Registro gratuito en [comicvine.gamespot.com/api](https://comicvine.gamespot.com/api/) |
| `GOOGLE_BOOKS_API_KEY` | Recomendada | Para metadata de libros. Consola en [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
| `CAPTCHA_API_KEY` | Opcional | API key de [2captcha.com](https://2captcha.com/) para resolver acortadores uii.io |
| `KCC_PROFILE` | No | Perfil Kindle para conversion (default: `KPW5`). Opciones: `KPW5`, `KPW4`, `KO`, `K11`, `KS` |
| `KCC_FORMAT` | No | Formato de salida (default: `EPUB`) |
| `CHECK_INTERVAL_HOURS` | No | Frecuencia del scheduler en horas (default: `6`) |
| `LOG_LEVEL` | No | Nivel de logs (default: `INFO`) |

> **Importante:** La variable `SECRET_KEY` es critica para la seguridad de las sesiones. Si no la configuras, se generara una aleatoria que se reinicia con cada restart (cerrando sesion a todos los usuarios).

### Perfiles KCC por dispositivo

| Perfil | Dispositivo |
|---|---|
| `KPW5` | Kindle Paperwhite 5 (11a gen, 2021+) — *recomendado* |
| `KPW4` | Kindle Paperwhite 4 (10a gen, 2018-2021) |
| `K11` | Kindle 11 (basico 2022+) |
| `KO` | Kindle Oasis |
| `KS` | Kindle Scribe |

---

## Primer acceso

1. Abre `http://localhost:8888` en tu navegador
2. Inicia sesion con usuario `admin` y la password de los logs
3. Cambia la password en tu primer login (obligatorio)
4. Crea usuarios adicionales desde **Admin → Usuarios**
5. Cada usuario debe configurar su cuenta Amazon en **Ajustes → Kindle**

---

## Uso rapido

### Anadir manga
1. **Buscar** → pestana **Manga** → selecciona un resultado de AniList
2. El sistema busca fuentes automaticamente
3. Los tomos disponibles aparecen con el estado de descarga

### Anadir un comic
1. **Buscar** → pestana **Comics** → selecciona un volumen de ComicVine
2. El scheduler busca links en los scrapers (puede tardar unos minutos)
3. Cuando aparezcan links, selecciona los issues que quieres y pulsa **Descargar**

### Anadir un libro
1. **Buscar** → pestana **Libros** → selecciona de Google Books o Lectulandia
2. Si hay EPUB disponible, aparece el badge "✓ EPUB disponible"
3. Pulsa **Anadir** y el scheduler descargara el EPUB

### Subir un archivo propio
1. **Subir** en la navbar
2. Selecciona el tipo (Manga / Comic / Libro)
3. Busca el titulo en AniList / ComicVine / Google Books y seleccionalo
4. Arrastra el archivo CBZ, EPUB o PDF (o haz clic para seleccionarlo)
5. Indica el numero de tomo/capitulo (opcional) y pulsa **Subir archivo**
6. El archivo se anade a la biblioteca y se convierte automaticamente

### Configurar Kindle (por usuario)
1. **Ajustes** → **Cuenta Kindle**
2. Click en **Conectar con Amazon**
3. Abre la URL en el navegador, inicia sesion en Amazon
4. Copia la URL completa de redireccion y pegala en el campo
5. Selecciona tu dispositivo Kindle preferido
6. Activa **Envio automatico** si lo deseas

---

## Comandos utiles

```bash
# Ver logs en tiempo real
docker compose logs -f backend
docker compose logs -f scheduler
docker compose logs -f kcc-converter

# Ver los ultimos 100 logs de un servicio
docker compose logs backend --tail 100

# Reiniciar un servicio
docker compose restart backend
docker compose restart scheduler

# Actualizar a la ultima version
git pull
docker compose up -d --build

# Recuperar la password del admin (si se perdio, solo funciona si el admin no existia aun)
docker compose logs backend | grep -i "ADMIN PASSWORD"

# Backup de la base de datos
docker compose exec postgres pg_dump -U alejandria alejandria > backup_$(date +%Y%m%d).sql

# Restaurar backup
cat backup_YYYYMMDD.sql | docker compose exec -T postgres psql -U alejandria alejandria

# Consultar la base de datos
docker compose exec -T postgres psql -U alejandria alejandria -c "SELECT username, is_admin, is_active FROM users;"
```

---

## Solucion de problemas

### No puedo entrar con el admin
- La password se genera **una sola vez** al primer arranque. Si no la guardaste y el usuario admin ya existe en la BD, no hay forma de recuperarla automaticamente.
- Solucion: resetear la password desde la BD:
  ```bash
  # Genera un hash bcrypt de tu nueva password
  docker compose exec backend python -c "from app.core.security import hash_password; print(hash_password('nueva-password'))"
  # Actualiza en BD
  docker compose exec -T postgres psql -U alejandria alejandria -c \
    "UPDATE users SET password_hash='HASH_AQUI', must_change_password=true WHERE username='admin';"
  ```

### Descargas atascadas en "descargando"
```bash
# Desde la UI: Cola → Reset Stuck (boton en la interfaz)
# O desde la BD:
docker compose exec -T postgres psql -U alejandria alejandria -c \
  "UPDATE chapters SET status='pending' WHERE status='downloading';
   UPDATE comic_issues SET status='pending' WHERE status='downloading';"
```

### Comics sin links de descarga
El scheduler busca automaticamente cada `CHECK_INTERVAL_HOURS` horas. Para forzar una busqueda:
```bash
docker compose restart scheduler
```

### Conversion KCC muy lenta o falla
- Comprueba que el contenedor kcc-converter esta corriendo: `docker compose ps`
- Lee los logs: `docker compose logs kcc-converter --tail 50`
- Si el archivo es > 500 MB puede tardar varios minutos por parte

### STK "session expired" o "no autorizado"
- Ve a **Ajustes → Cuenta Kindle → Desconectar**
- Vuelve a conectar siguiendo el proceso OAuth

### Error "no space left on device"
Los archivos descargados y convertidos se acumulan. Puedes limpiar desde la UI (detalle de cada manga/comic → eliminar archivo) o directamente:
```bash
# Ver uso de volumenes Docker
docker system df -v
# Limpiar volumenes sin usar (cuidado: no borra datos de la app)
docker volume prune
```

---

## Tests

El proyecto incluye tests de integracion que verifican scrapers, servicios de metadata, resolvers y downloaders contra los servicios reales.

```bash
# Tests de scrapers/downloaders (requiere servicios externos accesibles)
docker exec alejandria-backend python -m pytest tests/test_scrapers.py -v

# Tests unitarios del backend (auth, library, reading status, etc.)
docker exec alejandria-backend python -m pytest tests/ -v

# Solo una suite concreta
docker exec alejandria-backend python -m pytest tests/test_auth.py -v
```

| Suite | Que cubre |
|---|---|
| `test_scrapers.py` | TomosManga, MangayComics, Lectulandia, CBRComics, MegaComics, AniList, GoogleBooks, ComicVine, OUO.io, TeraBox, MangaDownloader, HostManager, ContentMatcher, Translator |
| `test_auth.py` | Login, registro, JWT, rate limiting |
| `test_library.py` | CRUD de manga, comics y libros |
| `test_reading_status.py` | Estados de lectura (read/reading/unread) |
| `test_health.py` | Health check del backend |
| `test_recommendations.py` | Motor de recomendaciones locales |

> **Nota:** Los tests de `test_scrapers.py` dependen de servicios externos (OUO.io, TeraBox, AniList, etc.) y pueden fallar si esos servicios estan caidos o bloqueando. ComicVine requiere `COMICVINE_API_KEY` configurada.

---

## Estructura del proyecto

```
alejandria/
├── backend/
│   ├── app/
│   │   ├── api/v1/            # Endpoints REST (manga, comics, books, auth, queue...)
│   │   ├── models/            # Modelos SQLAlchemy
│   │   ├── services/
│   │   │   ├── comic_scrapers/    # ZonaComics, CBRComics, MegaComics, GetComics
│   │   │   ├── book_scrapers/     # Lectulandia, Epubera
│   │   │   ├── manga_scrapers/    # MangaYComics, TomosManga, TuMangaOnline
│   │   │   ├── generic_downloader.py  # MediaFire, MEGA, etc.
│   │   │   ├── comic_service.py   # Logica de comics y bundles
│   │   │   ├── scheduler.py       # ContentScheduler
│   │   │   └── stk_kindle_sender.py   # STK por usuario
│   │   └── core/
│   │       ├── security.py        # JWT, bcrypt
│   │       └── deps.py            # FastAPI dependencies
│   ├── tests/                 # Tests (pytest): scrapers, auth, library, etc.
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── components/            # ContentDetailPage, ContentCard, ContentGrid...
│       ├── pages/                 # Library, Comics, Books, Queue, Settings, MangaReader...
│       └── utils/sanitizeUrl.js   # Sanitizacion de URLs
├── workers/
│   ├── kcc-converter/     # Conversion CBZ → EPUB
│   └── scheduler/         # Scheduler en contenedor separado
├── scripts/               # Migraciones y utilidades
├── docker-compose.yml
└── .env.example
```

---

## Roadmap

### v1.0 — Completado
- [x] Manga (AniList + MangaYComics + TomosManga + KCC + STK)
- [x] Libros (Google Books + Lectulandia + Epubera + STK)
- [x] Comics (ComicVine + ZonaComics + CBRComics + MegaComics)
- [x] Bundles inteligentes (TPB, HC, colecciones completas)
- [x] Resolucion de acortadores (ouo.io automatico, uii.io con 2captcha)
- [x] Descarga desde MediaFire, MEGA individual y carpetas, Google Drive
- [x] Sistema multi-usuario con roles y sesiones aisladas
- [x] STK por usuario con OAuth2 de Amazon
- [x] Scheduler en contenedor separado
- [x] KCC Worker con cola, reintentos y division de archivos grandes
- [x] Busqueda enriquecida (disponibilidad en scrapers al buscar)
- [x] Notificaciones toast en toda la UI
- [x] Hardening de seguridad (usuarios no-root, rate limiting, IDOR fixes, etc.)

### v2.0 — Completado
- [x] Watchlist inteligente (toggle monitored + filtro "Siguiendo")
- [x] Smart retry con backoff exponencial (5min → 30min → 2h → 24h)
- [x] Reading progress (mark-as-read, reading_status, stats de biblioteca)
- [x] Quality preferences por usuario (host preferido, formato, tamano maximo)
- [x] Import folder — watcher automatico de `/imports` cada 5 minutos
- [x] Content matching — anti-duplicados con Jaccard similarity ≥ 0.8
- [x] Differential downloads — solo descarga issues faltantes en bundles
- [x] Metadata enricher — refresh semanal desde AniList/ComicVine/Google Books
- [x] PWA mobile — manifest, service worker, menu hamburguesa responsive
- [x] Recomendaciones locales sin IA — pagina /discover con perfil de gustos

### v3.0 — Completado
- [x] Dashboard personal — stats de biblioteca, actividad reciente, progreso de lectura
- [x] Filtros avanzados — genero, estado, ano, idioma en Biblioteca/Comics/Libros
- [x] Badge de notificaciones — nuevos capitulos en la navbar con polling cada 60s
- [x] Panel de logs — sistema de diagnostico persistente en Ajustes (solo admin)
- [x] Export/Backup — JSON export/import de toda la biblioteca
- [x] Cola en tiempo real — SSE (Server-Sent Events) para actualizaciones sin polling
- [x] TuMangaOnline — segundo scraper de manga como fallback automatico
- [x] Web reader — leer manga descargado directamente en el navegador (fullscreen, teclado)

### v3.1 — Completado
- [x] TomosManga como fuente principal — busqueda paralela TomosManga + MangaYComics, ambas fuentes aparecen en los badges
- [x] Scorer mejorado — re-ediciones y ediciones recientes son preferidas (antes eran penalizadas)
- [x] Estado de lectura sin descarga — marcar manga/comic/libro como "leido/leyendo/sin leer" directamente desde la card
- [x] Pagina de inicio = Descubrir — `/` muestra recomendaciones; el dashboard esta en `/dashboard`
- [x] Descubrir con fallback — si la biblioteca esta vacia, muestra tendencias de AniList con banner informativo
- [x] Uploader de archivos — subir CBZ/CBR/EPUB/PDF directamente; crea el item en biblioteca si no existe

### Futuro
- [ ] Notificaciones push (Telegram, Discord)
- [ ] Importacion desde Calibre
- [ ] Sincronizacion con AniList / MyAnimeList
- [ ] Lector web para comics

---

## Seguridad

- Todos los contenedores corren como usuario no-root (`uid 1000`)
- PostgreSQL no expuesto al exterior (solo accesible dentro de la red Docker)
- JWT tokens firmados con `SECRET_KEY` configurable (sin default hardcodeado)
- Rate limiting en login: 10 intentos fallidos por IP cada 15 minutos
- Endpoints admin protegidos con verificacion de rol
- API docs (`/docs`) deshabilitados en produccion (activar con `DEBUG=True`)

---

## Disclaimer

Este proyecto es para uso personal y educativo. El autor no se hace responsable del uso que se haga del software. Respeta los derechos de autor y las leyes vigentes en tu pais.

---

<div align="center">

Hecho con amor para la comunidad · [Reportar un bug](https://github.com/tu-usuario/alejandria/issues)

</div>
