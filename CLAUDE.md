# Alejandría - Biblioteca Digital Automatizada

## 🎯 Descripción del Proyecto

Alejandría es una plataforma de gestión automatizada de contenido digital (manga, cómics, libros) con integración a Kindle. El sistema descarga, convierte y envía contenido automáticamente.

## 🏗️ Arquitectura

### Stack Tecnológico
- **Backend**: FastAPI + Python 3.11 + SQLAlchemy
- **Frontend**: React + Vite + Tailwind CSS
- **Base de Datos**: PostgreSQL
- **Workers**:
  - KCC Converter (CBZ → EPUB para Kindle)
  - Scheduler (descarga y conversión automática)
- **Servicios Externos**:
  - AniList (metadata de manga)
  - ComicVine (metadata de cómics)
  - Google Books (metadata de libros)
  - STK (Send to Kindle)

### Docker & Naming
- **Volumen de datos**: `library` (montado en `/library`)
- **Base de datos**: usuario `alejandria`, db `alejandria`
- **Clase scheduler**: `ContentScheduler` (param `library_dir`)
- **Migración desde versiones anteriores**: Ver `scripts/migrate-volumes.sh` y `scripts/migrate-db-user.sql`

### Estructura de Directorios
```
backend/
  app/
    api/v1/          # Endpoints REST
    models/          # SQLAlchemy models
    services/        # Lógica de negocio
      manga_scrapers/     # Scrapers de manga
      comic_scrapers/     # Scrapers de cómics
      book_scrapers/      # Scrapers de libros
workers/
  kcc-converter/   # Worker de conversión CBZ → EPUB
  scheduler/       # Worker de descarga automática
frontend/
  src/
    pages/         # Páginas React
    components/    # Componentes compartidos (ContentDetailPage, ContentCard, ContentGrid)
    services/      # Cliente API
```

### Frontend Unificado (V2)
Componentes compartidos por manga, cómics y libros:
- **ContentDetailPage**: Layout de detalle unificado (banner, cover, info, badges, acciones, stats, progreso)
- **ContentCard**: Card con config por tipo (colores: manga=#3B82F6, comics=#EF4444, books=#10B981)
- **ContentGrid**: Grid con skeletons, empty states, y key extraction por tipo
- Las páginas de detalle (MangaDetails, ComicDetails, BookDetails) construyen props y pasan a ContentDetailPage
- Queue.jsx tiene filtros por tipo de contenido (Manga/Comics/Libros)

## 🎨 Filosofía del Proyecto

### IMPORTANTE: Plataforma en ESPAÑOL
- **Todos los usuarios buscan en español**
- Los scrapers son de sitios en español (ZonaComics, CBRComics, MangayComics, etc.)
- ComicVine/AniList devuelven metadata en inglés
- **Solución**: Traducir automáticamente términos comunes para obtener metadata

### Principios de Diseño
1. **Automatización total**: El usuario solo añade → el sistema descarga, convierte y envía
2. **Multi-source**: Busca en múltiples scrapers para redundancia
3. **Bundles inteligentes**: Detecta colecciones (TPB, HC, "Completo") para descargar todo de una vez
4. **Priorización de hosts**: Google Drive > MediaFire > MEGA (por rate limits)

## 📚 Sistemas Implementados

### 1. Manga (✅ Funcional)
- **Metadata**: AniList
- **Scrapers**: MangayComics
- **Conversión**: CBZ → EPUB via KCC
- **Envío**: STK (Send to Kindle)

### 2. Libros (✅ Funcional)
- **Metadata**: Google Books
- **Scrapers**: Lectulandia, Epubera
- **Formato**: EPUB directo
- **Envío**: STK (Send to Kindle)

### 3. Cómics (✅ Funcional)
- **Metadata**: ComicVine
- **Scrapers**:
  - ✅ ZonaComics (Playwright + resolución ouo.io automática)
  - ✅ CBRComics (aiohttp + cbrcomicsweb.space redirect resolution)
  - ✅ MegaComics/MegaComicsTV3 (aiohttp search + table parsing + Playwright ouo.io)
- **Link Assignment**:
  - ✅ Smart: `issue_range` metadata from scraper tables (e.g., "#1 - #2" → bundle)
  - ✅ Sequential: 1:1 mapping when enough resolved links without issue_range
  - ✅ Bundle: All issues share best link when few resolved links
  - ✅ NO auto-download: User must manually trigger downloads
- **Download**:
  - ✅ MediaFire (individual + folders via Playwright)
  - ✅ MEGA individual (mega.py --no-deps + tenacity>=8.2)
  - ✅ MEGA shared folders (megatools CLI + Playwright M.d listing)
  - ✅ CBRComics pages (decode base64 data-link → MEGA folder URL)
  - ✅ ouo.io resolver, lock files, temp dir pattern
- **Conversión**: ✅ CBZ/CBR → EPUB via KCC (comic mode sin -m, factor 2.5x)
- **Envío**: STK (Send to Kindle)

## 🔑 Conceptos Clave

### Sistema de Bundles
Los cómics vienen en colecciones (TPB, HC, "Completo"):
- **Bundle**: Una descarga que contiene múltiples issues
- **Bundle Master**: El primer issue del bundle que ejecuta la descarga
- **Bundle ID**: Hash MD5 del URL de descarga (16 chars)
- Cuando el master se descarga, marca TODOS los issues del bundle como descargados
- **Auto-detección**: Si múltiples issues comparten la misma download_url, se crea bundle automáticamente
  - En `_search_scrapers_for_comic()` (post-procesamiento)
  - En `download_issues()` endpoint (al momento de descargar)
  - Via `issue_range` metadata: MegaComics table parsing (e.g., "#1 - #2" → same link → bundle)
- **Smart Link Assignment** (`fetch_volume_from_scraper`):
  1. Si links tienen `issue_range` → asigna por rango (bundles para multi-issue)
  2. Si hay suficientes links sin issue_range → asigna 1:1 secuencialmente
  3. Si pocos links → bundle todos los issues con el mejor link
- **Frontend (como manga)**: Seleccionar un issue del bundle selecciona TODOS
  - Badge morado "Bundle (X issues)" en cada issue
  - Highlight visual en issues del mismo bundle al seleccionar uno

### Cross-Language Matching
Búsquedas en español → Metadata en inglés:
- Usuario busca: "Star Wars Caballeros"
- Sistema traduce: "Star Wars Knights"
- ComicVine devuelve: "Star Wars: Knights of the Old Republic"
- Sistema usa metadata completa de ComicVine

### URL Shorteners
Muchos sitios usan acortadores:
- **ouo.io / ouo.press**: ZonaComics los resuelve automáticamente con Playwright (2-step form bypass)
  - También: `ouo_resolver.py` con bypass-ouo library + curl_cffi fallback
- **uii.io / wordcount.im**: reCAPTCHA (2captcha o manual)
- **Detección**: ZonaComics resuelve ouo.io automáticamente; otros acortadores se guardan y resuelven al descargar

## 🛠️ Comandos Útiles

```bash
# Iniciar servicios
docker compose up -d

# Ver logs
docker compose logs backend --tail 100
docker compose logs kcc-converter --tail 100

# Reiniciar servicios
docker compose restart backend

# Base de datos (user: alejandria, db: alejandria)
docker compose exec -T postgres psql -U alejandria alejandria -c "SELECT * FROM comics LIMIT 5;"

# Ver bundles
docker compose exec -T postgres psql -U alejandria alejandria -c \
  "SELECT c.title, ci.issue_number, ci.bundle_title, ci.is_bundle_master
   FROM comic_issues ci JOIN comics c ON ci.comic_id = c.id
   WHERE ci.bundle_id IS NOT NULL
   ORDER BY c.id, ci.issue_number::int;"

# Migración (solo instalaciones existentes)
bash scripts/migrate-volumes.sh        # Volumen manga → library
docker compose exec -T postgres psql -U manga alejandria < scripts/migrate-db-user.sql  # Usuario manga → alejandria
```

## 📖 Flujo de Trabajo

### Añadir un Cómic
1. Usuario busca en frontend (español)
2. Sistema:
   - Busca en ComicVine
   - Busca en scrapers directamente (resultados virtuales)
   - Muestra volumes individuales como cards
3. Usuario hace clic en "Añadir"
4. Backend:
   - Si tiene ComicVine ID: usa metadata de ComicVine
   - Si es virtual (ID=0): traduce y busca en ComicVine
   - Crea comic + issues en DB
5. Scheduler (background):
   - Busca fuentes en scrapers
   - Detecta bundles y asigna links (smart assignment con issue_range)
   - NO auto-descarga: usuario debe iniciar descargas manualmente
6. Usuario inicia descarga manualmente desde el frontend
7. KCC Worker:
   - Detecta archivos descargados (respeta lock files `.downloading`)
   - Comic mode: sin flag `-m` (izquierda→derecha), factor estimación 2.5x
   - Manga mode: con flag `-m` (derecha→izquierda), factor estimación 1.3x
   - Convierte CBZ/CBR → EPUB
   - Si >180MB, divide automáticamente en partes
8. Scheduler:
   - Detecta EPUBs convertidos
   - Envía a Kindle via STK

## 🎯 Reglas Importantes

### DO's ✅
- Usar Playwright para sitios con JavaScript/acortadores (ZonaComics resuelve ouo.io automáticamente)
- Detectar bundles automáticamente (TPB, HC, "Completo", "[X Tomos]", misma URL en múltiples issues)
- Traducir búsquedas de español → inglés para ComicVine
- Priorizar Google Drive > MediaFire > MEGA
- Usar búsqueda directa en scrapers para resultados en español
- Auto-crear bundles cuando múltiples issues comparten la misma download_url

### DON'Ts ❌
- NO auto-descargar comics al encontrar links (usuario decide cuándo descargar)
- NO verificar links de acortadores con HEAD requests
- NO usar MEGA como prioridad (rate limits ~6h/5GB)
- NO crear comics sin intentar traducir primero
- NO duplicar volumes en frontend (deduplicate por URL)
- NO forzar verificaciones que rompen el flujo
- NO guardar URLs de páginas de scrapers como download_url (resolver a MEGA/MediaFire real)

## 📝 Variables de Entorno Importantes

```env
# ComicVine
COMICVINE_API_KEY=tu_key_aqui

# STK (Send to Kindle)
STK_EMAIL=tu_email
STK_PASSWORD=tu_password

# Captcha (opcional, para uii.io)
CAPTCHA_API_KEY=tu_2captcha_key
```

## 🔧 Troubleshooting

### "Link inactive" en logs
- **Causa**: Intentando verificar acortadores directamente
- **Solución**: Acortadores deben detectarse y guardarse sin verificar

### Volumes triplicados en frontend
- **Causa**: Deduplicación por comic en vez de por volume.url
- **Solución**: Map por volume.url

### Comic sin metadata (publisher="Unknown")
- **Causa**: No está traduciendo para buscar en ComicVine
- **Solución**: Usar `_translate_comic_title()` antes de buscar

### 0/X issues have download_url
- **Causa**: Links no se guardan por verificación fallida
- **Solución**: Revisar logs, probablemente acortadores

## 🔍 Búsqueda Enriquecida (V6)

### Manga Search
- **Backend** (`manga.py` search endpoint): Tras buscar en AniList, lanza `MangayComicsScraper.search_manga()` en paralelo para cada resultado (via `run_in_executor`, timeout 8s)
- **Matching**: Keyword matching (mismas reglas que `quick_check_availability` de comics): stop words filtradas, intersección de keywords ≥ 2 o match exact
- **Schema** (`MangaSearch`): Nuevos campos `scraper_sources: List[str]`, `scraper_tomo_count: int`, `scraper_url: Optional[str]`
- **Frontend**: Cards custom en `Search.jsx` (no `ContentCard` genérico) — badge "✓ Encontrado" verde si hay scraper, "Sin fuentes" gris si no, badgets "📚 N tomos" y "🌐 MangayComics"

### Book Search
- **Backend** (`books.py` search endpoint): Lectulandia se busca siempre en `source='all'`; resultados se indexan por título normalizado. Los resultados de Google Books se anotan con `scraper_sources` y `scraper_url` si hay match de prefijo (35 chars)
- **Schema** (`GoogleBooksSearch`): Nuevos campos `scraper_sources: List[str]`, `scraper_url: Optional[str]`
- **Frontend**: Cards custom en `Search.jsx` — badge "✓ EPUB disponible" verde si Lectulandia o Epubera, "Sin EPUB conocido" gris si solo Google Books, badges "🌐 Lectulandia" / "🌐 Epubera"

### Patrón clave (idéntico a comics)
- Búsqueda de scrapers SIEMPRE en paralelo (asyncio.gather / run_in_executor)
- Timeout 8s para no bloquear si el scraper está lento
- Match flexible: exact match OR keyword intersection ≥ min(2, len/2)
- Frontend deduplica por `anilist_id` (manga) o `google_books_id || source_url` (libros)

## 📚 Skills y Workflow

Ver **`skills.md`** para reglas de workflow, gestión de tareas y principios core.

## 🎓 Recursos

- **Skills**: `skills.md` (workflow, subagents, task management, core principles)
- **Memory**: `~/.claude/projects/c--Users-kitos-Desktop-Alejandria/memory/MEMORY.md`
- **Logs de Sesiones**: `SESION_*.md`
- **Pendientes**: `PENDIENTES_*.md`
- **Diseño de Sistemas**: `*_DESIGN.md`
