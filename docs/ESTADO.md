# ESTADO — Alejandría

> **Documento vivo.** Snapshot del estado actual del proyecto. Re-leer al empezar una sesión y actualizar al terminar un hito.
> Para el "cómo está hecho" ver `ARQUITECTURA.md`. Para reglas de workflow y filosofía ver `../CLAUDE.md`.

**Última actualización:** 2026-10-01
**Versión:** v3.1 (main, tree limpio, sincronizado con `origin/main`)

---

## 1. Resumen en 30 segundos

Alejandría es una plataforma **multi-usuario en español** que automatiza una biblioteca digital de **manga / cómics / libros**: busca en scrapers, descarga (resolviendo acortadores y hostings), convierte CBZ/CBR → EPUB con KCC y envía a **Kindle** vía STK. Stack: FastAPI + SQLAlchemy + PostgreSQL (backend), React + Vite + Tailwind (frontend), y dos workers Docker (`scheduler`, `kcc-converter`) más `flaresolverr` para bypass de Cloudflare.

**Estado general: estable y funcional.** Los tres flujos (manga, cómics, libros) están completos y en producción. El front fue rediseñado recientemente (estética cinematográfica: negro profundo + dorado, Playfair Display + Outfit) — ver `docs/superpowers/`.

---

## 2. Zona activa / frente de batalla (últimos commits)

El esfuerzo reciente se concentra en la **capa de descargas y resolvers**, que es la parte más frágil del sistema:

| Área | Estado | Notas |
|---|---|---|
| **Resolver ouo.io / ouo.press** | 🔴 Frágil / iterando | Larga racha de `fix(ouo)` en el log. Estrategia actual: `bypass-ouo` lib → `curl_cffi` (fingerprint `chrome124`, `chrome120` bloqueado en Docker) → FlareSolverr → Playwright. v-token dinámico vía form POST1+POST2. Cache + dedup in-flight + semaphore=1. |
| **STK (Send to Kindle)** | 🟢 Corregido | La sesión NO expira (el `adp_token` de stkclient es de larga duración). El bug era propio: `_record_failure()` borraba la sesión tras 5 fallos y `deviceinfotoken` (403 transitorio) contaba como definitivo. Fix: quitar `deviceinfotoken` de definitivos, umbral 5→20, `heartbeat()` no-destructivo en el scheduler. Solo el logout manual (botón) resetea. |
| **Descarga directa** | 🟡 Estabilizado | Timeout total 2h, `sock_read` para no cortar archivos lentos, limpieza de parciales en error. |
| **Bundles** | 🟢 Funcional | `fix bundle URL mismatch`: se pasa la URL original a `_mark_bundled_chapters_downloaded`. |
| **Limpieza** | 🟢 Funcional | `fix cleanup_old_files`: `isnot(None)` correcto + `converted_path` separada por `|`. |

**Implicación para el trabajo:** si tocas descargas, empieza por `downloader.py`, `generic_downloader.py`, `ouo_resolver.py` y `terabox_bypass.py`. Son los archivos que más cambian y los más propensos a regredir.

---

## 3. Qué está funcionando (verificado)

- ✅ **Manga** — AniList (metadata) + TomosManga (primario) / MangaYComics (paralelo) / TuMangaOnline (fallback). Lector web en navegador (token en query param).
- ✅ **Cómics** — ComicVine (metadata, búsqueda ES→EN) + ZonaComics / CBRComics / MegaComics. Bundles (TPB/HC/Completo) con smart link assignment por `issue_range`. **NO auto-descarga**: el usuario dispara.
- ✅ **Libros** — Google Books (metadata) + Lectulandia / Epubera (EPUB directo).
- ✅ **Conversión** — KCC worker CBZ/CBR → EPUB, modo manga (`-m`) y comic (sin `-m`), división automática >180MB en partes.
- ✅ **Envío** — STK por usuario con OAuth2 de Amazon, tokens en volumen `stk_data` compartido backend/scheduler.
- ✅ **Multi-usuario** — admin + usuarios, bibliotecas aisladas, rate limiting en login, endpoints admin protegidos.
- ✅ **Automatización** — scheduler en contenedor propio con 10 jobs (ver ARQUITECTURA §6).
- ✅ **Extras** — /imports watcher, anti-duplicados (Jaccard ≥0.8), OPDS feed, SSE cola en tiempo real, PWA, web reader, uploader de archivos, /discover con recomendaciones locales sin IA.

---

## 4. Tests

- **201 funciones de test** en **17 ficheros** (`backend/tests/`).
- Suites unitarias: `test_auth`, `test_library`, `test_manga`, `test_comics`, `test_books`, `test_queue`, `test_reading_status`, `test_recommendations`, `test_recommender_score`, `test_settings`, `test_system`, `test_upload`, `test_opds_and_settings`, `test_health`, `test_ouo_dedup`.
- `test_scrapers.py` es **de integración real** (contra servicios externos): puede fallar si OUO.io/TeraBox/AniList caen o bloquean; ComicVine requiere `COMICVINE_API_KEY`.
- Ejecutar: `docker exec alejandria-backend python -m pytest tests/ -v` (o `scripts/run-tests.sh`).

> ⚠️ No hay evidencia en el repo de que los tests se ejecuten en CI. Verificar manualmente antes de declarar "listo" (ver `../skills.md` → Verification Before Done).

---

## 5. Puntos de dolor conocidos (troubleshooting recurrente)

| Sintoma | Causa probable | Solución |
|---|---|---|
| Descargas atascadas en "downloading" | Proceso muerto sin limpiar estado | UI: Cola → Reset Stuck. O `UPDATE chapters/comic_issues SET status='pending' WHERE status='downloading'` |
| Link "inactive" en logs | Verificando acortadores con HEAD | NO verificar acortadores; detectarlos y guardar sin verificar |
| Comics 0/X issues con `download_url` | Links descartados por verificación fallida | Revisar logs; normalmente acortadores |
| Volumes triplicados en front | Dedup por comic en vez de por `volume.url` | Deduplicar por `volume.url` |
| Comic sin metadata (publisher=Unknown) | No traducir ES→EN antes de ComicVine | Usar `_translate_comic_title()` antes de buscar |
| STK rechaza la sesión (raro) | Amazon revocó el dispositivo de verdad (no es expiración: la credencial no caduca) | Ajustes → Amazon Send to Kindle → Desconectar y reconectar |
| ouo.io no resuelve | Cloudflare cambia fingerprint | Ver §2; ajustar fingerprint en `ouo_resolver.py` |

---

## 6. Pendiente / Roadmap (Futuro, sin empezar)

- [ ] Notificaciones push (Telegram, Discord)
- [ ] Importación desde Calibre
- [ ] Sincronización con AniList / MyAnimeList (estado de lectura)
- [ ] Lector web para cómics (hoy solo manga)

---

## 7. Cómo orientarse rápido (checklist de sesión)

1. `git log --oneline -20` → ¿en qué zona estamos? (hoy: descargas/ouo)
2. Leer este `ESTADO.md` → contexto y dolores.
3. `ARQUITECTURA.md` §2 (modelo de datos) y §6 (scheduler) → cómo fluyen los datos.
4. `docker compose ps` + `logs backend --tail 100` → estado vivo.
5. Tocar solo lo necesario; la capa de descargas regresa con facilidad (§2).

**Comandos esenciales:**
```bash
docker compose up -d --build
docker compose logs backend --tail 100
docker compose exec -T postgres psql -U alejandria alejandria -c "SELECT ...;"
```