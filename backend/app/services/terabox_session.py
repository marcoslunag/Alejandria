"""
TeraBox Session Manager
Gestiona autenticación persistente para TeraBox usando Playwright
Basado en la arquitectura recomendada para bypass de protecciones anti-bot
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Directorio para estado de autenticación persistente
AUTH_STATE_DIR = Path(os.getenv('TERABOX_AUTH_DIR', '/downloads/.terabox_auth'))


class TeraBoxSessionManager:
    """
    Gestor de sesiones de TeraBox con autenticación persistente.

    Funcionalidades:
    - Persistencia de estado de sesión entre ejecuciones
    - Detección proactiva de expiración de sesión
    - Notificación cuando se requiere re-autenticación manual
    """

    # Cookies críticas que indican sesión válida
    REQUIRED_COOKIES = ['ndus']  # Cookie principal de sesión
    OPTIONAL_COOKIES = ['ndut_fmt', 'browserid', 'csrfToken']

    # Tiempo máximo estimado de validez de sesión (horas)
    SESSION_VALIDITY_HOURS = 72  # TeraBox típicamente 24-72 horas

    def __init__(self, auth_state_path: Path = None):
        """
        Inicializa el gestor de sesiones.

        Args:
            auth_state_path: Path al archivo de estado de autenticación
        """
        AUTH_STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.auth_state_path = auth_state_path or (AUTH_STATE_DIR / 'terabox_session.json')
        self._session_info: Optional[Dict] = None
        self._load_session_info()

    def _load_session_info(self):
        """Carga información de sesión si existe."""
        info_path = self.auth_state_path.with_suffix('.info.json')
        if info_path.exists():
            try:
                with open(info_path, 'r') as f:
                    self._session_info = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load session info: {e}")
                self._session_info = None

    def _save_session_info(self, info: Dict):
        """Guarda información de sesión."""
        info_path = self.auth_state_path.with_suffix('.info.json')
        try:
            with open(info_path, 'w') as f:
                json.dump(info, f, indent=2, default=str)
            self._session_info = info
        except Exception as e:
            logger.error(f"Could not save session info: {e}")

    def has_valid_session(self) -> bool:
        """
        Verifica si existe una sesión que parece válida.

        Returns:
            True si existe sesión con cookies requeridas no expiradas
        """
        if not self.auth_state_path.exists():
            logger.info("No auth state file found")
            return False

        try:
            with open(self.auth_state_path, 'r') as f:
                state = json.load(f)

            cookies = state.get('cookies', [])

            # Verificar cookies requeridas
            found_cookies = {}
            for cookie in cookies:
                name = cookie.get('name', '')
                if name in self.REQUIRED_COOKIES:
                    found_cookies[name] = cookie

            if not all(c in found_cookies for c in self.REQUIRED_COOKIES):
                missing = [c for c in self.REQUIRED_COOKIES if c not in found_cookies]
                logger.warning(f"Missing required cookies: {missing}")
                return False

            # Verificar expiración de cookie ndus
            ndus_cookie = found_cookies.get('ndus')
            if ndus_cookie:
                expires = ndus_cookie.get('expires')
                if expires:
                    # expires es timestamp en segundos
                    expiry_time = datetime.fromtimestamp(expires)
                    now = datetime.now()

                    if expiry_time <= now:
                        logger.warning(f"Session cookie 'ndus' expired at {expiry_time}")
                        return False

                    # Advertir si está próxima a expirar (menos de 4 horas)
                    time_left = expiry_time - now
                    if time_left < timedelta(hours=4):
                        logger.warning(f"Session expiring soon: {time_left} remaining")

            logger.info("Valid session found")
            return True

        except Exception as e:
            logger.error(f"Error checking session validity: {e}")
            return False

    def get_session_status(self) -> Dict:
        """
        Obtiene estado detallado de la sesión.

        Returns:
            Dict con información de estado de sesión
        """
        status = {
            'has_auth_file': self.auth_state_path.exists(),
            'is_valid': False,
            'cookies_found': [],
            'cookies_missing': self.REQUIRED_COOKIES.copy(),
            'expires_at': None,
            'time_remaining': None,
            'last_login': None,
            'needs_reauth': True
        }

        if not status['has_auth_file']:
            return status

        try:
            with open(self.auth_state_path, 'r') as f:
                state = json.load(f)

            cookies = state.get('cookies', [])

            for cookie in cookies:
                name = cookie.get('name', '')
                if name in self.REQUIRED_COOKIES or name in self.OPTIONAL_COOKIES:
                    status['cookies_found'].append(name)
                    if name in status['cookies_missing']:
                        status['cookies_missing'].remove(name)

                    if name == 'ndus' and cookie.get('expires'):
                        expiry = datetime.fromtimestamp(cookie['expires'])
                        status['expires_at'] = expiry.isoformat()
                        remaining = expiry - datetime.now()
                        status['time_remaining'] = str(remaining)

            status['is_valid'] = len(status['cookies_missing']) == 0
            status['needs_reauth'] = not status['is_valid']

            # Info de última autenticación
            if self._session_info:
                status['last_login'] = self._session_info.get('login_time')

        except Exception as e:
            logger.error(f"Error getting session status: {e}")
            status['error'] = str(e)

        return status

    def get_auth_state_path(self) -> Path:
        """Retorna path al archivo de estado de autenticación."""
        return self.auth_state_path

    def save_auth_state(self, storage_state: Dict, source: str = "manual"):
        """
        Guarda estado de autenticación desde Playwright.

        Args:
            storage_state: Estado retornado por context.storage_state()
            source: Origen de la autenticación (manual, refresh, etc.)
        """
        try:
            # Guardar estado de autenticación
            with open(self.auth_state_path, 'w') as f:
                json.dump(storage_state, f, indent=2)

            # Guardar metadata
            self._save_session_info({
                'login_time': datetime.now().isoformat(),
                'source': source,
                'cookies_count': len(storage_state.get('cookies', [])),
            })

            # Permisos restrictivos
            os.chmod(self.auth_state_path, 0o600)

            logger.info(f"Auth state saved: {self.auth_state_path}")

        except Exception as e:
            logger.error(f"Error saving auth state: {e}")
            raise

    def invalidate_session(self):
        """Invalida la sesión actual (marca como expirada)."""
        if self.auth_state_path.exists():
            try:
                # Renombrar a .invalid para preservar pero marcar como inválido
                invalid_path = self.auth_state_path.with_suffix('.invalid.json')
                self.auth_state_path.rename(invalid_path)
                logger.info(f"Session invalidated: {invalid_path}")
            except Exception as e:
                logger.error(f"Error invalidating session: {e}")

    def get_cookie_string(self) -> Optional[str]:
        """
        Obtiene las cookies en formato string para uso con requests.

        Returns:
            String de cookies formato "name1=value1; name2=value2" o None
        """
        if not self.auth_state_path.exists():
            return None

        try:
            with open(self.auth_state_path, 'r') as f:
                state = json.load(f)

            cookies = state.get('cookies', [])
            cookie_parts = []

            for cookie in cookies:
                name = cookie.get('name')
                value = cookie.get('value')
                if name and value:
                    cookie_parts.append(f"{name}={value}")

            return "; ".join(cookie_parts) if cookie_parts else None

        except Exception as e:
            logger.error(f"Error getting cookie string: {e}")
            return None


# Singleton instance
_session_manager: Optional[TeraBoxSessionManager] = None


def get_session_manager() -> TeraBoxSessionManager:
    """Obtiene instancia singleton del gestor de sesiones."""
    global _session_manager
    if _session_manager is None:
        _session_manager = TeraBoxSessionManager()
    return _session_manager
