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
    components/    # Componentes reutilizables
    services/      # Cliente API
```

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

### 3. Cómics (🚧 En Desarrollo - 95%)
- **Metadata**: ComicVine
- **Scrapers**:
  - ✅ ZonaComics (Playwright + resolución ouo.io automática)
  - ✅ CBRComics (aiohttp, basic + Playwright data-link decode)
  - ✅ MegaComics/MegaComicsTV3 (aiohttp search + Playwright ouo.io resolution)
  - ⏸️ Marmota (pendiente)
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
docker compose logs scheduler --tail 100
docker compose logs kcc-converter --tail 100

# Reiniciar servicios
docker compose restart backend
docker compose restart scheduler

# Base de datos
docker compose exec -T postgres psql -U manga manga_arr -c "SELECT * FROM comics LIMIT 5;"

# Ver bundles
docker compose exec -T postgres psql -U manga manga_arr -c \
  "SELECT c.title, ci.issue_number, ci.bundle_title, ci.is_bundle_master
   FROM comic_issues ci JOIN comics c ON ci.comic_id = c.id
   WHERE ci.bundle_id IS NOT NULL
   ORDER BY c.id, ci.issue_number::int;"
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
   - Detecta bundles
   - Descarga (solo bundle masters)
   - Marca todos los issues del bundle
6. KCC Worker:
   - Detecta archivos descargados (respeta lock files `.downloading`)
   - Comic mode: sin flag `-m` (izquierda→derecha), factor estimación 2.5x
   - Manga mode: con flag `-m` (derecha→izquierda), factor estimación 1.3x
   - Convierte CBZ/CBR → EPUB
   - Si >180MB, divide automáticamente en partes
7. Scheduler:
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
- NO verificar links de acortadores con HEAD requests
- NO usar MEGA como prioridad (rate limits ~6h/5GB)
- NO crear comics sin intentar traducir primero
- NO duplicar volumes en frontend (deduplicate por URL)
- NO forzar verificaciones que rompen el flujo

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

## 📚 Skills Disponibles

Para este proyecto NO se requieren skills especiales, ya que:
- Todo el código es custom (no usa frameworks especiales)
- La documentación está en los archivos `.md` del proyecto
- El contexto se mantiene en `~/.claude/memory/MEMORY.md`

## 🎓 Recursos

- **Memory**: `~/.claude/projects/c--Users-kitos-Desktop-Alejandria/memory/MEMORY.md`
- **Logs de Sesiones**: `SESION_*.md`
- **Pendientes**: `PENDIENTES_*.md`
- **Diseño de Sistemas**: `*_DESIGN.md`
