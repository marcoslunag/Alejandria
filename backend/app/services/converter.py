"""
KCC (Kindle Comic Converter) Service
Converts CBZ/CBR/ZIP files to Kindle-optimized EPUB/MOBI
"""

import subprocess
from pathlib import Path
from typing import Optional, List
import logging
import shutil

logger = logging.getLogger(__name__)


class KCCConverter:
    """
    Conversor usando Kindle Comic Converter (KCC)
    Convierte CBZ/CBR a EPUB optimizado para Kindle
    """

    # Perfiles de dispositivos Kindle disponibles
    PROFILES = {
        'KPW5': 'Kindle Paperwhite 5 (2021)',
        'KPW4': 'Kindle Paperwhite 4 (2018)',
        'KPW3': 'Kindle Paperwhite 3 (2015)',
        'KO': 'Kindle Oasis',
        'KV': 'Kindle Voyage',
        'K11': 'Kindle 11',
        'KHD': 'Kindle (High DPI)',
        'K': 'Kindle (Standard)'
    }

    def __init__(self, output_dir: str = "/manga/kindle"):
        """
        Initialize KCC converter

        Args:
            output_dir: Directory for converted files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Check if kcc-c2e is available
        self.kcc_available = self._check_kcc_installation()

    def _check_kcc_installation(self) -> bool:
        """
        Check if KCC is installed and available

        Returns:
            bool: True if KCC is available
        """
        try:
            result = subprocess.run(
                ['kcc-c2e', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"KCC found: {result.stdout.strip()}")
                return True
            else:
                logger.warning("KCC not found or not working properly")
                return False
        except FileNotFoundError:
            logger.error("kcc-c2e command not found. Install KCC first.")
            return False
        except Exception as e:
            logger.error(f"Error checking KCC installation: {e}")
            return False

    def convert_to_kindle(
        self,
        input_file: Path,
        profile: str = "KPW5",
        format: str = "EPUB",
        manga_style: bool = True,
        quality: int = 95
    ) -> Optional[Path]:
        """
        Convierte CBZ/CBR a formato Kindle

        Args:
            input_file: Path al archivo CBZ/CBR
            profile: Perfil de dispositivo Kindle (default: KPW5)
            format: Formato de salida (EPUB, MOBI, CBZ)
            manga_style: Optimizar para lectura manga (derecha a izquierda)
            quality: Calidad de compresión de imágenes (0-100)

        Returns:
            Path al archivo convertido o None si falla
        """
        if not self.kcc_available:
            logger.error("KCC is not available. Cannot convert.")
            return None

        if not input_file.exists():
            logger.error(f"Input file not found: {input_file}")
            return None

        try:
            output_file = self.output_dir / f"{input_file.stem}.{format.lower()}"

            logger.info(f"Converting {input_file.name} to {format} for {profile}")

            # Construir comando KCC
            cmd = [
                'kcc-c2e',
                str(input_file),
                '-p', profile,
                '-f', format,
                '-o', str(self.output_dir),
                '-q', str(quality)
            ]

            # Opciones adicionales
            if manga_style:
                cmd.append('-m')  # Manga mode (right-to-left)

            # Opciones recomendadas
            cmd.extend([
                '--forcecolor',  # Forzar modo color
                '--stretch',  # Ajustar imágenes al tamaño de pantalla
            ])

            # Ejecutar KCC
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutos max
            )

            if result.returncode != 0:
                logger.error(f"KCC error: {result.stderr}")
                return None

            # Verificar que el archivo se creó
            # KCC puede crear el archivo con nombre diferente
            possible_outputs = list(self.output_dir.glob(f"{input_file.stem}*.{format.lower()}"))

            if possible_outputs:
                actual_output = possible_outputs[0]
                logger.info(f"Converted successfully: {actual_output.name}")
                return actual_output
            else:
                logger.error(f"Conversion completed but output file not found")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"KCC timeout for {input_file}")
            return None
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            return None

    def batch_convert(
        self,
        input_dir: Path,
        profile: str = "KPW5",
        format: str = "EPUB"
    ) -> List[Path]:
        """
        Convierte todos los CBZ/CBR de un directorio

        Args:
            input_dir: Directory with CBZ/CBR files
            profile: Kindle device profile
            format: Output format

        Returns:
            List of converted file paths
        """
        if not input_dir.exists():
            logger.error(f"Input directory not found: {input_dir}")
            return []

        converted = []
        supported_formats = ['*.cbz', '*.cbr', '*.zip']

        for pattern in supported_formats:
            for file in input_dir.glob(pattern):
                logger.info(f"Processing: {file.name}")
                result = self.convert_to_kindle(file, profile, format)
                if result:
                    converted.append(result)

        logger.info(f"Batch conversion completed: {len(converted)} files")
        return converted

    def cleanup_source_files(self, input_file: Path, keep_backup: bool = False):
        """
        Limpia archivos fuente después de la conversión

        Args:
            input_file: Source file to cleanup
            keep_backup: Keep a backup instead of deleting
        """
        try:
            if not input_file.exists():
                return

            if keep_backup:
                backup_dir = input_file.parent / 'backup'
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / input_file.name
                shutil.move(str(input_file), str(backup_path))
                logger.info(f"Backed up: {input_file.name}")
            else:
                input_file.unlink()
                logger.info(f"Deleted: {input_file.name}")

        except Exception as e:
            logger.error(f"Error cleaning up {input_file}: {e}")

    def get_supported_profiles(self) -> dict:
        """
        Get list of supported Kindle device profiles

        Returns:
            Dict of profile codes and descriptions
        """
        return self.PROFILES.copy()

    def optimize_for_manga(
        self,
        input_file: Path,
        profile: str = "KPW5"
    ) -> Optional[Path]:
        """
        Optimiza específicamente para lectura de manga

        Args:
            input_file: Input CBZ/CBR file
            profile: Kindle device profile

        Returns:
            Path to optimized file or None
        """
        return self.convert_to_kindle(
            input_file=input_file,
            profile=profile,
            format="EPUB",
            manga_style=True,
            quality=95  # Alta calidad para manga
        )
