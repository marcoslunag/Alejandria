# SESIÓN 2026-10-01 — Remediación scrapers (3 fases)

> **Documento de recuperación.** Si se pierde la sesión, leer esto primero. Contiene: diagnóstico completo con evidencia verificada, diseño de las 3 fases, estado del trabajo, y el procedimiento operativo exacto (SSH/expect, deploy, verificación).

---

## 0. Contexto

El usuario reportó que "la plataforma no funciona bien" tras el último commit. Diagnóstico realizado el 2026-10-01: **el último commit (`1166521`, STK/scheduler) NO es la causa**. Los fallos son deriva de scrapers/sitios + latencia de búsqueda, preexistentes. El usuario pidió: **trabajar en autónomo hasta completar las 3 fases, haciendo commits, push/pull en el servidor y comprobando que no haya errores.**

### Dolor real del usuario (P0)
Logs del backend (15:51–15:57 UTC, vía Cloudflare desde `alejandria.undiamagico.es`):
- `POST /api/v1/books/from-url` → **400 TRES veces** (15:54:32, 15:56:33, 15:57:26) — el usuario reintentó la misma acción.
- `GET /manga/search?q=one piece` → 499 a los 60s (sigue corriendo; el sitio hace throttle).
- Búsqueda de libros "el hobbit" → 200 OK en ~9s (funciona, vía Playwright Lectulandia).

---

## 1. Entorno y acceso

| Dato | Valor |
|---|---|
| Repo local | `/Users/kitos/Desktop/Alejandria`, branch `main`, HEAD `1166521`, clean |
| Remote | `origin git@github.com:marcoslunag/Alejandria` |
| Servidor | `192.168.1.112`, `root` / `primos`, repo en `/root/Alejandria` (mismo commit) |
| Contenedores | `alejandria-backend` (puerto **7878**, `/health` OK), `alejandria-frontend` (nginx :8888), `alejandria-scheduler`, `alejandria-converter`, `alejandria-db` |
| DB (legacy .env) | `docker exec alejandria-db psql -U manga manga_arr -c '...'` (usuario `manga`, db `manga_arr`) |
| Cloudflare | delante de `alejandria.undiamagico.es` (IP real usuario 79.148.33.207). Cadena: browser→CF→nginx(180s)→backend(SCRAPER_TIMEOUT 150s) |
| CPU contenedor | `os.cpu_count()`=8 pero `nproc`=2 (cgroup) |
| Token de prueba | JWT usuario 2/kitos, exp ~2026-10-31: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzkzNDU2NTI0fQ.kYIOifYKwxymifNIS41EPHsksrleYF92toQIFTM_wf8` |
| Tests | `docker exec alejandria-backend python -m pytest tests/ -v` (201 tests, 17 ficheros; `test_scrapers.py` es integración real) |

### SSH con expect (NO hay sshpass)
Patrón que funciona (heredoc; `expect -c` inline falla por quoting):
```bash
expect << 'EXP_EOF'
set timeout 120
spawn ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@192.168.1.112 "<comando remoto>"
expect {
    "password" { send "primos\r"; exp_continue }
    timeout { puts "WAIT_TIMEOUT" }
    eof
}
catch wait result
exit [lindex $result 3]
EXP_EOF
```
**Reglas de quoting (Tcl + bash + zsh, lecciones de esta sesión):**
- Dentro de las comillas dobles de `spawn ssh ... "..."`: escapar `"` → `\"`, `$` → `\$`, `[` → `\[`, `]` → `\]`; sin backticks.
- En el bash remoto: **citar variables con espacios**: `-A \"\$UA\"` (sin citar → word-splitting → curl rompe la URL en 10 peticiones).
- `grep -E` en vez de BRE `\|` (la backslash se pierde al pasar por Tcl).
- No volcar HTML grande a stdout (budget de contexto 24KB/tool result): usar `grep -o`, `head -c`, extracciones puntuales.
- Escribir en `/tmp` local o dirs externos está bloqueado (`external_directory`): usar workspace o stdin.

---

## 2. FASE 1 (P0) — Añadir libro por URL (Lectulandia) ✅ DIAGNOSTICADO, FIX DISEÑADO

### Causa raíz (TODA la cadena verificada en el servidor)
1. La página del libro (`https://ww3.lectulandia.com/book/el-hobbit/`) tiene:
   ```html
   <a href="/download.php?t=1&d=ZDRFZmpQR1Mv&ti=El+hobbit"><input id="download1" ... value="epub" /></a>
   <a href="/download.php?t=2&d=UHZwSlY2aHQv&ti=El+hobbit"><input id="download2" ... value="pdf" /></a>
   ```
   (t=1 = EPUB, t=2 = PDF). El parámetro `d` es **estable por libro** (idéntico a la hora; no depende de sesión/cookies).
2. `download.php` **ya no redirige**: devuelve HTTP 200 + HTML con `<div id="notice">En un momento seras redirigido...</div>` y `var linkCode = "d4EfjPGS/";` (detrás de un reto Cloudflare que recarga la página).
3. `uCommon.js` de Lectulandia, función `getBookLink()` (se ejecuta cuando existe `#downloadPage #notice`):
   ```js
   var link = 'https://www.antupload.com/file/' + linkCode;
   setTimeout('redirect("' + link + '")', 11 * 1000);  // redirige tras 11s
   ```
   donde **`linkCode = base64_decode(parámetro d)`**. Verificado local: `printf 'ZDRFZmpQR1Mv' | base64 -d` → `d4EfjPGS/`.
4. `https://www.antupload.com/file/d4EfjPGS/` → **HTTP 200 con curl plano + UA de browser (SIN reto CF en este host)**. El HTML contiene:
   ```html
   <a id="downloadB" href="/filed/d4EfjPGS/El+hobbit+-+J.+R.+R.+Tolkien">DOWNLOAD NOW</a>
   ```
   Archivo: "El hobbit - J. R. R. Tolkien.epub", 9.82 MB.
5. `/filed/...` (el link directo) → **HTTP 302 → `http://www.antupload.com/file/d4EfjPGS`** (requiere sesión/cookies para el fichero real). **CONCLUSIÓN: la URL que hay que guardar es la página `/file/<linkCode>`, no `/filed/`.**
6. **El scheduler YA sabe descargar de antupload**: `scheduler.py:796-838` — si `download_url` contiene `antupload.com`, navega con Playwright, busca `#downloadB`, `expect_download` + `save_as`. Lo mismo en el endpoint manual de descarga (`books.py:976-1021`). **No hay que tocar la descarga, solo el scraping.**

### Por qué falla el código actual
`playwright_scraper.py:192 _resolve_lectulandia_download`: navega a `download.php` y espera 15s a que cambie la URL. El reto Cloudflare recarga la página → "Execution context was destroyed"; el JS redirige a los 11s pero el contexto ya está roto. Sin redirect → busca links directos en la página (no existen) → regex de mega/mediafire (no existen) → `None`. Fallback aiohttp (`lectulandia.py:124-169`) busca hosts directos (no hay) → `success=False` → **400** en `books.py:446`.

### FIX (diseño final, para implementar)
En `backend/app/services/book_scrapers/lectulandia.py`, método nuevo `_resolve_download_links_http(url)` que se llama **primero** en `get_download_links` (antes de Playwright):
1. GET página del libro (aiohttp, headers de browser).
2. Buscar `a[href*="download.php"]` con `t=1` (saltar `t=2`), regex `[?&]d=([^&]+)` → parámetro `d`.
3. `link_code = base64.b64decode(d).decode('utf-8', errors='ignore').strip()`.
4. `antupload_url = f"https://www.antupload.com/file/{link_code}"`.
5. GET `antupload_url` y **validar** que exista `<a id="downloadB">`.
6. Devolver `BookScraperResult(success=True, download_links=[DownloadLink(url=antupload_url, host=HostType.ANTUPLOAD, quality_score=80)])` + title/cover de la página.
7. Si CUALQUIER paso falla → `return None` → sigue el flujo actual (Playwright → fallback aiohttp).

**CUIDADO**: `base.py detect_host()` NO conoce antupload (→ UNKNOWN) y `HOST_QUALITY` no tiene ANTUPLOAD (default 30). Construir el `DownloadLink` **explícitamente** con `HostType.ANTUPLOAD, quality_score=80` (como hace `playwright_scraper._get_host_quality`).

### Archivos (Fase 1)
- `backend/app/services/book_scrapers/lectulandia.py:109` `get_download_links` — **objetivo del fix**
- `backend/app/services/book_scrapers/playwright_scraper.py:90/192/285` — fallback Playwright (no tocar en Fase 1)
- `backend/app/services/book_scrapers/base.py` — `HostType.ANTUPLOAD`, `DownloadLink`, `BookScraperResult`
- `backend/app/api/v1/books.py:412` `add_book_from_url` — consume `result.success`, `result.best_link.url`
- `backend/app/services/scheduler.py:796-838` — descarga antupload existente (compatible con `/file/`)

### Verificación Fase 1
1. `docker exec alejandria-backend python -m pytest tests/test_books.py -v`
2. Deploy (ver §6).
3. `curl -X POST http://localhost:7878/api/v1/books/from-url -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"source_url":"https://ww3.lectulandia.com/book/el-hobbit/"}'` → esperar **200** y `BookChapter.download_url` contiene `antupload.com/file/`.
4. **LIMPIAR el libro de prueba** tras verificar (DELETE por id o SQL).

---

## 3. FASE 2 (P1) — Búsqueda rápida (manga/libros/cómics)

### Diagnóstico (verificado)
`manga.py:133 search_manga`: hasta **20 resultados AniList × 2 scrapers** (TomosManga + MangayComics) = 40 peticiones HTTP vía `asyncio.wait` con `SCRAPER_TIMEOUT=150s`. Los sitios hacen **throttle** al paralelo (burst de 6 → 6.5s cada una; luego ~1-2 en paralelo) → 30-90s+. Executor ThreadPool **compartido entre todos los endpoints** → starvación (la búsqueda de libros se estancó detrás de la de manga). Test: `manga/search?q=one piece` → 499 a los 60s.

### Plan
1. `CHECK_LIMIT` 20 → **8**.
2. `asyncio.Semaphore(4)` sobre las comprobaciones de scrapers.
3. `ThreadPoolExecutor` **dedicado** (4 workers) para HTTP de scrapers (evita starvación entre endpoints).
4. `SCRAPER_TIMEOUT` 150s → **30s**.
5. Cache de disponibilidad (TTL 24-48h) por título normalizado + scraper.
6. nginx 180s ya es correcto; no tocar.
7. Revisar patrón similar en `comic.py:59 search_comics` y `comic.py:972 search_sources` → aplicar semáforo/timeout.
8. `books.py:46 search_books`: Lectulandia (Playwright) + Epubera (muerto) — aplicar timeout.

### Verificación Fase 2
`time curl /api/v1/manga/search?q=one piece` → **< 30s** y respuesta con badges de scrapers intactos.

---

## 4. FASE 3 (P2-P3) — Robustez

| # | Item | Detalle |
|---|---|---|
| 1 | **Epubera muerta** | `Cannot connect to host epubera1.com:443 [Connection reset by peer]`. Buscar dominio vigente; si no hay, desactivar con mensaje claro (no 500). |
| 2 | **Google Books 503** | Rate-limit desde la IP del servidor en CADA búsqueda de libros. Backoff (tenacity) + reintentos con espera. |
| 3 | **Translator spam** | `Translation failed: ... too many requests` (>5 req/s). Token bucket / rate limiter (máx ~5 req/s). |
| 4 | **Healthchecks rotos** | `frontend/Dockerfile`: `wget --spider http://localhost/` → BusyBox wget resuelve `localhost`→`::1`, nginx solo IPv4 → usar `127.0.0.1`. `scheduler/Dockerfile` + `kcc-converter/Dockerfile`: usan `pgrep` (no existe en slim) → healthcheck Python/curl. Objetivo: los 4 contenedores healthy. |
| 5 | **Zombies de cola** | `download_queue`: 3 items `downloading` desde mayo (ids 168, 161, 160) + 1 `failed` (id 178). Job en scheduler: items `downloading` con `started_at` > 2h → `failed` (o re-encolar). |

### Verificación Fase 3
`docker compose ps` → 4/4 healthy. Logs sin spam de translator/503. Zombies marcados.

---

## 5. Estado del trabajo (2026-10-01, cierre de sesión)

- [x] Diagnóstico completo P0 (cadena completa verificada con curl en el servidor).
- [x] Diagnóstico P1 (throttle + 150s cap + executor compartido).
- [x] Plan 3 fases acordado con el usuario.
- [x] Documento de recuperación escrito (este archivo).
- [ ] **Fase 1: implementar `_resolve_download_links_http` en `lectulandia.py` + commit + deploy + verificar.**
- [ ] Fase 2: implementar + commit + deploy + verificar.
- [ ] Fase 3: implementar + commit + deploy + verificar.
- Pendientes DB (Fase 3): marcar zombies `downloading` (168, 161, 160).

---

## 6. Procedimiento de deploy (por fase)

```bash
# LOCAL
cd /Users/kitos/Desktop/Alejandria
docker exec alejandria-backend python -m pytest tests/ -v   # tests locales si hay
git add -A && git commit -m "<fix(...) mensaje claro>"
git push origin main

# SERVIDOR (expect heredoc, ver §1)
cd /root/Alejandria && git pull
docker compose build backend        # o los servicios afectados
docker compose up -d
docker compose logs backend --tail 100   # sin errores
docker compose ps                     # estados
```
- Un commit **por fase** (mensajes descriptivos en español, estilo del repo: `fix(lectulandia): ...`, `perf(manga): ...`, `chore(docker): ...`).
- Tras cada deploy: verificar logs + test funcional de la fase + **limpiar datos de prueba**.

---

## 7. Evidencia verificada (resumen de comandos/resultados)

| Comando (en servidor) | Resultado |
|---|---|
| `curl` página `/book/el-hobbit/` | `#download1` → `/download.php?t=1&d=ZDRFZmpQR1Mv&ti=El+hobbit` |
| `printf 'ZDRFZmpQR1Mv' \| base64 -d` | `d4EfjPGS/` |
| `curl https://www.antupload.com/file/d4EfjPGS/` (UA browser) | **200**, `#downloadB` → `/filed/d4EfjPGS/El+hobbit+-+J.+R.+R.+Tolkien`, epub 9.82MB |
| `curl -r 0-0 .../filed/d4EfjPGS/...` | **302** → `http://www.antupload.com/file/d4EfjPGS` (session requerida) |
| `curl -s -o /dev/null -w '%{http_code} %{time_total}' /api/v1/manga/search?q=one piece` | 499 a 60s (throttle) |
| Logs 15:51-15:57 UTC | 3× 400 `from-url`; epubera reset; Google Books 503; translator "too many requests" |
