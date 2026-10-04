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

### 2. Caché de búsqueda (TTL 10–15 min)  ✅ IMPLEMENTADA (2026-10-04)
- [x] `app/models/search_cache.py` — `SearchCache(query_hash unique, tipo, payload JSON, created_at)`; registrado en `models/__init__.py`; `create_all` la crea al arrancar.
- [x] `app/services/search_cache.py` — TTL 15 min con expiración **lazy** (purge en cada `put` + borrado en `get` vencido, sin worker); `get_cached`/`put_cached` nunca lanzan (fallo = degrada a búsqueda en vivo).
  - Key: `sha256(f"{tipo}|{q.lower().strip()}|{page}|{limit}|{extras}")` — extras: manga `""`, comic `check_availability`, book `"{source}|{language}"`.
  - Payload `{"results", "total", "sources"}` se guarda **SIN estado por usuario**: `in_library`/`library_id` se recalculan en cada hit vía `annotate_in_library()` (1 query por tipo: manga por `anilist_id`, comic por `comicvine_id`, book por `google_books_id` + prefijo de título para cards de scraper).
- [x] Integración: hit al inicio de `search_manga`/`search_comics`/`search_books` (devuelve `status="complete"`, `search_id=None`); write en `_finish_*_search_job` (fase enriquecida) y en los paths sin job (`source=google/openlibrary`, `check_availability=false`, resultados vacíos).
- [ ] Verificación production (misma búsqueda <15 min → instantáneo, sin AniList/ComicVine/Google).

### 3. Traducción: caché persistente + batch  ✅ IMPLEMENTADA (2026-10-04)
- [x] `app/models/translation.py` — `Translation(source_hash unique, original, translated)`; registrado en `models/__init__.py`. `source_hash` = SHA-256(texto truncado a `max_length` y `strip`).
- [x] `app/services/translator.py` — caché por niveles: **L1** memoria → **L2** BD (`translations`) → Google (rate limiter 0.2s) → guardar L1+L2. `translate_batch` + `get_cached_translations` (bulk). `IntegrityError` al insertar = rollback silencioso (2 procesos escriben: API + scheduler). deep-translator síncrono → siempre vía `asyncio.to_thread`.
- [x] Warm-up en `metadata_enricher.py` (`run_weekly_enrichment`): tras el bucle de books, colecciona descripciones de mangas/cómics/libros, dedup, `get_cached_translations` + `translate_batch` (cap 50) vía `asyncio.to_thread`; stats `descriptions_cached`/`descriptions_translated`. El DB guarda la descripción ORIGINAL (inglés de AniList); la traducción ocurre en read; el warm-up solo calienta la caché persistente.
- [ ] Verificación production (descripciones en ES sin 429 tras primer enriquecimiento).

### 4. STK proactivo  ✅ IMPLEMENTADA (2026-10-04)
- [x] `models/user.py` — `stk_needs_reauth` (Boolean, default False) + `stk_last_sent_at` (DateTime); ALTERs en `database.py::_migrate_columns()`.
- [x] `stk_kindle_sender.py` — helpers module-level `mark_stk_needs_reauth(user_id, reason)` / `clear_stk_needs_reauth(user_id)` / `record_successful_send(user_id)` (nunca lanzan, `SessionLocal` propio). Wiring:
  - `complete_authorization` éxito → `clear_stk_needs_reauth`.
  - `send_file`: sin sesión → mark; éxito → `record_successful_send`; fallo definitivo → `logout()` + mark.
  - `get_devices`: fallo definitivo → `logout()` + mark.
- [x] `kindle.py` — `stk_status` devuelve `needs_reauth` (= flag BD **OR** `not is_authenticated()`, así también cubre usuarios que nunca se autorizaron) + `last_sent_at`. `stk_send_to_kindle`: no autenticado → **409** + `mark_stk_needs_reauth` + mensaje ES "Reconecta tu Kindle…"; fallo total → **409** con `last_error` (antes 500).
- [x] Frontend: los 3 botones de envío (`SendToKindleButton`/`BookSendToKindleButton`/`ComicSendToKindleButton`) — `useEffect` mount lee `stkStatus.needs_reauth`, `handleSend` pre-check, botón `disabled` + gris + `FaExclamationTriangle` + "Reconectar".
- [x] `Settings.jsx` — banner superior por `needs_reauth` ("Sesión de Amazon caducada"/"Kindle no configurado", botón "Reconectar"/"Configurar"); caja de estado 3 estados (orange/green/gray) + línea "Último envío exitoso"; flujo de autorización visible también con `needs_reauth`; resumen + mensaje de estado actualizados.
- [ ] Verificación production (revocar sesión de Amazon → banner naranja + envío 409 amable).

---

## P1 — Coherencia y funcionalidad

| # | Mejora | Estado |
|---|--------|--------|
| 5 | Auto-send de libros en scheduler (`auto_send_to_kindle` + EPUB) | ✅ 2026-10-04: `scheduler.py` bucle `BookChapter.status=='converted'` (limit 6, respeta `auto_send_to_kindle` + `stk_device_serial`) + `_send_book_chapter_to_kindle` (espejo de cómics: partes por `\|`, `is_authenticated()`, `title="{book.title}{vol}"`, `author=book.authors[0]`, marca `sent` solo si todas las partes OK) |
| 6 | Modo claro/oscuro + toggle persistido | ✅ 2026-10-04: la app ya era **dark-first** (tokens `dark.*` hardcodeados), así que se añadió **modo claro** (papel cálido + dorado) con toggle ☀/☾ en navbar (desktop + móvil), persistido en `localStorage('alejandria-theme')`. Implementación: bloque CSS **unlayered** bajo `html.light` en `index.css` (76 reglas, por utilidad: `text-*` oscurece, `bg-*`/`border-*` aclaran; `.card/.btn-secondary/.input/.skeleton` tocados a la clase por `@apply`; scrim del hero en variables `--tw-gradient-*`; acentos gold/rojo/colores de tipo intactos). Script inline en `index.html` aplica la clase **antes del paint** (anti-FOUC) + `theme-color` meta. `darkMode:'class'` en `tailwind.config.js` (inerte, sin variantes `dark:` usadas). Default = oscuro (identidad de la app). `npm run build` OK |
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

1. **#1** búsqueda progresiva ✅ + **#2** caché persistente ✅ (2026-10-04)
2. **#3** traducción persistente ✅ (2026-10-04)
3. **#4 + #5** STK proactivo + auto-send libros ✅ (2026-10-04)
4. Estilo: **#6** modo claro/oscuro ✅ (2026-10-04)

**Verificación local (2026-10-04):** `pytest backend/tests/` → **197 passed, 4 failed**.
Los 4 fallos son de **entorno local** (sin Playwright browser, Google Books 429 sin API key,
`/downloads` read-only, contaminación de estado de queue) — **ninguno toca el código de #2/#3/#4/#5**.
Todos los tests de `search` pasan. Nota: `httpx` quedó sin pin (`>=0.25`) y con `0.28.x` rompía
`TestClient` de starlette 0.27 (kwarg `app`); **pinado a `httpx==0.27.2`** en `requirements.txt`
para que un rebuild de Docker no rompa la suite.

## Comandos de deploy (recordatorio)

```bash
# LOCAL: commit + push (SIEMPRE desde local)
git add <files> && git commit -m "..." && git push
# SERVIDOR (SSH 192.168.1.112, root/primos, expect heredoc):
cd /root/Alejandria && git pull && docker compose restart backend
# Frontend cambia → rebuild:
cd /root/Alejandria && docker compose up -d --build frontend
```
