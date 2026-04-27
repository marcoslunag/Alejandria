"""
Alejandria - KCC Converter Worker
Normalizes archives before sending to KCC.
FINAL VERSION: Output filenames preserve original names (no .clean suffix)
"""

import os
import re
import time
import subprocess
import logging
import zipfile
import shutil
import tempfile
import json
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


def _natural_sort_key(path: Path) -> list:
    """
    Clave de ordenación natural — trata números embebidos como enteros,
    usando la ruta completa para respetar carpetas de capítulos.
    """
    result = []
    for component in path.parts:
        for segment in re.split(r'(\d+)', component.lower()):
            result.append(int(segment) if segment.isdigit() else segment)
    return result


# Sufijos que indican variantes de la misma página (no páginas distintas)
# Ejemplos: "36 copia.jpg", "36 copia (1).jpg", "p010-min-min.jpg"
_VARIANT_SUFFIX_RE = re.compile(
    r'(\s+copia(\s*\(\d+\))?)+$'  # " copia", " copia (1)", " copia copia"
    r'|(\s*-\s*min)+$',            # "-min", "-min-min"
    re.IGNORECASE
)


def _normalize_page_key(path: Path) -> tuple:
    """
    Clave para detectar páginas duplicadas: (directorio_padre, stem_normalizado).
    Strips variant suffixes: ' copia', ' copia (1)', '-min', '-min-min'.
    """
    stem = path.stem
    normalized = _VARIANT_SUFFIX_RE.sub('', stem).strip().lower()
    return (path.parent, normalized)


def _deduplicate_variant_pages(image_files: list, label: str = "") -> list:
    """
    Elimina páginas duplicadas producidas por variantes de archivo del mismo release:
    - '36 copia.jpg' y '36.jpg'     → misma página (ej: capítulo 132 de AoT t33)
    - 'p010-min-min.jpg' y 'p010.jpg' → misma página (versión comprimida vs original)

    Conserva el archivo de mayor tamaño (asumiendo mejor calidad).
    Preserva el orden del input.
    """
    if not image_files:
        return image_files

    # Agrupar por (directorio, stem normalizado)
    key_to_files: dict = {}
    for item in image_files:
        img_path, size = item
        key = _normalize_page_key(img_path)
        key_to_files.setdefault(key, []).append(item)

    # Determinar qué paths conservar (el más grande de cada grupo)
    keep_paths: set = set()
    removed_count = 0
    for key, group in key_to_files.items():
        if len(group) == 1:
            keep_paths.add(group[0][0])
        else:
            best = max(group, key=lambda x: x[1])  # mayor tamaño = mejor calidad
            keep_paths.add(best[0])
            removed_count += len(group) - 1
            others = [p.name for p, _ in group if p != best[0]]
            logger.info(
                f"🗑️  Dedup{f' [{label}]' if label else ''}: "
                f"'{best[0].name}' reemplaza a {others}"
            )

    if removed_count:
        logger.warning(
            f"⚠️  Eliminadas {removed_count} página(s) duplicada(s) con sufijos "
            f"'copia'/'-min'{f' en {label}' if label else ''} — "
            f"se conserva la versión de mayor tamaño"
        )

    # Filtrar preservando el orden original
    return [(p, s) for p, s in image_files if p in keep_paths]


def _detect_and_sort_images(image_files: list, label: str = "") -> list:
    """
    Detecta el patrón de nombres de las imágenes, aplica natural sort,
    y logea una advertencia si el orden léxico habría sido incorrecto.

    Patrones manejados correctamente:
    - "1.jpg" ... "99.jpg" ... "100.jpg"   (sin zero-padding) ✓
    - "001.jpg" ... "099.jpg" ... "100.jpg" (con zero-padding) ✓
    - "Page_1.jpg" ... "Page_100.jpg"       (prefijo + número) ✓
    - "Chapter 1/001.jpg" ... "Chapter 10/" (carpetas de capítulos) ✓
    - Mezcla de cualquiera de los anteriores ✓
    """
    if not image_files:
        return image_files

    paths = [x[0] for x in image_files]
    names = [p.name for p in paths]

    # Detectar si hay carpetas de capítulos (rutas distintas)
    unique_parents = set(p.parent for p in paths)
    has_chapter_dirs = len(unique_parents) > 1

    # Extraer el último grupo numérico de cada nombre de archivo
    last_num_re = re.compile(r'(\d+)(?=\D*$)')
    page_nums = []
    zero_padded_count = 0
    for name in names:
        stem = Path(name).stem
        m = last_num_re.search(stem)
        if m:
            num_str = m.group(1)
            page_nums.append(int(num_str))
            if len(num_str) > 1 and num_str[0] == '0':
                zero_padded_count += 1

    # Describir el patrón detectado
    if has_chapter_dirs:
        chapter_names = sorted(set(p.parent.name for p in paths))[:5]
        pattern = (
            f"subcarpetas de capítulos ({len(unique_parents)} dirs: "
            f"{', '.join(chapter_names)}{'...' if len(unique_parents) > 5 else ''})"
        )
    elif not page_nums:
        pattern = "sin numeración de páginas"
    else:
        total = len(page_nums)
        zp_pct = zero_padded_count / total
        lo, hi = min(page_nums), max(page_nums)
        if zp_pct >= 0.9:
            pattern = f"zero-padded ({lo}–{hi}, {total} páginas)"
        elif zp_pct <= 0.1:
            pattern = (
                f"SIN zero-padding ({lo}–{hi}, {total} páginas) "
                f"← riesgo de salto de páginas sin natural sort"
            )
        else:
            pattern = (
                f"padding MIXTO ({lo}–{hi}, {total} págs, "
                f"{zp_pct:.0%} zero-padded)"
            )

    # Aplicar natural sort (ruta completa)
    nat_sorted = sorted(image_files, key=lambda x: _natural_sort_key(x[0]))

    # Comparar con orden léxico de RUTA COMPLETA para detectar discrepancias.
    # Usar ruta completa (no solo nombre) permite detectar casos como
    # SNK_131_9.jpg vs SNK_131_10.jpg donde el orden léxico invertiría páginas.
    lex_sorted = sorted(image_files, key=lambda x: str(x[0]).lower())

    nat_names = [x[0].name for x in nat_sorted]
    lex_names = [x[0].name for x in lex_sorted]

    if nat_names != lex_names:
        first = next(
            i for i, (n, l) in enumerate(zip(nat_names, lex_names)) if n != l
        )
        logger.warning(
            f"⚠️  SORT [{label}] — {pattern}: "
            f"el orden léxico INCORRECTO habría causado salto de páginas "
            f"en posición {first + 1} "
            f"(léxico='{lex_names[first]}' → correcto='{nat_names[first]}'). "
            f"Natural sort aplicado — páginas en orden correcto."
        )
    else:
        logger.info(
            f"✅ SORT [{label}] — {pattern}: "
            f"orden léxico = natural, sin riesgo de saltos."
        )

    return nat_sorted

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

WATCH_DIR = Path(os.getenv('WATCH_DIR', '/downloads'))
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', '/library/kindle'))
KCC_CONFIG_FILE = WATCH_DIR / '.kcc_config.json'

# Defaults (can be overridden by config file)
KCC_PROFILE = os.getenv('KCC_PROFILE', 'KPW5')
KCC_FORMAT = os.getenv('KCC_FORMAT', 'EPUB')  # MOBI para Kindle nativo
KCC_QUALITY = os.getenv('KCC_QUALITY', '85')

# Tamaño máximo por archivo para STK (Send to Kindle API)
MAX_OUTPUT_SIZE_MB = 180  # Dejamos margen para metadatos
MAX_CONVERSION_RETRIES = 3  # Máximo de reintentos si el output excede el límite


def load_kcc_config():
    """Lee la configuración de KCC desde el archivo compartido"""
    global KCC_PROFILE, KCC_FORMAT
    try:
        if KCC_CONFIG_FILE.exists():
            with open(KCC_CONFIG_FILE, 'r') as f:
                config = json.load(f)
            KCC_PROFILE = config.get('profile', KCC_PROFILE)
            KCC_FORMAT = config.get('format', KCC_FORMAT)
            logger.info(f"Loaded KCC config: profile={KCC_PROFILE}, format={KCC_FORMAT}")
    except Exception as e:
        logger.warning(f"Could not load KCC config: {e}")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SKIP_FILES = {'.ds_store', 'thumbs.db', 'desktop.ini', '._.ds_store', '__macosx'}


def generate_comicinfo_xml(metadata: dict, part_number: int = None) -> str:
    """
    Genera ComicInfo.xml desde metadatos del manga o comic
    Formato compatible con ComicRack/KCC
    Detecta automáticamente si es manga o comic americano basado en los metadatos
    """
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    root = ET.Element("ComicInfo")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")

    def add_elem(name, value):
        if value:
            elem = ET.SubElement(root, name)
            elem.text = str(value)

    # Detectar si es comic americano (tiene comicvine_id o publisher) o manga (tiene anilist_id)
    is_comic = bool(metadata.get('comicvine_id') or metadata.get('publisher'))
    is_manga = bool(metadata.get('anilist_id') or metadata.get('country') in ['JP', 'KR', 'CN', 'TW'])

    # Serie
    add_elem("Series", metadata.get('title', 'Unknown'))

    # Volumen/Número
    volume = metadata.get('volume_number', 1)
    issue_number = metadata.get('issue_number')

    if is_comic and issue_number:
        # Para comics americanos, usar issue_number
        add_elem("Number", str(issue_number))
        add_elem("Volume", "1")  # La mayoría de comics son volumen 1
    else:
        # Para manga, usar volume_number como antes
        add_elem("Volume", str(volume))
        add_elem("Number", str(volume))

    # Título
    if is_comic:
        title = metadata.get('chapter_title') or f"Issue #{issue_number or volume}"
    else:
        title = metadata.get('chapter_title') or f"Tomo {volume}"

    if part_number:
        title = f"{title} - Parte {part_number}"
    add_elem("Title", title)

    # Sinopsis
    if metadata.get('description'):
        desc = metadata['description'].replace('\r\n', '\n').replace('\r', '\n')
        import re
        desc = re.sub(r'<[^>]+>', '', desc)
        add_elem("Summary", desc[:2000])

    # Autores/Artistas
    if metadata.get('authors'):
        add_elem("Writer", ", ".join(metadata['authors'][:3]))

    if metadata.get('artists'):
        artists = ", ".join(metadata['artists'][:3])
        add_elem("Penciller", artists)
        add_elem("Inker", artists)
    elif metadata.get('authors'):
        add_elem("Penciller", ", ".join(metadata['authors'][:3]))

    # Coloristas (principalmente para comics)
    if metadata.get('colorists'):
        add_elem("Colorist", ", ".join(metadata['colorists'][:3]))

    # Géneros
    if metadata.get('genres'):
        add_elem("Genre", ", ".join(metadata['genres'][:5]))

    # Fecha - usar release_date del issue si está disponible, si no start_date
    release_date = metadata.get('release_date') or metadata.get('start_date')
    if release_date:
        try:
            release_date = str(release_date)
            if len(release_date) >= 4:
                add_elem("Year", release_date[:4])
            if len(release_date) >= 7:
                add_elem("Month", release_date[5:7])
            if len(release_date) >= 10:
                add_elem("Day", release_date[8:10])
        except (ValueError, IndexError):
            pass

    # Idioma
    if is_comic:
        add_elem("LanguageISO", "en")  # Comics americanos en inglés
    else:
        add_elem("LanguageISO", "es")  # Manga traducido al español

    # Formato manga vs comic
    if is_manga and not is_comic:
        add_elem("Manga", "Yes")
        add_elem("BlackAndWhite", "Yes")
    else:
        add_elem("Manga", "No")
        # Comics suelen ser a color
        add_elem("BlackAndWhite", "No")

    # URL de referencia
    if metadata.get('comicvine_url'):
        add_elem("Web", metadata['comicvine_url'])
    elif metadata.get('anilist_url'):
        add_elem("Web", metadata['anilist_url'])

    # Editorial
    if metadata.get('publisher'):
        add_elem("Publisher", metadata['publisher'])
    elif metadata.get('country'):
        country = metadata['country']
        country_names = {'JP': 'Japón', 'KR': 'Corea del Sur', 'CN': 'China', 'TW': 'Taiwan', 'US': 'USA'}
        add_elem("Publisher", country_names.get(country, country))

    # Notas
    if is_comic:
        notes = "Importado de ComicVine"
        if metadata.get('comicvine_id'):
            notes += f" (ID: {metadata['comicvine_id']})"
    else:
        score = metadata.get('average_score')
        notes = f"Importado de AniList. Score: {score}/100" if score else "Importado de AniList"
    add_elem("Notes", notes)

    # Tags
    if metadata.get('tags'):
        tags = metadata['tags'][:10]
        add_elem("Tags", ", ".join(str(t) for t in tags))

    # Personajes (principalmente para comics)
    if metadata.get('characters'):
        chars = metadata['characters'][:10]
        add_elem("Characters", ", ".join(str(c) for c in chars))

    # Clasificación de edad
    if metadata.get('is_adult'):
        add_elem("AgeRating", "Adults Only 18+")
    elif metadata.get('genres'):
        genres_lower = [g.lower() for g in metadata['genres']]
        if any(g in genres_lower for g in ['ecchi', 'gore', 'violencia', 'mature', 'adult']):
            add_elem("AgeRating", "Mature 17+")

    # Formatear XML
    xml_str = ET.tostring(root, encoding='unicode')
    dom = minidom.parseString(xml_str)
    return dom.toprettyxml(indent="  ", encoding=None)


def load_metadata_for_file(file_path: Path) -> dict | None:
    """Carga metadatos JSON si existe para el archivo"""
    metadata_path = file_path.with_suffix('.metadata.json')
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            logger.info(f"Loaded metadata for: {file_path.name}")
            return metadata
        except Exception as e:
            logger.warning(f"Could not load metadata: {e}")
    return None


class ArchiveHandler(FileSystemEventHandler):

    def __init__(self):
        self.processing = set()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if self.is_supported(file_path):
            logger.info(f"New file detected: {file_path.name}")
            self.process_file(file_path)

    def is_supported(self, file_path: Path) -> bool:
        # IMPORTANTE: Ignorar archivos .clean para evitar loops
        # También ignorar archivos con lock files activos
        return (
            file_path.suffix.lower() in ['.cbz', '.cbr', '.zip', '.rar']
            and '.clean' not in file_path.stem.lower()
            and not file_path.name.startswith('.')
            and not file_path.name.endswith('.downloading')
        )

    def has_active_lock(self, file_path: Path) -> bool:
        """Verifica si el archivo tiene un lock file activo (descarga en progreso)"""
        lock_file = file_path.parent / f"{file_path.name}.downloading"
        return lock_file.exists()

    def should_skip_file(self, filename: str) -> bool:
        name_lower = filename.lower()
        return (
            name_lower.startswith('.') 
            or name_lower in SKIP_FILES
            or '__macosx' in name_lower
        )

    def process_file(self, file_path: Path):
        if str(file_path) in self.processing:
            return

        # Verificar si hay un lock file activo (descarga en progreso)
        if self.has_active_lock(file_path):
            logger.info(f"Lock file detected, waiting for download to complete: {file_path.name}")
            if not self.wait_for_lock_release(file_path):
                logger.error(f"Download lock timeout: {file_path.name}")
                return
            logger.info(f"Lock released, proceeding: {file_path.name}")

        # Esperar estabilidad del archivo
        if not self.wait_for_file_complete(file_path):
            logger.error(f"File not stable: {file_path.name}")
            return

        # Verificar integridad del archivo
        if not self.verify_archive_integrity(file_path):
            logger.error(f"Archive integrity check failed: {file_path.name}")
            return

        self.processing.add(str(file_path))

        # Recargar configuración
        load_kcc_config()

        # Cargar metadatos si existen
        metadata = load_metadata_for_file(file_path)

        output_ext = KCC_FORMAT.lower()

        try:
            # Loop de reintentos si el output excede el límite
            min_parts = 1
            retry_count = 0
            # Números de tomo ya convertidos correctamente en intentos anteriores (no re-procesar)
            skip_volumes: set = set()
            # Archivos convertidos y guardados en intentos anteriores (acumulados)
            prior_converted: list = []

            while retry_count < MAX_CONVERSION_RETRIES:
                retry_count += 1
                logger.info(f"Conversion attempt {retry_count}/{MAX_CONVERSION_RETRIES} (min_parts={min_parts})")

                # normalize_archive ahora retorna una lista de CBZs
                normalized_files = self.normalize_archive(
                    file_path, metadata, min_parts=min_parts,
                    skip_volumes=skip_volumes if skip_volumes else None
                )

                if not normalized_files:
                    if skip_volumes:
                        # Todos los volúmenes ya fueron procesados en intentos anteriores
                        logger.info("All volumes already converted in previous attempt(s), nothing left to process")
                        all_success = True
                        needs_more_parts = False
                    else:
                        logger.error("Normalization failed.")
                        return
                    break

                all_success = True
                converted_files = []
                needs_more_parts = False
                max_output_size_found = 0
                failed_volume_nums: set = set()  # Tomos que excedieron el límite en este intento

                for normalized_file in normalized_files:
                    if not normalized_file.exists():
                        logger.error(f"Normalized file not found: {normalized_file}")
                        all_success = False
                        continue

                    # El stem del archivo normalizado ya incluye " - Parte X" si fue dividido
                    part_stem = normalized_file.stem.replace('.clean', '')

                    logger.info(f"Starting conversion: {normalized_file.name}")
                    success = self.convert_with_kcc(normalized_file, metadata=metadata)

                    if success:
                        # KCC genera: [part_stem].clean.[ext]
                        # Queremos: [part_stem].[ext]
                        temp_output = OUTPUT_DIR / f"{part_stem}.clean.{output_ext}"
                        final_output = OUTPUT_DIR / f"{part_stem}.{output_ext}"

                        if temp_output.exists():
                            if final_output.exists():
                                final_output.unlink()

                            temp_output.rename(final_output)

                            # VERIFICAR TAMAÑO POST-CONVERSIÓN
                            output_size_mb = final_output.stat().st_size / (1024 * 1024)
                            max_output_size_found = max(max_output_size_found, output_size_mb)
                            logger.info(f"Output size: {output_size_mb:.1f}MB")

                            if output_size_mb > MAX_OUTPUT_SIZE_MB:
                                logger.warning(f"⚠️ Output exceeds limit ({output_size_mb:.1f}MB > {MAX_OUTPUT_SIZE_MB}MB): {final_output.name}")
                                needs_more_parts = True
                                # Eliminar el archivo que excede el límite
                                final_output.unlink(missing_ok=True)
                                # Registrar qué tomo falló para el retry inteligente
                                vol_m = re.search(r'tomo\s*0*(\d+)', part_stem, re.IGNORECASE)
                                if vol_m:
                                    failed_volume_nums.add(int(vol_m.group(1)))
                            else:
                                converted_files.append(final_output.name)
                                logger.info(f"✅ Saved: {final_output.name} ({output_size_mb:.1f}MB)")
                        else:
                            # KCC puede nombrar diferente, buscar el archivo
                            possible_outputs = list(OUTPUT_DIR.glob(f"*{part_stem}*.{output_ext}"))
                            if possible_outputs:
                                for p in possible_outputs:
                                    output_size_mb = p.stat().st_size / (1024 * 1024)
                                    max_output_size_found = max(max_output_size_found, output_size_mb)
                                    if output_size_mb > MAX_OUTPUT_SIZE_MB:
                                        logger.warning(f"⚠️ Output exceeds limit: {p.name} ({output_size_mb:.1f}MB)")
                                        needs_more_parts = True
                                        p.unlink(missing_ok=True)
                                        vol_m = re.search(r'tomo\s*0*(\d+)', part_stem, re.IGNORECASE)
                                        if vol_m:
                                            failed_volume_nums.add(int(vol_m.group(1)))
                                    else:
                                        converted_files.append(p.name)
                                        logger.info(f"✅ Found output: {p.name} ({output_size_mb:.1f}MB)")
                            else:
                                logger.error(f"Expected output not found: {temp_output}")
                                all_success = False
                    else:
                        logger.error(f"❌ Conversion failed: {normalized_file.name}")
                        all_success = False

                    # Limpiar archivo temporal
                    normalized_file.unlink(missing_ok=True)

                # Si necesitamos más partes, reintentar — pero conservar archivos de tomos que sí cupieron
                if needs_more_parts and retry_count < MAX_CONVERSION_RETRIES:
                    logger.info("Cleaning up and retrying with more parts...")
                    failed_count = 0
                    for f in converted_files:
                        vol_m = re.search(r'tomo\s*0*(\d+)', f, re.IGNORECASE)
                        file_vol = int(vol_m.group(1)) if vol_m else None
                        if file_vol is not None and file_vol not in failed_volume_nums:
                            # Este tomo convirtió bien → conservar, no volver a procesar
                            prior_converted.append(f)
                            skip_volumes.add(file_vol)
                        else:
                            # Este tomo falló (o no tiene nº de tomo) → borrar y reintentar
                            (OUTPUT_DIR / f).unlink(missing_ok=True)

                    # min_parts basado sólo en tomos que fallaron
                    failed_count = len(failed_volume_nums) if failed_volume_nums else len(normalized_files)
                    if max_output_size_found > 0:
                        extra_factor = int(max_output_size_found / MAX_OUTPUT_SIZE_MB) + 1
                        min_parts = max(min_parts * extra_factor, failed_count + extra_factor)
                    else:
                        min_parts = min_parts * 2

                    logger.info(f"Next attempt will use min_parts={min_parts}")
                    continue

                # Si llegamos aquí, terminamos (éxito o fallo sin posibilidad de retry)
                break

            # Combinar archivos de todos los intentos
            converted_files = prior_converted + converted_files

            if all_success and converted_files and not needs_more_parts:
                # Limpiar archivo original solo si todas las partes se convirtieron correctamente
                file_path.unlink(missing_ok=True)
                # Limpiar archivo de metadatos si existe
                metadata_path = file_path.with_suffix('.metadata.json')
                metadata_path.unlink(missing_ok=True)
                logger.info(f"✅ All parts converted: {', '.join(converted_files)}")
            elif converted_files:
                logger.warning(f"⚠️ Partial success: {', '.join(converted_files)}")
            elif needs_more_parts:
                logger.error(f"❌ Failed after {MAX_CONVERSION_RETRIES} attempts - output still exceeds {MAX_OUTPUT_SIZE_MB}MB")

        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)

        finally:
            self.processing.discard(str(file_path))

    def extract_archive(self, archive_path: Path, output_dir: Path) -> bool:
        ext = archive_path.suffix.lower()
        
        result = subprocess.run(
            ['7z', 'x', str(archive_path), f'-o{output_dir}', '-y', '-aos'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return True
        
        # Si 7z falla con "unsupported method", intentar con unrar
        # Esto puede pasar con archivos RAR guardados como .cbz o con RAR5/RAR moderno
        stderr_lower = result.stderr.lower() if result.stderr else ''
        stdout_lower = result.stdout.lower() if result.stdout else ''
        
        if 'unsupported method' in stderr_lower or 'unsupported method' in stdout_lower:
            logger.warning(f"7z failed (unsupported method), trying unrar: {archive_path.name}")
            
            result_unrar = subprocess.run(
                ['unrar', 'x', '-o+', str(archive_path), str(output_dir) + '/'],
                capture_output=True,
                text=True
            )
            
            if result_unrar.returncode == 0:
                return True
                
            logger.error(f"unrar also failed: {result_unrar.stderr}")
            return False
        
        # Para archivos RAR/CBR, siempre intentar unrar como fallback
        if ext in ['.cbr', '.rar']:
            logger.warning(f"7z failed, trying unrar: {archive_path.name}")
            
            result_unrar = subprocess.run(
                ['unrar', 'x', '-o+', str(archive_path), str(output_dir) + '/'],
                capture_output=True,
                text=True
            )
            
            if result_unrar.returncode == 0:
                return True
                
            logger.error(f"unrar failed: {result_unrar.stderr}")
        else:
            logger.error(f"7z error: {result.stderr}")
            
        return False

    def validate_image(self, image_path: Path) -> bool:
        if not HAS_PIL:
            return image_path.stat().st_size > 0
            
        try:
            with Image.open(image_path) as img:
                img.verify()
            return True
        except Exception:
            logger.warning(f"Corrupted image (skipping): {image_path.name}")
            return False

    def _detect_volume_folders(self, extract_dir: Path) -> dict[int, list]:
        """
        Detecta carpetas de tomos dentro del archivo extraído.
        Busca patrones como "Tomo 01", "Vol 1", "Volume 01", "T01", etc.
        También detecta carpetas creadas por extracción de CBRs anidados como:
        "_extracted_Gantz - Tomo 01 (#001-010)"

        Returns:
            Dict mapping volume number -> dict with 'folder' and 'images' keys
        """
        import re

        volumes = {}

        # Patrones para detectar número de tomo en el nombre de carpeta
        # Orden de prioridad: más específico primero
        volume_patterns = [
            # "Tomo 01", "Tomo 1", "tomo01", "Tomo-01"
            (re.compile(r'tomo\s*[_\-\.\s]*(\d+)', re.IGNORECASE), "tomo"),
            # "Vol 01", "Volume 1", "vol.01"
            (re.compile(r'vol(?:ume)?\.?\s*[_\-\s]*(\d+)', re.IGNORECASE), "vol"),
            # "T01", "T.01", "T-01" (común en releases) - solo si es al principio o después de espacio
            (re.compile(r'(?:^|\s|_)T\.?\s*[_\-]?\s*(\d+)(?:\D|$)', re.IGNORECASE), "T"),
        ]

        # Buscar todas las carpetas (incluyendo las creadas al extraer archivos anidados)
        all_folders = [item for item in extract_dir.rglob('*') if item.is_dir()]

        logger.info(f"Scanning {len(all_folders)} folders for volume structure...")
        if all_folders:
            logger.info(f"Folder names: {[f.name for f in all_folders[:10]]}")  # Log primeras 10

        for item in all_folders:
            folder_name = item.name

            # Intentar cada patrón
            for pattern, pattern_name in volume_patterns:
                match = pattern.search(folder_name)
                if match:
                    vol_num = int(match.group(1))
                    # Evitar números muy altos que probablemente no sean tomos
                    if 1 <= vol_num <= 999:
                        if vol_num not in volumes:
                            volumes[vol_num] = {'folder': item, 'images': []}
                            logger.info(f"Found volume {vol_num} folder (pattern: {pattern_name}): {folder_name}")
                        break  # Usar primer patrón que coincida

        # Si encontramos carpetas de tomos, recolectar imágenes de cada una
        if volumes:
            logger.info(f"Detected {len(volumes)} volume folders: {sorted(volumes.keys())}")
            # Incluir tanto minúsculas como mayúsculas (Linux es case-sensitive)
            image_extensions = (
                '*.jpg', '*.jpeg', '*.png', '*.webp', '*.gif',
                '*.JPG', '*.JPEG', '*.PNG', '*.WEBP', '*.GIF',
                '*.Jpg', '*.Jpeg', '*.Png',  # Casos mixtos comunes
            )

            for vol_num, vol_data in volumes.items():
                folder = vol_data['folder']
                seen_paths = set()  # Evitar duplicados
                for ext in image_extensions:
                    for img_path in folder.rglob(ext):
                        # Evitar duplicados (por si coincide con múltiples patrones)
                        if img_path in seen_paths:
                            continue
                        seen_paths.add(img_path)
                        
                        if self.should_skip_file(img_path.name):
                            continue
                        if self.validate_image(img_path):
                            size_bytes = img_path.stat().st_size
                            vol_data['images'].append((img_path, size_bytes))

                # Ordenar con detección de patrón + natural sort
                vol_data['images'] = _detect_and_sort_images(
                    vol_data['images'], label=f"Tomo {vol_num}"
                )
                # Eliminar duplicados con sufijos 'copia'/'-min'
                vol_data['images'] = _deduplicate_variant_pages(
                    vol_data['images'], label=f"Tomo {vol_num}"
                )
                logger.info(f"Volume {vol_num}: {len(vol_data['images'])} images found")

            # Filtrar volúmenes sin imágenes
            volumes = {k: v for k, v in volumes.items() if v['images']}

            if volumes:
                logger.info(f"Volumes with images: {sorted(volumes.keys())}")
        else:
            logger.info("No volume folders detected - will process as single archive")

        return volumes

    def normalize_archive(self, file_path: Path, metadata: dict = None, min_parts: int = 1, skip_volumes: set = None) -> list[Path] | None:
        """
        Crea archivo(s) temporal(es) .clean.cbz para procesamiento interno.

        IMPORTANTE: Si el archivo contiene múltiples tomos (carpetas Tomo 01, Tomo 02, etc.),
        cada tomo se convierte por separado en lugar de dividir arbitrariamente.

        Si el archivo es muy grande y NO tiene estructura de tomos, lo divide en partes
        para cumplir el límite de 200MB.

        Incluye ComicInfo.xml si hay metadatos disponibles.
        Retorna una lista de paths a los CBZ normalizados.

        Args:
            min_parts: Número mínimo de partes (usado en reintentos si el output excede el límite)
        """
        temp_extract_dir = Path(tempfile.mkdtemp())

        try:
            logger.info(f"Extracting {file_path.name}...")

            if not self.extract_archive(file_path, temp_extract_dir):
                raise RuntimeError("Extraction failed")

            # Extraer anidados
            nested_archives = [
                p for p in temp_extract_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in ['.cbr', '.rar', '.zip', '.cbz']
                and not self.should_skip_file(p.name)
            ]

            for archive in nested_archives:
                nested_dir = archive.parent / f"_extracted_{archive.stem}"
                nested_dir.mkdir(exist_ok=True)

                if self.extract_archive(archive, nested_dir):
                    archive.unlink(missing_ok=True)

            # NUEVO: Detectar si hay múltiples tomos en carpetas separadas
            volume_folders = self._detect_volume_folders(temp_extract_dir)

            # Excluir tomos ya convertidos exitosamente en intentos anteriores
            if skip_volumes and volume_folders:
                before = set(volume_folders.keys())
                volume_folders = {k: v for k, v in volume_folders.items() if k not in skip_volumes}
                skipped = before - set(volume_folders.keys())
                if skipped:
                    logger.info(f"Skipping already-converted volumes: {sorted(skipped)}")
                if not volume_folders:
                    logger.info("All volumes already converted in previous attempts")
                    return []

            # Use volume-aware path when:
            # - archive has multiple volumes (normal multi-tomo case), OR
            # - we are in a retry that skip_volumes reduced to a single remaining volume
            #   (without this check the rglob below would scan ALL extracted dirs and
            #   produce flat "Parte N" files mixing pages from all volumes)
            if len(volume_folders) > 1 or (skip_volumes and volume_folders):
                logger.info(f"📚 Detected {len(volume_folders)} separate volumes in archive: {sorted(volume_folders.keys())}")
                if min_parts <= 1:
                    # First attempt: check if any volume is large enough to need splitting
                    is_comic = bool(metadata and (metadata.get('comicvine_id') or metadata.get('publisher')))
                    size_factor = 2.5 if is_comic else 1.3
                    needs_split = False
                    for vol_num, vol_data in volume_folders.items():
                        vol_size_mb = sum(s for _, s in vol_data['images']) / (1024 * 1024)
                        estimated_epub = vol_size_mb * size_factor
                        if estimated_epub > MAX_OUTPUT_SIZE_MB:
                            needs_split = True
                            break
                    if not needs_split:
                        return self._create_volume_cbzs(file_path.stem, volume_folders, metadata)
                    logger.info(f"Some volumes estimated to exceed {MAX_OUTPUT_SIZE_MB}MB, splitting proactively")

                # Split each volume based on its estimated output size
                is_comic = bool(metadata and (metadata.get('comicvine_id') or metadata.get('publisher')))
                size_factor = 2.5 if is_comic else 1.3
                per_volume_parts = {}
                for vol_num, vol_data in volume_folders.items():
                    vol_size_mb = sum(s for _, s in vol_data['images']) / (1024 * 1024)
                    estimated_epub = vol_size_mb * size_factor
                    parts_needed = max(1, int(estimated_epub / MAX_OUTPUT_SIZE_MB) + 1)
                    if min_parts > 1:
                        parts_needed = max(parts_needed, max(2, min_parts // len(volume_folders)))
                    per_volume_parts[vol_num] = parts_needed
                    logger.info(f"Volume {vol_num}: {vol_size_mb:.0f}MB raw -> ~{estimated_epub:.0f}MB EPUB -> {parts_needed} parts")

                max_parts = max(per_volume_parts.values())
                logger.info(f"Splitting volumes into up to {max_parts} parts each")
                return self._create_volume_cbzs_split(file_path.stem, volume_folders, metadata, max_parts)

            # Si solo hay un tomo o no hay estructura de carpetas, proceder normal
            # Colectar imágenes válidas con sus tamaños
            # Incluir tanto minúsculas como mayúsculas (Linux es case-sensitive)
            image_extensions = (
                '*.jpg', '*.jpeg', '*.png', '*.webp', '*.gif',
                '*.JPG', '*.JPEG', '*.PNG', '*.WEBP', '*.GIF',
                '*.Jpg', '*.Jpeg', '*.Png',  # Casos mixtos comunes
            )
            image_files = []
            seen_paths = set()  # Evitar duplicados

            for ext in image_extensions:
                for img_path in temp_extract_dir.rglob(ext):
                    # Evitar duplicados
                    if img_path in seen_paths:
                        continue
                    seen_paths.add(img_path)
                    
                    if self.should_skip_file(img_path.name):
                        continue
                    if self.validate_image(img_path):
                        size_bytes = img_path.stat().st_size
                        image_files.append((img_path, size_bytes))
                    else:
                        img_path.unlink(missing_ok=True)

            if not image_files:
                raise RuntimeError("No valid images found")

            # Ordenar con detección de patrón + natural sort
            image_files = _detect_and_sort_images(image_files, label=file_path.stem)
            # Eliminar duplicados con sufijos 'copia'/'-min' (ej: AoT t33 cap 132)
            image_files = _deduplicate_variant_pages(image_files, label=file_path.stem)

            # Calcular tamaño total
            total_size_mb = sum(size for _, size in image_files) / (1024 * 1024)

            # Comics a color generan EPUBs ~2.5x más grandes que las imágenes extraídas
            # Manga B/N es ~1.3x. Usar metadata para detectar tipo
            # Si el output excede 180MB, el retry loop en process_file() lo divide automáticamente
            is_comic = bool(metadata and (metadata.get('comicvine_id') or metadata.get('publisher')))
            size_factor = 2.5 if is_comic else 1.3
            estimated_epub_size = total_size_mb * size_factor

            logger.info(f"Total images: {len(image_files)}, Size: {total_size_mb:.1f}MB, Estimated EPUB: {estimated_epub_size:.1f}MB ({'comic' if is_comic else 'manga'} factor={size_factor}x)")

            # Determinar si necesitamos dividir
            estimated_output_size = total_size_mb * size_factor
            num_parts = max(min_parts, int(estimated_output_size / MAX_OUTPUT_SIZE_MB) + 1)

            if num_parts == 1 and min_parts == 1:
                # No necesita división, crear un solo CBZ
                return self._create_single_cbz(file_path.stem, image_files, metadata)
            else:
                # Dividir en partes
                logger.info(f"Splitting into {num_parts} parts (min_parts={min_parts})")
                return self._create_split_cbz(file_path.stem, image_files, num_parts, metadata)

        except Exception as e:
            logger.error(f"Normalization error: {e}")
            return None

        finally:
            shutil.rmtree(temp_extract_dir, ignore_errors=True)

    def _create_single_cbz(self, stem: str, image_files: list, metadata: dict = None) -> list[Path]:
        """Crea un único CBZ normalizado con ComicInfo.xml si hay metadatos"""
        clean_cbz_path = Path(tempfile.gettempdir()) / f"{stem}.clean.cbz"

        if clean_cbz_path.exists():
            clean_cbz_path.unlink()

        with zipfile.ZipFile(clean_cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            if metadata:
                try:
                    comicinfo_xml = generate_comicinfo_xml(metadata)
                    zf.writestr("ComicInfo.xml", comicinfo_xml)
                    logger.info(f"ComicInfo.xml added for: {stem}")
                except Exception as e:
                    logger.warning(f"Could not generate ComicInfo.xml: {e}")

            # Renombrar a secuencial zero-padded (0001.jpg, 0002.jpg, ...)
            # CRÍTICO: KCC ordena el CBZ alfabéticamente al leerlo.
            # Si conservamos nombres originales (ej: 1.jpg, 10.jpg, 18.jpg)
            # KCC los leería en orden léxico incorrecto aunque nosotros los
            # hayamos ordenado bien. El renombrado garantiza el orden correcto.
            for i, (img_path, _) in enumerate(image_files):
                ext = img_path.suffix.lower()
                arc_name = f"{i + 1:04d}{ext}"
                zf.write(img_path, arc_name)

        logger.info(f"Created: {clean_cbz_path.name} ({len(image_files)} images)")
        return [clean_cbz_path]

    def _create_volume_cbzs(self, stem: str, volume_folders: dict, metadata: dict = None) -> list[Path]:
        """
        Crea un CBZ separado para cada tomo detectado en el archivo.
        Esto es diferente de _create_split_cbz porque respeta la estructura original de tomos.
        """
        result_paths = []

        # Extraer nombre base del manga (quitar info de rango y tomo del nombre)
        import re
        base_name = stem
        # Quitar rangos como "[001-004]" o "[07-12]"
        base_name = re.sub(r'\s*\[?\d+\s*-\s*\d+\]?\s*$', '', base_name).strip()
        # Quitar "- Tomo 007" o "Tomo 007" del final
        base_name = re.sub(r'\s*-?\s*tomo\s*\d+\s*$', '', base_name, flags=re.IGNORECASE).strip()
        # Quitar "tomos" suelto
        base_name = re.sub(r'\s*tomos?\s*$', '', base_name, flags=re.IGNORECASE).strip()
        # Quitar guiones finales
        base_name = base_name.rstrip(' -')

        for vol_num in sorted(volume_folders.keys()):
            vol_data = volume_folders[vol_num]
            image_files = vol_data['images']

            if not image_files:
                continue

            # Nombre: "Manga - Tomo 001.clean.cbz"
            vol_name = f"{base_name} - Tomo {vol_num:03d}"
            clean_cbz_path = Path(tempfile.gettempdir()) / f"{vol_name}.clean.cbz"

            if clean_cbz_path.exists():
                clean_cbz_path.unlink()

            with zipfile.ZipFile(clean_cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                if metadata:
                    try:
                        vol_metadata = metadata.copy()
                        vol_metadata['volume_number'] = vol_num
                        vol_metadata['chapter_title'] = f"Tomo {vol_num}"
                        comicinfo_xml = generate_comicinfo_xml(vol_metadata)
                        zf.writestr("ComicInfo.xml", comicinfo_xml)
                        logger.info(f"ComicInfo.xml added for: {vol_name}")
                    except Exception as e:
                        logger.warning(f"Could not generate ComicInfo.xml: {e}")

                # Renombrar a secuencial para garantizar orden correcto en KCC
                for i, (img_path, _) in enumerate(image_files):
                    ext = img_path.suffix.lower()
                    arc_name = f"{i + 1:04d}{ext}"
                    zf.write(img_path, arc_name)

            vol_size = sum(p.stat().st_size for p, _ in image_files) / (1024 * 1024)
            logger.info(f"📖 Created volume {vol_num}: {clean_cbz_path.name} ({len(image_files)} images, ~{vol_size:.1f}MB)")
            result_paths.append(clean_cbz_path)

        return result_paths

    def _create_volume_cbzs_split(self, stem: str, volume_folders: dict, metadata: dict = None, parts_per_volume: int = 2) -> list[Path]:
        """
        Like _create_volume_cbzs, but splits each volume into multiple parts
        so the converted EPUB stays under MAX_OUTPUT_SIZE_MB.
        """
        import re
        result_paths = []

        base_name = stem
        base_name = re.sub(r'\s*\[?\d+\s*-\s*\d+\]?\s*$', '', base_name).strip()
        base_name = re.sub(r'\s*-?\s*tomo\s*\d+\s*$', '', base_name, flags=re.IGNORECASE).strip()
        base_name = re.sub(r'\s*tomos?\s*$', '', base_name, flags=re.IGNORECASE).strip()
        base_name = base_name.rstrip(' -')

        for vol_num in sorted(volume_folders.keys()):
            vol_data = volume_folders[vol_num]
            image_files = vol_data['images']
            if not image_files:
                continue

            # Use ceiling division so 189 images / 2 parts = 95+94 (not 94+94+1)
            import math
            images_per_part = max(10, math.ceil(len(image_files) / parts_per_volume))
            actual_parts = math.ceil(len(image_files) / images_per_part)

            for part_idx in range(actual_parts):
                start = part_idx * images_per_part
                end = min(start + images_per_part, len(image_files))
                part_images = image_files[start:end]

                vol_name = f"{base_name} - Tomo {vol_num:03d} - Parte {part_idx + 1}"
                clean_cbz_path = Path(tempfile.gettempdir()) / f"{vol_name}.clean.cbz"
                if clean_cbz_path.exists():
                    clean_cbz_path.unlink()

                with zipfile.ZipFile(clean_cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    if metadata:
                        try:
                            vol_metadata = metadata.copy()
                            vol_metadata['volume_number'] = vol_num
                            vol_metadata['chapter_title'] = f"Tomo {vol_num}"
                            comicinfo_xml = generate_comicinfo_xml(vol_metadata, part_number=part_idx + 1)
                            zf.writestr("ComicInfo.xml", comicinfo_xml)
                        except Exception as e:
                            logger.warning(f"Could not generate ComicInfo.xml: {e}")

                    # Renombrar a secuencial para garantizar orden correcto en KCC
                    for i, (img_path, _) in enumerate(part_images):
                        ext = img_path.suffix.lower()
                        arc_name = f"{i + 1:04d}{ext}"
                        zf.write(img_path, arc_name)

                part_size = sum(p.stat().st_size for p, _ in part_images) / (1024 * 1024)
                logger.info(f"📖 Created volume {vol_num} part {part_idx + 1}/{actual_parts}: {clean_cbz_path.name} ({len(part_images)} images, ~{part_size:.1f}MB)")
                result_paths.append(clean_cbz_path)

        return result_paths

    def _create_split_cbz(self, stem: str, image_files: list, num_parts: int, metadata: dict = None) -> list[Path]:
        """Divide las imágenes en múltiples CBZ con ComicInfo.xml si hay metadatos"""
        images_per_part = len(image_files) // num_parts
        if images_per_part < 10:
            images_per_part = 10  # Mínimo 10 imágenes por parte
            num_parts = len(image_files) // images_per_part + 1

        result_paths = []

        for part_num in range(num_parts):
            start_idx = part_num * images_per_part
            end_idx = start_idx + images_per_part if part_num < num_parts - 1 else len(image_files)

            if start_idx >= len(image_files):
                break

            part_images = image_files[start_idx:end_idx]

            # Nombre con parte
            part_name = f"{stem} - Parte {part_num + 1}"
            clean_cbz_path = Path(tempfile.gettempdir()) / f"{part_name}.clean.cbz"

            if clean_cbz_path.exists():
                clean_cbz_path.unlink()

            with zipfile.ZipFile(clean_cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                if metadata:
                    try:
                        comicinfo_xml = generate_comicinfo_xml(metadata, part_number=part_num + 1)
                        zf.writestr("ComicInfo.xml", comicinfo_xml)
                        logger.info(f"ComicInfo.xml added for: {part_name}")
                    except Exception as e:
                        logger.warning(f"Could not generate ComicInfo.xml: {e}")

                # Renombrar a secuencial para garantizar orden correcto en KCC
                for i, (img_path, _) in enumerate(part_images):
                    ext = img_path.suffix.lower()
                    arc_name = f"{i + 1:04d}{ext}"
                    zf.write(img_path, arc_name)

            part_size = sum(p.stat().st_size for p, _ in part_images) / (1024 * 1024)
            logger.info(f"Created part {part_num + 1}/{num_parts}: {clean_cbz_path.name} ({len(part_images)} images, ~{part_size:.1f}MB)")
            result_paths.append(clean_cbz_path)

        return result_paths

    def wait_for_lock_release(self, file_path: Path, timeout: int = 1800) -> bool:
        """
        Espera hasta que el lock file sea eliminado (descarga completada)
        Timeout por defecto: 30 minutos (para archivos grandes)
        """
        lock_file = file_path.parent / f"{file_path.name}.downloading"
        elapsed = 0
        check_interval = 5  # Chequear cada 5 segundos

        while elapsed < timeout:
            if not lock_file.exists():
                return True

            if elapsed % 60 == 0:  # Log cada minuto
                logger.info(f"Still waiting for download: {file_path.name} ({elapsed}s)")

            time.sleep(check_interval)
            elapsed += check_interval

        # Timeout - eliminar lock file huérfano
        logger.warning(f"Lock timeout, removing stale lock: {lock_file.name}")
        lock_file.unlink(missing_ok=True)
        return False

    def wait_for_file_complete(self, file_path: Path, timeout: int = 120) -> bool:
        """Espera a que el archivo esté estable (sin cambios de tamaño)"""
        last_size = -1
        stable_count = 0
        elapsed = 0

        while elapsed < timeout:
            if not file_path.exists():
                return False

            try:
                current_size = file_path.stat().st_size
            except OSError:
                return False

            if current_size == last_size:
                stable_count += 1
                if stable_count >= 5:  # 5 segundos estable
                    return True
            else:
                stable_count = 0
                last_size = current_size

            time.sleep(1)
            elapsed += 1

        return stable_count >= 5

    def verify_archive_integrity(self, file_path: Path) -> bool:
        """Verifica que el archivo es un archivo válido (detecta formato por magic bytes)"""
        if not file_path.exists():
            return False

        # Tamaño mínimo
        if file_path.stat().st_size < 1024:
            logger.warning(f"File too small: {file_path.name}")
            return False

        # Detectar formato real por magic bytes
        actual_format = self._detect_archive_format(file_path)
        logger.info(f"Detected format: {actual_format} for {file_path.name}")

        # Verificar ZIP
        if actual_format == 'zip':
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    bad_file = zf.testzip()
                    if bad_file:
                        logger.error(f"Corrupted file in archive: {bad_file}")
                        return False
                    if len(zf.namelist()) == 0:
                        logger.error(f"Empty archive: {file_path.name}")
                        return False
                return True
            except zipfile.BadZipFile:
                logger.error(f"Invalid ZIP: {file_path.name}")
                return False
            except Exception as e:
                logger.error(f"Error verifying archive: {e}")
                return False

        # Verificar RAR (puede estar guardado como .cbz)
        if actual_format == 'rar':
            logger.info(f"RAR archive detected (extension: {file_path.suffix}): {file_path.name}")
            # Primero intentar con 7z
            result = subprocess.run(
                ['7z', 't', str(file_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info(f"RAR archive verified with 7z: {file_path.name}")
                return True
            
            # Si 7z falla con "Unsupported Method", intentar con unrar
            if 'unsupported method' in result.stderr.lower() or 'unsupported method' in result.stdout.lower():
                logger.info(f"7z doesn't support compression method, trying unrar for verification...")
                result_unrar = subprocess.run(
                    ['unrar', 't', str(file_path)],
                    capture_output=True,
                    text=True
                )
                if result_unrar.returncode == 0:
                    logger.info(f"RAR archive verified with unrar: {file_path.name}")
                    return True
                else:
                    logger.error(f"RAR integrity check failed with unrar: {file_path.name}")
                    logger.error(f"unrar stderr: {result_unrar.stderr[:500] if result_unrar.stderr else 'None'}")
                    return False
            else:
                logger.error(f"RAR integrity check failed: {file_path.name}")
                logger.error(f"7z stderr: {result.stderr[:500] if result.stderr else 'None'}")
                return False

        # Para RAR/CBR por extensión (fallback)
        if file_path.suffix.lower() in ['.rar', '.cbr']:
            result = subprocess.run(
                ['7z', 't', str(file_path)],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.error(f"RAR integrity check failed: {file_path.name}")
                return False
            return True

        # Formato desconocido pero archivo existe con tamaño decente
        logger.warning(f"Unknown archive format for {file_path.name}, accepting based on size")
        return True

    def _detect_archive_format(self, file_path: Path) -> str:
        """Detecta el formato de archivo por magic bytes"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(8)

            # ZIP: PK\x03\x04
            if header[:4] in [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08']:
                return 'zip'

            # RAR: Rar!\x1a\x07
            if header[:6] == b'Rar!\x1a\x07' or header[:7] == b'Rar!\x1a\x07\x00' or header[:7] == b'Rar!\x1a\x07\x01':
                return 'rar'

            return 'unknown'
        except Exception as e:
            logger.warning(f"Error detecting archive format: {e}")
            return 'unknown'

    def convert_with_kcc(self, input_file: Path, metadata: dict = None) -> bool:
        # Recargar configuración antes de cada conversión
        load_kcc_config()

        # Detectar si es comic americano (no usar manga mode)
        is_comic = bool(metadata and (metadata.get('comicvine_id') or metadata.get('publisher')))
        is_manga = not is_comic

        # NOTA: NO usar '-q' — en KCC v9.7+ significa '--hq' (Panel View),
        # que hace que el Kindle amplíe automáticamente paneles individuales.
        # En versiones antiguas '-q' era modo silencioso (sin efecto en Panel View).
        cmd = [
            'kcc-c2e',
            str(input_file),
            '-p', KCC_PROFILE,
            '-f', KCC_FORMAT,
            '-o', str(OUTPUT_DIR),
            '--jpeg-quality', KCC_QUALITY,
            '--forcecolor'
        ]

        # Solo agregar -m (manga mode: derecha→izquierda) para manga
        if is_manga:
            cmd.append('-m')
        else:
            logger.info(f"Comic mode: skipping manga flag (-m) for {input_file.name}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                logger.error(f"KCC error (returncode={result.returncode})")
                logger.error(f"KCC stdout: {result.stdout}")
                logger.error(f"KCC stderr: {result.stderr}")
                return False
                
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("KCC timeout")
            return False
        except Exception as e:
            logger.error(f"KCC execution error: {e}")
            return False


def scan_existing_files(handler: ArchiveHandler):
    logger.info(f"Scanning {WATCH_DIR} for existing files...")
    for file_path in WATCH_DIR.iterdir():
        if handler.is_supported(file_path):
            handler.process_file(file_path)


def main():
    logger.info("KCC Converter Started (No-suffix version)")
    logger.info(f"Profile: {KCC_PROFILE} | Format: {KCC_FORMAT}")

    handler = ArchiveHandler()
    observer = Observer()
    observer.schedule(handler, str(WATCH_DIR), recursive=False)
    observer.start()

    scan_existing_files(handler)

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


if __name__ == '__main__':
    main()