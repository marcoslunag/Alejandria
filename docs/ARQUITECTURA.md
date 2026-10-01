# ARQUITECTURA — Alejandría

> **Referencia de "cómo está hecho".** Documenta estructura, modelo de datos, flujos y decisiones clave.
> Para el estado vivo y pendientes ver `ESTADO.md`. Para filosofía, reglas y "DON'Ts" ver `../CLAUDE.md`.

---

## 1. Vista general

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              ALEJANDRÍA (Docker)                         │
│                                                                          │
│  frontend ──:8888──► nginx ──► backend (FastAPI :9878→7878)             │
│                                        │        │                        │
│                        ┌───────────────┘        └────────────┐           │
│                        ▼                                     ▼           │
│                 postgres (5432, interno)             workers             │
│                        ▲        ▲                        ▲               │
│                        │        │                        │               │
│              scheduler (jobs)   │      kcc-converter (CBZ→EPUB)         │
│              (contenedor propio)│                                     │
│                                 │      flaresolverr (bypass CF)         │
└─────────────────────────────────┼────────────────────────────────────────┘
                                  ▼
        Volumen /downloads (descargas) · /library (EPUB/kindle) · /imports · /stk-data
```

| Contenedor | Puerto | Rol |
|---|---|---|
| `frontend` | 8888→80 | UI React (nginx) |
| `backend` | 9878→7878 | API FastAPI (scheduler **desactivado** aquí: `DISABLE_SCHEDULER=true`) |
| `scheduler` | — | Worker con jobs de fondo (descargas, conversión, envío, imports) |
| `kcc-converter` | — | Convierte CBZ/CBR → EPUB watcheando `/downloads` |
| `postgres` | — (interno) | BD `alejandria` / user `alejandria` |
| `flaresolverr` | 8191 | Bypass Cloudflare para ouo.io/ouo.press |

**Volumen clave:** `library` → montado en `/library`. STK tokens en `stk_data` → `/stk-data` (fuera de `/app` para sobrevivir al bind mount).

> El backend monta `./backend:/app` y el scheduler `./backend:/app/backend` **como live source**: cambios en el código Python no requieren rebuild (solo restart).

---

## 2. Modelo de datos (PostgreSQL + SQLAlchemy)

Tablas principales (en `backend/app/models/`):

| Tabla | Model | Clave | Notas |
|---|---|---|---|
| `users` | `User` | id | `is_admin`, `is_active`, `must_change_password`, prefs de calidad/hosts, cuenta STK (email/dispositivo) |
| `manga` | `Manga` | id | Unique(`user_id`,`anilist_id`), Unique(`user_id`,`slug`). Metadata AniList. `reading_status`, `monitored`, `auto_download`, `is_resolving` |
| `chapters` | `Chapter` | id | FK→manga. `number` (Float, soporta 1.5), `download_url`, `download_host`, `volume_range_start/end` (bundle de tomos), `status`, `file_path`, `converted_path`, `retry_count` |
| `comics` | `Comic` | id | Unique(`user_id`,`comicvine_id`). Metadata ComicVine. `source_urls` (dict scraper→url), `sources_searched`, `reading_status` |
| `comic_issues` | `ComicIssue` | id | FK→comics. `issue_number`, `download_url`, `link_status`, **bundle**: `bundle_id` (hash MD5 16 de URL), `bundle_title`, `bundle_range`, `is_bundle_master`. `status`, `converted_path` (`\|` separa partes) |
| `books` | `Book` | id | Metadata Google Books. `reading_status` |
| `book_chapters` | `BookChapter` | id | FK→books |
| `download_queue` | `DownloadQueue` | id | Polimórfico: `chapter_id` / `book_chapter_id` / `comic_issue_id` + `content_type`. `progress`, `bytes_downloaded`, `retry_count`, `max_retries=3`, `next_retry_at` (backoff), `priority` |
| `app_settings` | `AppSettings` | — | Ajustes globales |
| `system_logs` | `LogEntry` | — | Diagnóstico persistente (panel admin) |

### Estado de un item (máquina de estados)
```
pending → downloading → downloaded → converting → converted → sent
   └──────────┴──────────────┴──► error   (con retry/backoff)
```
- `Chapter.is_downloaded`: status ∈ {downloaded, converting, converted, sent}
- `DownloadQueue.can_retry`: status==failed y retry_count < max_retries
- **Backoff exponencial** (V2): 5min → 30min → 2h → 24h, controlado por `next_retry_at`.

### Relaciones
- `Manga 1─N Chapter` (cascade all, delete-orphan, lazy=dynamic)
- `Comic 1─N ComicIssue` (idéntico)
- `Book 1─N BookChapter` (idéntico)
- Todo content tiene `user_id` → **aislamiento multi-usuario**. Los endpoints de queue verifican ownership por JOIN (fix IDOR).

---

## 3. Backend (FastAPI)

**Entrada:** `backend/app/main.py`. Lifespan inicia DB + scheduler (salvo `DISABLE_SCHEDULER`). Docs (`/docs`, `/redoc`, `/openapi.json`) solo si `DEBUG=True`. CORS vía `CORS_ORIGINS_STR`.

**Patrón CRÍTICO de config:** `app/config.py` exporta `get_settings()` (con `@lru_cache`).
- ✅ `from app.config import get_settings; settings = get_settings()`
- ❌ `from app.config import settings` → **ImportError en arranque**.

### Routers (prefijos en `app/api/v1/`)
Todos montados bajo `settings.API_V1_PREFIX` = `/api/v1`.

| Prefijo | Archivo | Qué hace |
|---|---|---|
| `/auth` | `auth.py` | login, registro, JWT, rate limiting (10/15min por IP) |
| `/manga` | `manga.py` | search (AniList + scrapers en paralelo), add, CRUD, capítulos, descargas, **web reader** (`/chapters/{id}/pages/{idx}?token=…`), reading-status, stats, discover trending/popular |
| `/comics` | `comic.py` | search (ComicVine ES→EN), add, issues, **bundles** (`/issues/download`, `search-sources`), send-to-kindle, reading-status, stats |
| `/books` | `books.py` | search (Google Books + Lectulandia), add, capítulos, descargas, send-to-kindle, reading-status |
| `/queue` | `queue.py` | cola de descargas (con ownership por user_id) |
| `/kindle` | `kindle.py` | STK: status, signin-url, authorize, devices, send, logout |
| `/kindle-sync` | `kindle_sync.py` | list, download, mark-downloaded (auth) |
| `/import` | `import_api.py` | status, process, retry (carpeta /imports) |
| `/recommendations` | `recommendations.py` | motor local sin IA |
| `/notifications` | `notifications.py` | count, mark-seen, **SSE stream** |
| `/export` | `export.py` | export/import JSON de biblioteca |
| `/upload` | `upload.py` | `POST /upload` multipart (CBZ/CBR/EPUB/PDF/ZIP, 2GB) |
| `/opds` | `opds.py` | feed OPDS (manga/comics/books) |
| `/activity` | `activity.py` | actividad reciente |
| `/settings` | `settings.py` | settings de usuario + terabox-status |
| `/system` | `system.py` | status, health, config, process-queue/conversions, cleanup, stats, logs (admin) |

### Auth (patrones en `app/core/deps.py`)
```python
current_user: User = Depends(get_current_user)   # cualquier usuario logueado
admin: User = Depends(get_admin_user)            # solo admin
# system.py define require_admin localmente
```

### Services (lógica de negocio en `app/services/`)
Los más grandes/importantes (líneas):
- `scheduler.py` (1651) — orquestación de todos los jobs (ver §6)
- `comic_service.py` (1871) — cómics, **bundles**, smart link assignment, descarga de carpetas MediaFire/MEGA
- `downloader.py` (~1000) — descarga multi-host (mega, mediafire, gdrive, sendnow, terabox, ouo, uii, shortener genérico)
- `generic_downloader.py` (705) — fireload, 1fichier, mediafire, mega, gdrive vía Playwright
- `ouo_resolver.py` (734) — resolver ouo.io/ouo.press (FlareSolverr + Playwright)
- `terabox_bypass.py` — TeraBox (path traversal corregido con `Path(filename).name`)
- `stk_kindle_sender.py` — envío STK por usuario. **Modelo de sesión (verificado en la fuente de stkclient):** `Client.dumps()` persiste SOLO `adp_token` + RSA key (`device_info`), NO access/refresh token. El access token OAuth2 se usa UNA vez para registrar el dispositivo y luego se descarta; todas las llamadas se firman en vivo con RSA+`adp_token`. Por tanto el `adp_token` es de **larga duración y NO expira por calendario** → la sesión solo muere si el código llama a `logout()`. El auto-logout está prácticamente desactivado (umbral 20 fallos definitivos, `deviceinfotoken` ya no cuenta, `heartbeat()` no-destructivo).
- `content_matcher.py` — anti-duplicados (Jaccard ≥0.8)
- `recommender.py` — recomendaciones locales por perfil
- `import_watcher.py` — procesa /imports
- `metadata_enricher.py` — refresh semanal AniList/ComicVine/Google Books (+ Open Library fallback)
- `anilist.py`, `comicvine.py`, `google_books.py`, `openlibrary.py` — clientes de metadata
- `circuit_breaker.py`, `host_manager.py` — resiliencia / prioridad de hosts
- `translator.py` — traducción ES→EN de títulos

### Scrapers (subdirectorios en `app/services/`)
- **Manga** (archivos sueltos, no carpeta): `tomosmanga_search.py` (primario + scorer), `mangaycomics_scraper.py` (paralelo), `scraper.py` (TuMangaOnline fallback)
  - Scorer (`tomosmanga_search.py`): re-ediciones **+25** (antes -50), reciente **+5/año desde 2015**, color -20, guía -100.
- **Cómics** (`comic_scrapers/`): `zonacomics.py` (Playwright + ouo automático), `cbrcomics.py` (aiohttp + redirect resolution), `megacomics.py` (search + table parsing + ouo), `title_parser.py`, `base.py`
- **Libros** (`book_scrapers/`): `lectulandia.py`, `epubera.py`, `playwright_scraper.py`, `base.py`

**Prioridad de hosts:** Google Drive > MediaFire > MEGA (por rate limits ~6h/5GB).

---

## 4. Frontend (React + Vite + Tailwind)

**Entrada:** `frontend/src/App.jsx`. Rutas (React Router):

| Ruta | Componente | Nota |
|---|---|---|
| `/login` | `Login` | público |
| `/change-password` | `ChangePassword` | obligatorio tras primer login |
| `/device-setup` | `DeviceSetup` | wizard tras cambiar password |
| `/` | **`Discover`** | inicio = recomendaciones (fallback trending AniList si biblioteca vacía) |
| `/dashboard` | `Home` | stats de biblioteca + actividad |
| `/library` | `Library` | con filtro "Siguiendo" (watchlist) |
| `/search` | `Search` | tabs manga/comics/libros, cards custom con badges de disponibilidad |
| `/manga/:id` | `MangaDetails` | |
| `/comics` · `/comics/:id` | `Comics` · `ComicDetails` | |
| `/books` · `/books/:id` | `Books` · `BookDetails` | |
| `/queue` | `Queue` | filtros por tipo, Reset Stuck |
| `/settings` | `Settings` | cuenta Kindle, prefs, logs (admin) |
| `/upload` | `Upload` | sube archivo y crea item |
| `/manga/:mangaId/chapters/:chapterId/read` | `MangaReader` | fullscreen, sin navbar |
| `/admin/users` | `AdminUsers` | solo admin |
| `/discover` | → redirect a `/` | |

**Flujo de guardado (layouts):** `ProtectedLayout` (usuario normal) y `AdminLayout` (redirige a `/admin/users`). Ambos aplican `ProtectedRoute` + `ErrorBoundary` + `Navbar`. Si `mustChangePassword` → force a change-password. Si `!deviceSetupCompleted` → force a device-setup.

### Componentes compartidos (unificación V2)
- **`ContentDetailPage`** — layout de detalle unificado (banner, cover, info, badges, acciones, stats, progreso). `MangaDetails`/`ComicDetails`/`BookDetails` construyen props y lo reutilizan.
- **`ContentCard`** — card con config por tipo. Colores: manga `#3B82F6`, comics `#EF4444`, books `#10B981`. Menú 3-puntos con reading-status.
- **`ContentGrid`** — grid con skeletons, empty states, key extraction por tipo.
- También existen cards/grids por tipo (`MangaCard`, `ComicCard`, `BookCard`, `*Grid`, `*List`) usados en listas específicas.

**Servicios:** `frontend/src/services/api.js` (cliente axios único). **Utils:** `utils/sanitizeUrl.js` → `sanitizeUrl()` devuelve `#` si el protocolo no es http/https (usado en `ContentDetailPage`, `ChapterList`, `BookChapterList`, `ComicIssueList`). **Context:** `contexts/AuthContext.jsx` (`useAuth`).

**Estética (rediseño reciente):** tokens en `tailwind.config.js` + `index.css`; Playfair Display (títulos) + Outfit (UI); negro profundo + acento dorado; animaciones `shimmer` y `page-in`. Detalle en `docs/superpowers/`.

---

## 5. Workers

### scheduler (`workers/scheduler/main.py` → `app/services/scheduler.py`)
Contenedor propio. Inicia `ContentScheduler(check_interval_hours, download_dir, library_dir)` y espera señales (SIGTERM/SIGINT).

**Jobs programados** (`ContentScheduler.start()`, APScheduler):

| Job | Trigger | Función |
|---|---|---|
| `check_new_chapters` | cada `CHECK_INTERVAL_HOURS` (def 6h) | nuevos capítulos manga (solo status RELEASING/None) |
| `process_downloads` | cada 5min | procesa `download_queue` (`_process_manga/book/comic_download`) |
| `process_conversions` | cada 10min | dispara conversión (`_check_or_convert_chapter/comic_issue`, local o KCC) |
| `send_to_kindle` | cada 15min | envía EPUBs convertidos vía STK |
| `check_comic_sources` | cada 6h | busca fuentes de cómics en scrapers + smart link assignment |
| `retry_failed_downloads` | cada 1h | reintenta con backoff exponencial |
| `process_imports` | cada 5min | carpeta `/imports` |
| `refresh_metadata` | dom 03:00 | enriquece metadata semanalmente |
| `cleanup_old_files` | diario 03:00 | borra archivos viejos (respetando `converted_path` con `\|`) |
| `stk_health` | cada 8h | heartbeat STK (no-destructivo): verifica sesión y persiste la credencial; NUNCA la borra |

Todos con `max_instances=1` (salvo cleanup) para no solaparse.

### kcc-converter (`workers/kcc-converter/converter.py`, 1354 líneas)
Watchea `WATCH_DIR=/downloads`, escribe en `OUTPUT_DIR=/library/kindle`.
- **Manga mode:** flag `-m` (derecha→izquierda), factor estimación 1.3x.
- **Comic mode:** sin `-m` (izquierda→derecha), factor 2.5x.
- Si el EPUB resultante >180MB, **divide en partes** (por eso `converted_path` puede tener varias rutas separadas por `|`).
- Respeta lock files `.downloading` para no coger archivos a medio bajar.

---

## 6. Flujos de datos clave

### Añadir y descargar un comic (el más complejo)
1. Frontend: `Buscar → Comics` → elige un volumen de ComicVine.
2. Backend `comic.py`: si tiene `comicvine_id` usa su metadata; si es virtual (id=0) traduce ES→EN y busca en ComicVine. Crea `Comic` + `ComicIssue`s en BD.
3. Scheduler `check_comic_sources` (o `search-sources` manual): busca en ZonaComics/CBRComics/MegaComics en paralelo, detecta bundles, hace **smart link assignment**:
   - links con `issue_range` → asigna por rango (bundle multi-issue)
   - suficientes links sin range → 1:1 secuencial
   - pocos links → bundle todos los issues con el mejor link
4. **NO auto-descarga.** El usuario pulsa **Descargar** (elige issues; el bundle selecciona todos).
5. `DownloadQueue` → `process_downloads` → `downloader.py` (resuelve acortadores ouo/uii, elige host por prioridad, lock file). Si el master de un bundle se descarga, marca descargados TODOS los issues del bundle.
6. KCC convierte CBZ/CBR → EPUB (dividiendo si >180MB).
7. `send_to_kindle` envía vía STK.

### Lector web (manga)
`GET /manga/{id}/chapters/{ch_id}/pages/{idx}?token=<jwt>` — el token va en **query param** porque `<img src>` no puede enviar header `Authorization`.

### Búsqueda enriquecida (V6)
Al buscar, se consulta el scraper **en paralelo** (timeout 8s) para cada resultado de metadata y se anotan `scraper_sources` / `scraper_url` / `scraper_tomo_count`. Frontend muestra badge "✓ Encontrado" verde o "Sin fuentes" gris. Match flexible: exacto OR intersección de keywords ≥ min(2, len/2).

---

## 7. Decisiones y patrones que hay que respetar

- **Plataforma en español.** Usuarios buscan en español; scrapers son ES; ComicVine/AniList devuelven EN. **Traducir** (ES→EN) antes de buscar metadata. Términos comunes ya traducidos en `translator.py`.
- **No auto-descargar cómics**: el usuario decide.
- **No verificar acortadores con HEAD**: detectarlos y guardar sin verificar.
- **No usar MEGA como prioridad** (rate limits).
- **Bundles**: misma URL en varios issues → mismo `bundle_id` (hash MD5 16 de la URL). El master descarga por todos.
- **`converted_path` con `|`** puede contener varias partes (EPUB dividido).
- **Sanitizar URLs** en el frontend con `sanitizeUrl()`.
- **Ownership multi-usuario** en todos los endpoints de content/queue.
- **Config**: siempre `get_settings()`, nunca importar `settings`.

---

## 8. Mapas de archivos (dónde está cada cosa)

```
backend/app/
  main.py                 # app FastAPI + lifespan
  config.py               # get_settings()  ⚠️ patrón crítico
  database.py             # init_db, SessionLocal, Base
  api/v1/                 # routers (ver §3)
  models/                 # User, Manga, Chapter, Comic, ComicIssue, Book, BookChapter, DownloadQueue, AppSettings, LogEntry
  schemas/                # Pydantic (request/response)
  core/                   # deps.py (auth), security.py (JWT/bcrypt), logging.py
  services/
    scheduler.py          # ContentScheduler (jobs)        §5
    comic_service.py      # cómics + bundles               §3
    downloader.py         # descarga multi-host            §3
    generic_downloader.py # fireload/1fichier/mega/gdrive  §3
    ouo_resolver.py       # ouo.io/ouo.press               §2 ESTADO
    terabox_bypass.py     # TeraBox
    stk_kindle_sender.py  # STK por usuario
    content_matcher.py    # anti-dup (Jaccard)
    recommender.py        # recomendaciones locales
    import_watcher.py     # /imports
    metadata_enricher.py  # refresh semanal
    anilist/comicvine/google_books/openlibrary.py  # metadata
    tomosmanga_search.py  # manga primario + scorer
    mangaycomics_scraper.py / scraper.py            # manga paralelo/fallback
    comic_scrapers/       # zonacomics, cbrcomics, megacomics
    book_scrapers/        # lectulandia, epubera, playwright_scraper
frontend/src/
  App.jsx                 # rutas + layouts
  contexts/AuthContext.jsx
  components/             # ContentDetailPage, ContentCard, ContentGrid, *Card, *Grid, Navbar, …
  pages/                  # Discover, Home, Library, Search, *Details, Queue, Settings, Upload, MangaReader, …
  services/api.js         # cliente axios
  utils/sanitizeUrl.js
workers/
  scheduler/main.py       # worker scheduler
  kcc-converter/converter.py  # CBZ/CBR → EPUB
scripts/
  init-db.sql             # bootstrap BD
  migrate-*.sql / migrate-volumes.sh  # migraciones de versiones anteriores
  run-tests.sh
```