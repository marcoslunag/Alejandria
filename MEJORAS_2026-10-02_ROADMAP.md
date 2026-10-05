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
| 7 | Web Push en PWA (service worker existe; fin del polling 60s de badges) | ✅ 2026-10-04: Web Push **VAPID** de fondo (app cerrada). Backend: `PushSubscription` (endpoint único, p256dh/auth) + claves VAPID P-256 **persistidas en `app_settings`** (BD, para que API y worker compartan pareja — no hay volumen compartido); `push_service.py` genera pareja base64url si falta y `send_push()` fire-and-forget (nunca lanza, borra suscripciones 404/410); endpoints `GET /push/vapid-public-key` + `POST/DELETE /push/subscribe` (upsert por endpoint, DELETE filtra `user_id` anti-IDOR). Hook en `scheduler._check_manga` tras commit (manga `monitored` → push "Nuevos capítulos"). Frontend: `sw.js` handlers `push` (showNotification con icon/tag/data.url) + `notificationclick` (focus/abrir); card "Notificaciones Push" en Ajustes (permiso + subscribe/unsubscribe + `pushsubscriptionchange` re-suscripción); `pushApi` en `api.js`. `pywebpush` en requirements (compatible con `httpx==0.27.2`). Tests `test_push.py` (9): roundtrip VAPID, auth, upsert, IDOR, never-raises |
| 8 | Web reader para EPUB (epub.js) + tamaño de fuente/tema | ✅ 2026-10-04: leer EPUB descargados en el navegador (misma UX que el reader de manga). Backend: `GET /books/{id}/chapters/{ch_id}/epub` (FileResponse `application/epub+zip`, auth por Bearer header **o** query param `token` — mismo patrón que el reader de manga; ownership por JOIN; valida que el fichero existe en disco y tiene extensión `.epub`). Frontend: `epubjs`+`jszip` en package.json; nueva página `EpubReader.jsx` con ruta fullscreen `/books/:id/read/:chapterId` (sin Navbar, como `MangaReader`): fetch del EPUB como ArrayBuffer con header Bearer → `new ePub(buffer)` (sin token en URL); controles persistidos en `localStorage` — tamaño de fuente 12–30px (A+/A−) y 3 temas (claro/sepia/oscuro) vía `themes.register/select`; navegación prev/next por botones, zonas laterales 1/4 (estilo manga), flechas/espacio de teclado; barra superior (título + capítulo + % progreso) y auto-ocultado de UI al 3s; al llegar a ≥98% marca el capítulo como leído una sola vez (`markChapterRead`). Botón "📖 Leer" en `BookChapterList` para capítulos con `file_path`; `api` (instancia axios) ahora exportada de `api.js` para el fetch con auth. Tests: +6 en `test_books.py` (stream OK + content-type, token por query, 401 sin auth, IDOR 404, 404 sin file_path, 404 fichero inexistente) |
| 9 | Paginación/infinite scroll en grids grandes | ✅ 2026-10-04: los 3 endpoints de library ya paginaban (`/manga` skip/limit, `/comics/` y `/books/library` page/limit) pero **no devolvían el total** y el frontend cargaba todo (cortes implícitos de 100/50/50 items). Backend: header **`X-Total-Count`** (total tras filtros) en `list_manga` (manga.py), `get_library` (comic.py — ya calculaba `total`) y `get_library` (books.py) — sin cambiar schemas. Frontend: hook **`useInfiniteScroll.js`** (IntersectionObserver, `rootMargin` 400px, se re-observa tras cada carga hasta llenar el viewport; guard de doble carga con `inflightRef` en cada página). Aplicado a `Library.jsx` (manga, `skip: manga.length`), `Comics.jsx` y `Books.jsx` (page-based): página inicial 50, "Cargando más..." con contador `N de TOTAL`, `hasMore` por header con fallback heurístico (página llena). Tests: +3 (`X-Total-Count` en manga con skip/limit, comics, books) |

## P2 — Rendimiento y datos

- **10.** Sesión `aiohttp` compartida en `anilist.py` ✅ IMPLEMENTADA (2026-10-04): `_execute_query` ya no crea/cierra `ClientSession` por query. `AnilistService.__init__` + `_get_session()`: sesión perezosa con `TCPConnector(limit=10, ttl_dns_cache=300)` + `ClientTimeout(total=15)` + header `Accept` a nivel sesión; recreada solo si cambia el event loop (tests) — sin awaits entre check y asignación (atómico en el loop). `close()` idempotente al que se llama en el shutdown del `lifespan` (main.py). Tests `test_anilist_session.py` (4): misma sesión entre llamadas, recreación al cambiar de loop, `_execute_query` no cierra la sesión (pool persistente), `close()` idempotente
- **11.** Índices DB ✅ IMPLEMENTADOS (2026-10-04): índices compuestos declarados en los models (`__table_args__` + `Index`) → `chapters(manga_id, number)` como `ix_chapters_manga_id_number` y `comic_issues(comic_id, issue_number)` como `ix_comic_issues_comic_id_issue_number`. Cobertura: `filter(parent_id=X).order_by(número)` en listados de capítulos/issues sin paso de orden. Migración `_migrate_columns()` (database.py) con `CREATE INDEX IF NOT EXISTS` (idempotente, PG+SQLite) para BDs existentes. **Adaptación**: `download_queue(user_id, status)` NO aplica — la tabla no tiene columna `user_id` (la cola se filtra por JOIN a `Manga/Book/Comic.user_id` + `status` del item) y `download_queue.status` ya tiene índice propio. Tests `test_db_indexes.py` (4): declaración en models, creación real vía `create_all`, `status` indexado
- **12.** Proxy de covers con caché local + `ETag`/`Cache-Control` ✅ IMPLEMENTADO (2026-10-04): nuevo endpoint `GET /covers/proxy?url=<url>` (`app/api/v1/covers.py`, registrado en `api_router`). Valida http(s) + **allowlist de hosts** (AniList/ComicVine/Google Books/Amazon) → no es proxy abierto (anti-SSRF) y **requiere auth** (`get_current_user`). Caché en disco `<LIBRARY_DIR>/covers_cache/<md5(url)>.<ext>` con **TTL 7 días**; fetch `requests` timeout 10s, máx 10 MB, solo `image/*`. Respuesta con **`ETag`** (md5 del contenido) + **`Cache-Control: public, max-age`** + **304 Not Modified** si `If-None-Match` coincide. Frontend: helper `utils/coverUrl.js` → `proxyCover(url)` (enruta http(s) al proxy, pasa relativas, sanitiza `#` en no-http) aplicado en **todos** los renders de portada: `ContentCard` (grids), `MangaCard`/`ComicCard`/`BookCard`, `ContentDetailPage` (banner+cover), `ComicIssueList`, `Navbar`, `Comics`, `Search`, `Queue`. Tests `test_covers.py` (9): auth, host no permitido, no-http, ETag+Cache-Control, 304 sin re-fetch, cache hit, no-imagen→502, upstream error→502, URLs distintas→caché distinta
- **13.** Telemetría éxitos/fallos por scraper/host → priorización dinámica de fuentes ✅ IMPLEMENTADO (2026-10-04): model `ScraperStat` (tabla `scraper_stats`: `key` `host:<id>`/`scraper:<nombre>`, successes/failures, `streak_failures`, last_error, timestamps). Servicio `app/services/scraper_telemetry.py`: `record_success/record_failure` (upsert, traga errores de BD — **nunca rompe el flujo**), `get_stats`, `reset`, `dynamic_penalty` (<5 intentos → 0; tasa <50% → +2; tasa <30% o racha ≥5 → +4) y `sort_links_dynamically`/`effective_host_priority` (prioridad estática de `host_manager` + penalización). Hooks: `downloader.py::download_chapter` (orden dinámico de URLs con fallback estático + registro por intento: éxito / no-result / excepción), `comic_service.py::search_scrapers_directly` (búsqueda con resultados → éxito, excepción → fallo, vacío → neutro), `fetch_volume_from_scraper` (links → éxito, sin links/except → fallo), `manga.py::_run_scraper` (junto al circuit breaker existente). Endpoints admin: `GET /system/scraper-stats` (stats + `with_penalty`) y `POST /system/scraper-stats/reset/{kind}/{name}`. La tabla nueva se crea sola vía `create_all` (no necesita migración manual). Tests `test_scraper_telemetry.py` (19): upsert/tasa/racha, umbrales de penalización, prioridad efectiva, reordenamiento (mediafire 20% → pasa detrás de mega), reset, endpoints admin (auth 403/401, 404, 400)
- **14.** Retención de disco: borrar CBZ tras conversión+envío OK (configurable) + dashboard de uso ✅ IMPLEMENTADO (2026-10-04): `cleanup_old_files` (scheduler) ahora usa **`settings.CLEANUP_DAYS`** (antes hardcodeaba 7) → `>0` días tras envío, `0` = inmediato, `<0` = desactivado. **Cobertura ampliada**: antes solo limpiaba manga; ahora borra CBZ/RAR + EPUB (pipe-separated) de items enviados en **manga, cómics y libros** (los de cómics/libros se quedaban en disco para siempre). Endpoint admin `GET /system/disk-usage`: tamaño real por directorio (`/downloads`, `/library`, `/library/kindle`) con breakdown por extensión + **`reclaimable`** (items con `sent_at` y archivo aún en disco, por tipo, con bytes/MB + `cleanup_days` vigente). Tests `test_disk_retention.py` (10): cutoff respeta CLEANUP_DAYS (7/0/-1), comics+books limpiados, items sin `sent_at` intactos, EPUB multi-parte pipe-separated, endpoint (estructura, reclaimable real, 403/401)

## P3 — Calidad y ops

- **15.** Tests pytest de lógica pura: scorer, bundles, clasificador fallos STK, rate-limiter traductor ✅ IMPLEMENTADO (2026-10-04): `test_pure_logic.py` (30 tests, sin red/BD). **Scorer** (`TomosMangaSearch.find_best_match` con `search` mockeado): re-edición +25 gana, año 2023 > 2018, más tomos gana, guía -100, color -20, spin-off -80, 'completo' +30, vacío → None, 1 resultado → directo. **Bundles** (`detect_bundle`): `#1-30`, `#4-#12`, `[12/12]`, `[5 de 5]`, `[9 Tomos]`, `[80 números]`, rango invertido → None, 'Vol. 4' → None, 'collects #13-#15', 'collects issues #13 - #15' (lo captura el patrón de rango), 'Complete Collection' + `count_of_issues`, '#4' solo → None. **STK** (`STKKindleSender`): señales definitivas (adp_token/device not registered/customer not found), transitorios (403/503/timeout/connection) NO borran sesión, error no clasificado → intacta, burst <120s cuenta como 1 operación, `MAX_CONSECUTIVE_FAILURES` (20) → True en el 20º, `_reset_failure_count` a 0. **Rate-limiter** (`_TranslateRateLimiter`): 1ª llamada inmediata, 5 llamadas espaciadas ≥50ms, 6 hilos → slots estrictamente ordenados (thread-safe)
- **16.** Backups automáticos: `pg_dump` + JSON semanal a `/backups` con retención ✅ IMPLEMENTADO (2026-10-04): nuevo `backup_service.py` — **`run_backup()`**: (1) JSON portable de **toda la BD (todos los usuarios)** con contadores de chapters/issues, (2) **`pg_dump -Fc`** (custom format, restorable con `pg_restore`) usando credenciales de `DATABASE_URL` (el Dockerfile ya instala `postgresql-client`), (3) **retención** `BACKUP_RETENTION` (default 4): borra los timestamps más viejos (par `.json`+`.dump`). `run_backup` **nunca lanza** (fallo de backup no rompe el scheduler). Job APScheduler **domingos 4 AM** (tras cleanup 3 AM + metadata refresh). Endpoints admin: `POST /system/backup` (manual, 500 si falla), `GET /system/backups` (lista con bytes/MB/fecha), `DELETE /system/backups/{ts}` (anti path-traversal: solo `<YYYYMMDD-HHMMSS>[.json|.dump]`). `docker-compose`: volumen `backups` + `BACKUP_DIR`/`BACKUP_RETENTION` en backend y scheduler. Config: `BACKUP_DIR=/backups`, `BACKUP_RETENTION=4`. Tests `test_backups.py` (20): parse_database_url (passwords encoded), run_backup (JSON+dump, dump falla → JSON sigue válido, nunca lanza), retención (6→3, ignora archivos ajenos, -1 desactiva), delete_backup traversal, endpoints (200/403/500/404)
- **17.** Rate-limit endpoints de búsqueda + latencia p95 en panel de logs ✅ IMPLEMENTADO (2026-10-04): **Rate-limit**: `app/core/rate_limit.py` — `SlidingWindowRateLimiter` in-memory thread-safe (ventana deslizante, mismo patrón que el de login) + dependency `rate_limit_search` aplicada a `GET /manga/search`, `/comics/search` y `/books/search`: **30 búsquedas/usuario/5 min** (config: `SEARCH_RATE_LIMIT_MAX`/`SEARCH_RATE_LIMIT_WINDOW`), 429 "Demasiadas búsquedas…" al exceder. Por usuario (requieren auth), no por IP. **Latencia**: `app/core/latency.py` — `LatencyTracker` (deque bounded 5000 muestras, thread-safe) + middleware `latency_middleware` en `main.py` que mide cada request a `/api/v1/*` (agrupado por plantilla de route, no por path con ID). Endpoint admin `GET /system/latency?window_minutes=60` → count, avg, **p50/p95/p99**, max, `slowest` (top-10 endpoints por p95 con count/max). Frontend `Settings.jsx`: card "Latencia de la API (última hora)" en la sección Logs del sistema — chips p50/p95/p99/max + nº peticiones + tabla de 5 endpoints más lentos; botón "Actualizar" carga logs + latencia. Tests `test_rate_limit_latency.py` (14): limiter (máx, expiración ventana, reset, 80 hilos→10 permitidas), tracker (percentiles interpolados, ventana, grouping), endpoint (200/403, middleware registra), search 429 al 4º intento (AniList stubeado) y límite por usuario (user agotado, admin no)
- **18.** Discover 2.0: "Siguiendo", "Continuar leyendo", "Añadidos recientemente" ✅ IMPLEMENTADO (2026-10-04): Endpoint `GET /recommendations/library-sections?limit=12` (`recommendations.py`) → 3 secciones de la biblioteca del usuario: **`following`** (`monitored=True`), **`continue_reading`** (`reading_status='reading'`), **`recently_added`** (todos, `created_at` desc). Cada item en shape unificado compatible con `ContentCard` (`content_type` manga/comic/book, `library_id`, `title`, `cover_image`, `genres` (book: `categories`), `reading_status`, `monitored`, `in_library`). Frontend `Discover.jsx`: 3 filas horizontales con scroll (`SectionRow`: FaRss verde / FaBookOpen azul / FaClock amarillo) **antes** de las recomendaciones; secciones vacías no se renderizan (el fallback trending sigue cubriendo biblioteca vacía). `api.js`: `recommendationsApi.getLibrarySections(limit)`. Tests `test_discover_sections.py` (7): auth 403, biblioteca vacía, separación de secciones, mapeo content_type + shape, aislamiento por usuario, orden created_at desc, límite
- **19.** Unificar `MangaCard/ComicCard/BookCard` en `ContentCard` ✅ IMPLEMENTADO (2026-10-04): Los 6 componentes (`MangaCard`/`ComicCard`/`BookCard` + sus grids `MangaGrid`/`ComicGrid`/`BookGrid`) eran **huérfanos**: el único uso mutuo era grid→card y ningún page/componente los importaba (verificado con grep de imports, strings y dynamic imports). `ContentCard` + `ContentGrid` ya son la única implementación usada (Library, Comics, Books, Discover, Search, Dashboard). **Borrados 6 archivos** (672 líneas) — unificación real sin riesgo de regresión. `npm run build` OK

---

## Orden de ejecución acordado

1. **#1** búsqueda progresiva ✅ + **#2** caché persistente ✅ (2026-10-04)
2. **#3** traducción persistente ✅ (2026-10-04)
3. **#4 + #5** STK proactivo + auto-send libros ✅ (2026-10-04)
4. Estilo: **#6** modo claro/oscuro ✅ (2026-10-04)
5. **#7** Web Push VAPID ✅ (2026-10-04)
6. **#8** Web reader EPUB (epub.js) ✅ (2026-10-04)
7. **#9** Paginación/infinite scroll ✅ (2026-10-04)
8. **#10** Sesión aiohttp compartida en Anilist ✅ (2026-10-04)
9. **#11** Índices BD compuestos (chapters, comic_issues) ✅ (2026-10-04)
10. **#12** Proxy de covers con caché + ETag ✅ (2026-10-04)
11. **#13** Telemetría éxitos/fallos + priorización dinámica ✅ (2026-10-04)
12. **#14** Retención de disco (CLEANUP_DAYS configurable, 3 tipos) + /system/disk-usage ✅ (2026-10-04)
13. **#15** Tests de lógica pura (scorer, bundles, STK, rate-limiter) ✅ (2026-10-04)
14. **#16** Backups automáticos (pg_dump + JSON, retención, /backups) ✅ (2026-10-04)
15. **#17** Rate-limit búsquedas (30/5min por usuario) + p95 latencia en panel de logs ✅ (2026-10-04)
16. **#18** Discover 2.0 (Siguiendo / Continuar leyendo / Añadidos recientemente) ✅ (2026-10-04)
17. **#19** Unificar cards: borrar MangaCard/ComicCard/BookCard + grids huérfanos ✅ (2026-10-04)

**Verificación local (2026-10-04):** `pytest backend/tests/` → **332 passed, 4 failed** (197 base + 9 push + 6 reader EPUB + 3 pagination + 4 sesión Anilist + 4 índices BD + 9 proxy covers + 19 telemetría + 10 retención disco + 30 lógica pura + 20 backups + 14 rate-limit/latencia + 7 discover sections). `npm run build` OK (warning de chunk >500 kB: epubjs).
Los fallos (4-5) son de **entorno local/red** (sin Playwright browser, Google Books 429 sin API key,
`/downloads` read-only, contaminación de estado de queue, y 1 scraper de red intermitente —
pasa al ejecutarlo aislado) — **ninguno toca el código de #2/#3/#4/#5/#7/#8/#9/#10/#11/#12/#13/#14/#15/#16/#17/#18/#19**.
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
