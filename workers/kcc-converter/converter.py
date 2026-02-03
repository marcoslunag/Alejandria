"""
Alejandria - KCC Converter Worker
Normalizes archives before sending to KCC.
FINAL VERSION: Output filenames preserve original names (no .clean suffix)
"""

import os
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
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', '/manga/kindle'))
KCC_CONFIG_FILE = WATCH_DIR / '.kcc_config.json'

# Defaults (can be overridden by config file)
KCC_PROFILE = os.getenv('KCC_PROFILE', 'KPW5')
KCC_FORMAT = os.getenv('KCC_FORMAT', 'MOBI')  # MOBI para Kindle nativo
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
    Genera ComicInfo.xml desde metadatos del manga
    Formato compatible con ComicRack/KCC
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

    # Serie
    add_elem("Series", metadata.get('title', 'Unknown'))

    # Volumen
    volume = metadata.get('volume_number', 1)
    add_elem("Volume", str(volume))
    add_elem("Number", str(volume))

    # Titulo
    title = metadata.get('chapter_title') or f"Tomo {volume}"
    if part_number:
        title = f"{title} - Parte {part_number}"
    add_elem("Title", title)

    # Sinopsis
    if metadata.get('description'):
        desc = metadata['description'].replace('\r\n', '\n').replace('\r', '\n')
        # Limpiar tags HTML basicos
        import re
        desc = re.sub(r'<[^>]+>', '', desc)
        add_elem("Summary", desc[:2000])  # Limitar longitud

    # Autores/Artistas
    if metadata.get('authors'):
        add_elem("Writer", ", ".join(metadata['authors'][:3]))

    if metadata.get('artists'):
        artists = ", ".join(metadata['artists'][:3])
        add_elem("Penciller", artists)
        add_elem("Inker", artists)
    elif metadata.get('authors'):
        add_elem("Penciller", ", ".join(metadata['authors'][:3]))

    # Generos
    if metadata.get('genres'):
        add_elem("Genre", ", ".join(metadata['genres'][:5]))

    # Fecha
    start_date = metadata.get('start_date')
    if start_date:
        try:
            if len(start_date) >= 4:
                add_elem("Year", start_date[:4])
            if len(start_date) >= 7:
                add_elem("Month", start_date[5:7])
            if len(start_date) >= 10:
                add_elem("Day", start_date[8:10])
        except (ValueError, IndexError):
            pass

    # Idioma
    add_elem("LanguageISO", "es")

    # Formato manga
    add_elem("Manga", "Yes")
    add_elem("BlackAndWhite", "Yes")

    # URL de referencia
    if metadata.get('anilist_url'):
        add_elem("Web", metadata['anilist_url'])

    # Notas
    score = metadata.get('average_score')
    notes = f"Importado de AniList. Score: {score}/100" if score else "Importado de AniList"
    add_elem("Notes", notes)

    # Tags
    if metadata.get('tags'):
        tags = metadata['tags'][:10]
        add_elem("Tags", ", ".join(str(t) for t in tags))

    # Clasificacion de edad
    if metadata.get('is_adult'):
        add_elem("AgeRating", "Adults Only 18+")
    elif metadata.get('genres'):
        genres_lower = [g.lower() for g in metadata['genres']]
        if any(g in genres_lower for g in ['ecchi', 'gore', 'violencia']):
            add_elem("AgeRating", "Mature 17+")

    # Pais/Editorial
    country = metadata.get('country')
    if country:
        country_names = {'JP': 'Japon', 'KR': 'Corea del Sur', 'CN': 'China', 'TW': 'Taiwan'}
        add_elem("Publisher", country_names.get(country, country))

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

            while retry_count < MAX_CONVERSION_RETRIES:
                retry_count += 1
                logger.info(f"Conversion attempt {retry_count}/{MAX_CONVERSION_RETRIES} (min_parts={min_parts})")

                # normalize_archive ahora retorna una lista de CBZs
                normalized_files = self.normalize_archive(file_path, metadata, min_parts=min_parts)

                if not normalized_files:
                    logger.error("Normalization failed.")
                    return

                all_success = True
                converted_files = []
                needs_more_parts = False
                max_output_size_found = 0

                for normalized_file in normalized_files:
                    if not normalized_file.exists():
                        logger.error(f"Normalized file not found: {normalized_file}")
                        all_success = False
                        continue

                    # El stem del archivo normalizado ya incluye " - Parte X" si fue dividido
                    part_stem = normalized_file.stem.replace('.clean', '')

                    logger.info(f"Starting conversion: {normalized_file.name}")
                    success = self.convert_with_kcc(normalized_file)

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

                # Si necesitamos más partes, limpiar los archivos ya convertidos y reintentar
                if needs_more_parts and retry_count < MAX_CONVERSION_RETRIES:
                    logger.info(f"Cleaning up and retrying with more parts...")
                    for f in converted_files:
                        output_path = OUTPUT_DIR / f
                        output_path.unlink(missing_ok=True)
                    converted_files.clear()

                    # Calcular cuántas partes adicionales necesitamos
                    # Si el máximo encontrado fue X MB y el límite es Y MB, necesitamos ceil(X/Y) veces más partes
                    if max_output_size_found > 0:
                        extra_factor = int(max_output_size_found / MAX_OUTPUT_SIZE_MB) + 1
                        min_parts = max(min_parts * extra_factor, len(normalized_files) + extra_factor)
                    else:
                        min_parts = min_parts * 2

                    logger.info(f"Next attempt will use min_parts={min_parts}")
                    continue

                # Si llegamos aquí, terminamos (éxito o fallo sin posibilidad de retry)
                break

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
            
        if 'unsupported method' in result.stderr.lower() and ext in ['.cbr', '.rar']:
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

    def normalize_archive(self, file_path: Path, metadata: dict = None, min_parts: int = 1) -> list[Path] | None:
        """
        Crea archivo(s) temporal(es) .clean.cbz para procesamiento interno.
        Si el archivo es muy grande, lo divide en partes para cumplir el límite de 200MB.
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

            # Colectar imágenes válidas con sus tamaños
            image_extensions = ('*.jpg', '*.jpeg', '*.png', '*.webp', '*.gif')
            image_files = []

            for ext in image_extensions:
                for img_path in temp_extract_dir.rglob(ext):
                    if self.should_skip_file(img_path.name):
                        continue
                    if self.validate_image(img_path):
                        size_bytes = img_path.stat().st_size
                        image_files.append((img_path, size_bytes))
                    else:
                        img_path.unlink(missing_ok=True)

            if not image_files:
                raise RuntimeError("No valid images found")

            # Ordenar por nombre
            image_files.sort(key=lambda x: x[0].name)

            # Calcular tamaño total
            total_size_mb = sum(size for _, size in image_files) / (1024 * 1024)
            # Estimamos que el EPUB será ~1.1x el tamaño de las imágenes (compresión + metadatos)
            estimated_epub_size = total_size_mb * 1.1

            logger.info(f"Total images: {len(image_files)}, Size: {total_size_mb:.1f}MB, Estimated EPUB: {estimated_epub_size:.1f}MB")

            # Determinar si necesitamos dividir
            # Usar factor 1.3 para ser más conservador con la estimación
            estimated_output_size = total_size_mb * 1.3
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

        seen_names = set()
        final_images = []

        for img_path, _ in image_files:
            name = img_path.name
            counter = 1
            original_name = name

            while name in seen_names:
                s = Path(original_name).stem
                suffix = Path(original_name).suffix
                name = f"{s}_{counter:03d}{suffix}"
                counter += 1

            seen_names.add(name)
            final_images.append((img_path, name))

        with zipfile.ZipFile(clean_cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Insertar ComicInfo.xml si hay metadatos
            if metadata:
                try:
                    comicinfo_xml = generate_comicinfo_xml(metadata)
                    zf.writestr("ComicInfo.xml", comicinfo_xml)
                    logger.info(f"ComicInfo.xml added for: {stem}")
                except Exception as e:
                    logger.warning(f"Could not generate ComicInfo.xml: {e}")

            for src_path, arc_name in final_images:
                zf.write(src_path, arc_name)

        logger.info(f"Created: {clean_cbz_path.name} ({len(final_images)} images)")
        return [clean_cbz_path]

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

            seen_names = set()
            final_images = []

            for img_path, _ in part_images:
                name = img_path.name
                counter = 1
                original_name = name

                while name in seen_names:
                    s = Path(original_name).stem
                    suffix = Path(original_name).suffix
                    name = f"{s}_{counter:03d}{suffix}"
                    counter += 1

                seen_names.add(name)
                final_images.append((img_path, name))

            with zipfile.ZipFile(clean_cbz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Insertar ComicInfo.xml con numero de parte
                if metadata:
                    try:
                        comicinfo_xml = generate_comicinfo_xml(metadata, part_number=part_num + 1)
                        zf.writestr("ComicInfo.xml", comicinfo_xml)
                        logger.info(f"ComicInfo.xml added for: {part_name}")
                    except Exception as e:
                        logger.warning(f"Could not generate ComicInfo.xml: {e}")

                for src_path, arc_name in final_images:
                    zf.write(src_path, arc_name)

            part_size = sum(p.stat().st_size for p, _ in part_images) / (1024 * 1024)
            logger.info(f"Created part {part_num + 1}/{num_parts}: {clean_cbz_path.name} ({len(final_images)} images, ~{part_size:.1f}MB)")
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
            # 7z puede leer RAR
            result = subprocess.run(
                ['7z', 't', str(file_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info(f"RAR archive verified: {file_path.name}")
                return True
            else:
                logger.error(f"RAR integrity check failed: {file_path.name}")
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

    def convert_with_kcc(self, input_file: Path) -> bool:
        # Recargar configuración antes de cada conversión
        load_kcc_config()

        cmd = [
            'kcc-c2e',
            str(input_file),
            '-p', KCC_PROFILE,
            '-f', KCC_FORMAT,
            '-o', str(OUTPUT_DIR),
            '--jpeg-quality', KCC_QUALITY,
            '-m',
            '-q',
            '--forcecolor'
        ]

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