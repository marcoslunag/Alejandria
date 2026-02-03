"""
ComicInfo.xml Generator
Genera metadatos en formato ComicRack para KCC
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Optional, List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ComicInfoGenerator:
    """
    Genera archivos ComicInfo.xml para insertar en CBZ
    KCC puede leer estos metadatos con --metadatatitle 1
    """

    def generate(
        self,
        series: str,
        volume: Optional[int] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        writer: Optional[str] = None,
        penciller: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[int] = None,
        month: Optional[int] = None,
        day: Optional[int] = None,
        language: str = "es",
        manga: str = "Yes",
        page_count: Optional[int] = None,
        web: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        age_rating: Optional[str] = None,
        country: Optional[str] = None,
    ) -> str:
        """
        Genera XML de ComicInfo

        Args:
            series: Nombre de la serie (obligatorio)
            volume: Numero de volumen
            title: Titulo del volumen
            summary: Descripcion/sinopsis
            writer: Autor/guionista
            penciller: Artista/dibujante
            genre: Generos separados por coma
            year: Ano de publicacion
            month: Mes de publicacion
            day: Dia de publicacion
            language: Codigo ISO de idioma (es, en, jp)
            manga: "Yes" para formato manga (derecha a izquierda)
            page_count: Numero de paginas
            web: URL de referencia
            notes: Notas adicionales
            tags: Lista de tags
            age_rating: Clasificacion de edad

        Returns:
            String XML formateado
        """
        root = ET.Element("ComicInfo")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")

        # Campos obligatorios
        self._add_element(root, "Series", series)

        # Campos opcionales
        if volume is not None:
            self._add_element(root, "Volume", str(volume))
            self._add_element(root, "Number", str(volume))

        if title:
            self._add_element(root, "Title", title)

        if summary:
            # Limpiar summary de caracteres problematicos
            summary_clean = summary.replace('\r\n', '\n').replace('\r', '\n')
            self._add_element(root, "Summary", summary_clean)

        if writer:
            self._add_element(root, "Writer", writer)

        if penciller:
            self._add_element(root, "Penciller", penciller)
            self._add_element(root, "Inker", penciller)  # En manga suele ser el mismo

        if genre:
            self._add_element(root, "Genre", genre)

        if year:
            self._add_element(root, "Year", str(year))

        if month:
            self._add_element(root, "Month", str(month))

        if day:
            self._add_element(root, "Day", str(day))

        if language:
            self._add_element(root, "LanguageISO", language)

        if manga:
            self._add_element(root, "Manga", manga)

        if page_count:
            self._add_element(root, "PageCount", str(page_count))

        if web:
            self._add_element(root, "Web", web)

        if notes:
            self._add_element(root, "Notes", notes)

        if tags:
            self._add_element(root, "Tags", ", ".join(tags))

        if age_rating:
            self._add_element(root, "AgeRating", age_rating)

        if country:
            # Mapear codigo de pais a nombre
            country_names = {
                'JP': 'Japon',
                'KR': 'Corea del Sur',
                'CN': 'China',
                'TW': 'Taiwan',
            }
            self._add_element(root, "Publisher", country_names.get(country, country))

        # Formato de lectura para manga
        self._add_element(root, "BlackAndWhite", "Yes")

        # Convertir a string formateado
        xml_str = ET.tostring(root, encoding='unicode')
        # Formatear con minidom para legibilidad
        dom = minidom.parseString(xml_str)
        return dom.toprettyxml(indent="  ", encoding=None)

    def _add_element(self, parent: ET.Element, name: str, value: str):
        """Anade elemento al XML si el valor no esta vacio"""
        if value:
            elem = ET.SubElement(parent, name)
            elem.text = str(value)

    def generate_from_manga(self, manga_data: Dict, volume_number: int) -> str:
        """
        Genera ComicInfo.xml desde datos de manga de la BD

        Args:
            manga_data: Diccionario con datos del manga
            volume_number: Numero de volumen

        Returns:
            String XML
        """
        # Extraer autores/artistas
        writer = None
        penciller = None

        if manga_data.get('authors'):
            writer = ", ".join(manga_data['authors'][:3])  # Max 3 autores

        if manga_data.get('artists'):
            penciller = ", ".join(manga_data['artists'][:3])
        elif writer:
            penciller = writer  # En manga suele ser el mismo

        # Extraer generos
        genre = None
        if manga_data.get('genres'):
            genre = ", ".join(manga_data['genres'][:5])  # Max 5 generos

        # Extraer ano de la fecha
        year = None
        month = None
        day = None
        if manga_data.get('start_date'):
            try:
                date_str = manga_data['start_date']
                if len(date_str) >= 4:
                    year = int(date_str[:4])
                if len(date_str) >= 7:
                    month = int(date_str[5:7])
                if len(date_str) >= 10:
                    day = int(date_str[8:10])
            except (ValueError, IndexError):
                pass

        # Determinar clasificacion de edad
        age_rating = None
        if manga_data.get('is_adult'):
            age_rating = "Adults Only 18+"
        elif manga_data.get('genres'):
            genres_lower = [g.lower() for g in manga_data['genres']]
            if any(g in genres_lower for g in ['ecchi', 'gore', 'violencia']):
                age_rating = "Mature 17+"

        # Notas
        notes = f"Importado de AniList. Score: {manga_data.get('average_score', 'N/A')}/100"

        return self.generate(
            series=manga_data.get('title', 'Unknown'),
            volume=volume_number,
            title=f"Tomo {volume_number}",
            summary=manga_data.get('description'),
            writer=writer,
            penciller=penciller,
            genre=genre,
            year=year,
            month=month,
            day=day,
            language="es",
            manga="Yes",
            web=manga_data.get('anilist_url'),
            notes=notes,
            tags=manga_data.get('tags', [])[:10],
            age_rating=age_rating,
            country=manga_data.get('country'),
        )


# Instancia global
_generator = ComicInfoGenerator()


def generate_comicinfo_xml(manga_data: Dict, volume_number: int) -> str:
    """
    Funcion de conveniencia para generar ComicInfo.xml

    Args:
        manga_data: Datos del manga desde la BD
        volume_number: Numero de volumen

    Returns:
        String XML formateado
    """
    return _generator.generate_from_manga(manga_data, volume_number)
