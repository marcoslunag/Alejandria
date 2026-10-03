# Mejoras Alejandría — Roadmap 2026-10-02

Documento de trabajo para cerrar sesiones: estado de cada mejora, diseño y próximos pasos.
Ver también `SESION_2026-10-01_SCRAPER_REMEDIATION.md` (contexto de rendimiento de scrapers).

## Contexto verificado (2026-10-02)

- Rendimientos actuales (production): manga search **29.4s** · comic search **34.4s** · book search ~18s
  → el dolor nº1 es la espera total (spinner vacío todo el tiempo).
- La búsqueda ya va por Enter/botón (no keystroke) → no hace falta debounce.
- Imágenes ya `loading="lazy"`; `get_library` (cómics) sin N+1 (query única + count).
- `opds.py` YA existe en `backend/app/api/v1/` (no es feature nueva).
- Frontend: no hay `dark:` (sin modo oscuro), sin virtualización, sin Web Push (polling de badges 60s).
- Traductor: caché solo en memoria (se pierde al restart), endpoint free de Google con 429 frecuentes,
  `translate_batch` sin usar. deep-translator es síncrono (bloquea si no va en thread).
- STK: sin auto-send de libros (solo manga/cómics); fallos DeviceInfoToken solo visibles como 500 al enviar.

---

## P0 — Gran impacto, esfuerzo bajo/medio

### 1. Búsqueda progresiva + caché  ✅ IMPLEMENTADA (pendiente verificación production)
- [x] Diseño (abajo)
- [x] `app/services/search_jobs.py` — jobs en memoria con TTL (10 min, limpieza lazy, ownership por user_id)
- [x] `manga.py` — split metadata/scrapers + `GET /manga/search/{job_id}` (fase scrapers = closure `run_scraper_phase`)
- [x] `books.py` — split GB/scrapers + `GET /books/search/{job_id}` (fase scrapers = `_enrich_book_search_results` con `SessionLocal()` propia)
- [x] `comic.py` — split ComicVine/availability + `GET /comics/search/{job_id}` (fase = closure `run_availability_phase`)
- [x] Frontend `api.js` (`getSearchStatus` en los 3 APIs) + `Search.jsx` (polling 2s, guard de generación `searchSeqRef`, cap 90s, indicador "Comprobando fuentes…")
- [ ] Verificación production (timing inicial <3s, badges se rellenan después)
- [ ] (Opcional, después) caché de resultados con TTL 10–15 min

**Notas de implementación (2026-10-03):**
- Endpoint de estado: `GET /{tipo}/search/{job_id}` (2 segmentos, no colisiona con `/{id}`).
- El job se completa SIEMPRE (aunque la fase falle) → el frontend deja de hacer polling.
- `source="google"|"openlibrary"` (books) y `check_availability=false` (cómics) → sin job (`search_id=null`).
- Backend 1 worker uvicorn → in-memory OK. Si se escala a N workers, migrar jobs a Redis/DB.

**Diseño aprobado:**
- Cada endpoint de búsqueda hace la **fase de metadata primero** (AniList / Google Books / ComicVine, ~2-3s),
  crea un `SearchJob` en memoria (uuid4, TTL 10 min), lanza la **fase de scrapers en background**
  (`asyncio.create_task`) y devuelve YA los resultados de metadata + `search_id` + `status: "in_progress"`.
- El background task enriquece (badges `scraper_sources`, `scraper_url`, `scraper_tomo_count`,
  disponibilidad, scores) y deja `status: "complete"` + resultados finales en el job.
- El frontend pinta cards de inmediato y hace polling (1.5-2s) al endpoint de estado hasta `complete`,
  mergeando por `anilist_id` (manga), `google_books_id||source_url` (libros), título/URL (cómics).
- Respuesta: wrapper `{results: [...], search_id: str|null, status: "in_progress"|"complete"}`.
  Si la fase de scrapers es trivial/ya terminada (o falla al arrancar) → `status: "complete"` directo.
- **OJO**: la fase background NO puede usar la DB session del request (se cierra). Si necesita DB
  (p. ej. `in_library`), se calcula en la fase metadata o se abre sesión nueva dentro del task.
- Limpieza de jobs: lazy (al crear/leer) — no scheduler.

### 2. Caché de búsqueda (TTL 10–15 min)  ⬜ PENDING
Tabla `search_cache(query_hash, tipo, payload json, created_at)`; check al inicio de cada search.

### 3. Traducción: caché persistente + batch  ⬜ PENDING
- Tabla `translations(source_hash, original, traducido)` — sobrevive restarts, compartida enricher/detalle.
- `translate_batch` para el enricher semanal (N descripciones en 1 llamada a Google).

### 4. STK proactivo  ⬜ PENDING
- Tras N fallos `DeviceInfoToken` → flag `stk_needs_reauth` → banner naranja en Settings/Home
  "Sesión de Amazon caducada — Reconectar"; botón enviar deshabilitado con explicación (no 500).
- Mostrar "último envío exitoso" por usuario.

---

## P1 — Coherencia y funcionalidad

| # | Mejora | Estado |
|---|--------|--------|
| 5 | Auto-send de libros en scheduler (`auto_send_to_kindle` + EPUB) | ⬜ |
| 6 | Modo oscuro (Tailwind `dark:` + toggle persistido) | ⬜ |
| 7 | Web Push en PWA (service worker existe; fin del polling 60s de badges) | ⬜ |
| 8 | Web reader para EPUB (epub.js) + tamaño de fuente/tema | ⬜ |
| 9 | Paginación/infinite scroll en grids grandes | ⬜ |

## P2 — Rendimiento y datos

- **10.** Sesión `aiohttp` compartida en `anilist.py` (hoy `ClientSession` por query)
- **11.** Índices DB: `comic_issues(comic_id, issue_number)`, `chapters(manga_id, number)`,
  `download_queue(user_id, status)` — verificar con `EXPLAIN`
- **12.** Proxy de covers con caché local + `ETag`/`Cache-Control`
- **13.** Telemetría éxitos/fallos por scraper/host → priorización dinámica de fuentes
- **14.** Retención de disco: borrar CBZ tras conversión+envío OK (configurable) + dashboard de uso

## P3 — Calidad y ops

- **15.** Tests pytest de lógica pura: scorer, bundles, clasificador fallos STK, rate-limiter traductor
- **16.** Backups automáticos: `pg_dump` + JSON semanal a `/backups` con retención
- **17.** Rate-limit endpoints de búsqueda + latencia p95 en panel de logs
- **18.** Discover 2.0: "Siguiendo", "Continuar leyendo", "Añadidos recientemente"
- **19.** Unificar `MangaCard/ComicCard/BookCard` en `ContentCard`

---

## Orden de ejecución acordado

1. **#1** búsqueda progresiva (+ #2 después si tiene sentido)
2. **#3** traducción persistente
3. **#4 + #5** STK proactivo + auto-send libros
4. Estilo: **#6** modo oscuro o **#7** push, según decisión

## Comandos de deploy (recordatorio)

```bash
# LOCAL: commit + push (SIEMPRE desde local)
git add <files> && git commit -m "..." && git push
# SERVIDOR (SSH 192.168.1.112, root/primos, expect heredoc):
cd /root/Alejandria && git pull && docker compose restart backend
# Frontend cambia → rebuild:
cd /root/Alejandria && docker compose up -d --build frontend
```
