"""
Host Manager - Sistema de ranking y gestión de hosts de descarga
Prioriza hosts que no requieren login y son más fiables
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)


class HostPriority(IntEnum):
    """Prioridad de hosts (menor = mejor)"""
    EXCELLENT = 1   # Sin login, descarga directa, muy fiable
    GOOD = 2        # Sin login, puede requerir espera
    MEDIUM = 3      # Sin login pero con limitaciones
    LOW = 4         # Requiere resolver captcha o espera larga
    REQUIRES_AUTH = 5  # Requiere login/cuenta
    BLOCKED = 10    # No funciona / bloqueado


@dataclass
class HostConfig:
    """Configuración de un host de descarga"""
    name: str
    priority: HostPriority
    requires_login: bool
    supports_direct_download: bool
    max_file_size_mb: Optional[int] = None
    wait_time_seconds: int = 0
    notes: str = ""


# Configuración de hosts conocidos
HOST_CONFIGS: Dict[str, HostConfig] = {
    # === EXCELENTES (sin login, descarga directa) ===
    'mediafire': HostConfig(
        name='MediaFire',
        priority=HostPriority.EXCELLENT,
        requires_login=False,
        supports_direct_download=True,
        notes="Muy fiable, sin límites significativos"
    ),
    'fireload': HostConfig(
        name='Fireload',
        priority=HostPriority.EXCELLENT,
        requires_login=False,
        supports_direct_download=True,
        notes="Sin login requerido"
    ),
    '1fichier': HostConfig(
        name='1fichier',
        priority=HostPriority.GOOD,
        requires_login=False,
        supports_direct_download=True,
        wait_time_seconds=30,
        notes="Puede requerir espera entre descargas"
    ),

    # === BUENOS (sin login, algunas limitaciones) ===
    'mega': HostConfig(
        name='MEGA',
        priority=HostPriority.GOOD,
        requires_login=False,
        supports_direct_download=True,
        max_file_size_mb=5000,
        notes="Límite de transferencia diaria sin cuenta"
    ),
    'google_drive': HostConfig(
        name='Google Drive',
        priority=HostPriority.GOOD,
        requires_login=False,
        supports_direct_download=True,
        notes="Archivos grandes pueden requerir confirmación"
    ),
    'dropbox': HostConfig(
        name='Dropbox',
        priority=HostPriority.GOOD,
        requires_login=False,
        supports_direct_download=True,
        notes="Links públicos funcionan sin login"
    ),

    # === MEDIO (limitaciones notables) ===
    'uptobox': HostConfig(
        name='Uptobox',
        priority=HostPriority.MEDIUM,
        requires_login=False,
        supports_direct_download=False,
        wait_time_seconds=60,
        notes="Espera de 60s para usuarios free"
    ),
    'zippyshare': HostConfig(
        name='Zippyshare',
        priority=HostPriority.BLOCKED,  # Ya no existe
        requires_login=False,
        supports_direct_download=False,
        notes="Servicio cerrado"
    ),

    # === REQUIEREN AUTENTICACIÓN ===
    'terabox': HostConfig(
        name='TeraBox',
        priority=HostPriority.REQUIRES_AUTH,
        requires_login=True,
        supports_direct_download=False,
        notes="Requiere login para descargar - usar bypass como fallback"
    ),
    'uploaded': HostConfig(
        name='Uploaded',
        priority=HostPriority.REQUIRES_AUTH,
        requires_login=True,
        supports_direct_download=False,
        notes="Requiere cuenta premium"
    ),

    # === ACORTADORES (resolver primero) ===
    'ouo': HostConfig(
        name='OUO.io',
        priority=HostPriority.LOW,
        requires_login=False,
        supports_direct_download=False,
        wait_time_seconds=10,
        notes="Acortador - redirige a otro host"
    ),
    'shrinkme': HostConfig(
        name='ShrinkMe',
        priority=HostPriority.LOW,
        requires_login=False,
        supports_direct_download=False,
        notes="Acortador - redirige a otro host"
    ),
}


def identify_host(url: str) -> Optional[str]:
    """
    Identifica el host de una URL

    Args:
        url: URL a identificar

    Returns:
        Nombre del host o None
    """
    url_lower = url.lower()

    host_patterns = {
        'mediafire': ['mediafire.com'],
        'fireload': ['fireload.com'],
        '1fichier': ['1fichier.com'],
        'mega': ['mega.nz', 'mega.co.nz'],
        'google_drive': ['drive.google.com', 'docs.google.com'],
        'dropbox': ['dropbox.com'],
        'uptobox': ['uptobox.com'],
        'terabox': ['terabox.com', 'terabox.app', '1024terabox.com'],
        'uploaded': ['uploaded.net', 'uploaded.to'],
        'ouo': ['ouo.io', 'ouo.press'],
        'shrinkme': ['shrinkme.io'],
        'zippyshare': ['zippyshare.com'],
    }

    for host_id, patterns in host_patterns.items():
        if any(pattern in url_lower for pattern in patterns):
            return host_id

    return None


def get_host_config(host_id: str) -> Optional[HostConfig]:
    """Obtiene la configuración de un host"""
    return HOST_CONFIGS.get(host_id)


def get_host_priority(url: str) -> int:
    """
    Obtiene la prioridad de una URL basándose en su host

    Args:
        url: URL a evaluar

    Returns:
        Valor de prioridad (menor = mejor)
    """
    host_id = identify_host(url)
    if host_id:
        config = HOST_CONFIGS.get(host_id)
        if config:
            return config.priority

    # Host desconocido - prioridad media
    return HostPriority.MEDIUM


def sort_download_links(links: List[Dict]) -> List[Dict]:
    """
    Ordena una lista de enlaces de descarga por prioridad

    Args:
        links: Lista de dicts con 'url' y opcionalmente 'host'

    Returns:
        Lista ordenada por prioridad (mejor primero)
    """
    def get_priority(link: Dict) -> int:
        url = link.get('url', '')
        return get_host_priority(url)

    return sorted(links, key=get_priority)


def select_best_links(links: List[Dict], max_links: int = 2) -> List[Dict]:
    """
    Selecciona los mejores enlaces de descarga

    Args:
        links: Lista de enlaces disponibles
        max_links: Número máximo de enlaces a devolver

    Returns:
        Lista con los mejores enlaces (principal + backups)
    """
    if not links:
        return []

    # Ordenar por prioridad
    sorted_links = sort_download_links(links)

    # Filtrar hosts bloqueados
    valid_links = [
        link for link in sorted_links
        if get_host_priority(link.get('url', '')) < HostPriority.BLOCKED
    ]

    if not valid_links:
        # Si todos están bloqueados, devolver los originales
        return sorted_links[:max_links]

    # Seleccionar los mejores
    selected = []
    seen_hosts = set()

    for link in valid_links:
        host_id = identify_host(link.get('url', ''))

        # Evitar duplicados del mismo host
        if host_id in seen_hosts:
            continue

        selected.append(link)
        seen_hosts.add(host_id)

        if len(selected) >= max_links:
            break

    return selected


def get_download_strategy(url: str) -> Dict:
    """
    Obtiene la estrategia de descarga para una URL

    Args:
        url: URL de descarga

    Returns:
        Dict con información de estrategia
    """
    host_id = identify_host(url)
    config = get_host_config(host_id) if host_id else None

    strategy = {
        'host_id': host_id or 'unknown',
        'host_name': config.name if config else 'Desconocido',
        'requires_login': config.requires_login if config else False,
        'supports_direct': config.supports_direct_download if config else True,
        'wait_time': config.wait_time_seconds if config else 0,
        'priority': config.priority if config else HostPriority.MEDIUM,
        'use_playwright': host_id in ['fireload', 'mediafire', '1fichier', 'mega'],
        'use_bypass': host_id == 'terabox',
    }

    return strategy


# Logging para debug
def log_host_ranking(links: List[Dict]):
    """Log del ranking de hosts para debug"""
    if not links:
        logger.debug("No links to rank")
        return

    logger.info("=== Host Ranking ===")
    for i, link in enumerate(sort_download_links(links)):
        url = link.get('url', '')[:50]
        host_id = identify_host(link.get('url', ''))
        priority = get_host_priority(link.get('url', ''))
        logger.info(f"  {i+1}. [{priority}] {host_id}: {url}...")
