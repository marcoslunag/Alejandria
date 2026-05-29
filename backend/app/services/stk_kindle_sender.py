"""
STKClient Kindle Sender Service
Uses stkclient library for Amazon's Send to Kindle API
Supports OAuth2 authentication and large files (>10MB)

Each user has their own isolated STK session stored at /stk-data/stk_{user_id}.json
(STK_DATA_DIR env var, mounted como volumen Docker para persistir entre reinicios)

DISEÑO DE SESIÓN PERSISTENTE:
- El token ADP + RSA key son credenciales de dispositivo de larga duración (no expiran
  como un access token OAuth2 estándar de 1h). Amazon los mantiene válidos mientras el
  "dispositivo" siga activo.
- Bug anterior: _is_token_expired_error usaba '403' genérico → cualquier error temporal
  de Amazon (rate limit, corte momentáneo) borraba la sesión permanentemente.
- Fix: solo errores específicos y confirmados de Amazon indican token revocado.
  Los errores temporales se logean pero NO borran la sesión.
- Protección adicional: MAX_CONSECUTIVE_FAILURES=3 — la sesión solo se elimina tras
  3 fallos confirmados consecutivos, no al primero.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
import stkclient

logger = logging.getLogger(__name__)

# Número de operaciones de envío fallidas (no ficheros individuales) antes de borrar sesión.
# Con burst detection, 9 ficheros fallando en el mismo envío = 1 fallo de operación, no 9.
MAX_CONSECUTIVE_FAILURES = 5

# Ventana en segundos: fallos dentro de esta ventana = mismo burst = 1 solo fallo de operación.
# Protege contra el caso de enviar N EPUBs en bucle: si todos fallan en <120s, cuenta como 1.
BURST_WINDOW_SECONDS = 120

# Intervalo mínimo entre refrescos proactivos del token (segundos). 6h = 21600s.
TOKEN_REFRESH_INTERVAL = 6 * 3600

# Palabras clave que Amazon devuelve cuando el ADP token está DEFINITIVAMENTE revocado.
# '403' y 'forbidden' NO están aquí porque son demasiado genéricos (rate limit, etc.)
# NOTA: 'deviceinfotoken' puede ser transitorio (rate-limit, mantenimiento) — ahora
# protegido por burst detection para no borrar la sesión por un único envío fallido.
_DEFINITIVE_EXPIRY_SIGNALS = [
    'deviceinfotoken',       # ADP token inválido o transitoriamente rechazado
    'device not registered', # Dispositivo eliminado de la cuenta Amazon
    'invalid adp token',
    'adp_token is invalid',
    'device_registration',
    'customer not found',
]

def _init_data_dir() -> Path:
    primary = Path(os.environ.get("STK_DATA_DIR", "/app/data"))
    try:
        primary.mkdir(parents=True, exist_ok=True)
        test_file = primary / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return primary
    except (PermissionError, OSError):
        fallback = Path("/tmp/stk_data")
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning(f"Cannot write to {primary}, using fallback {fallback}")
        return fallback

DATA_DIR = _init_data_dir()


def _client_file(user_id: int) -> Path:
    return DATA_DIR / f"stk_{user_id}.json"


class STKKindleSender:
    """
    Sends files to Kindle using stkclient (Amazon's Send to Kindle API)
    Uses OAuth2 authentication - user authorizes once via browser.
    Each instance is bound to a specific user_id.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.client: Optional[stkclient.Client] = None
        self.oauth: Optional[stkclient.OAuth2] = None
        self._consecutive_failures: int = 0      # operaciones fallidas (no ficheros individuales)
        self._last_definitive_failure_at: float = 0.0  # timestamp del último fallo de operación
        self._last_token_refresh_at: float = 0.0       # timestamp del último refresco proactivo
        self._load_client()

    def _load_client(self) -> bool:
        """Load saved client from file"""
        f = _client_file(self.user_id)
        if f.exists():
            try:
                self.client = stkclient.Client.loads(f.read_text())
                logger.info(f"Loaded existing STK session for user {self.user_id}")
                return True
            except Exception as e:
                logger.warning(f"Failed to load STK client for user {self.user_id}: {e}")
                f.unlink(missing_ok=True)
        return False

    def _save_client(self):
        """Save client to file for future sessions"""
        if self.client:
            try:
                f = _client_file(self.user_id)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(self.client.dumps())
                logger.info(f"Saved STK session for user {self.user_id}")
            except Exception as e:
                logger.error(f"Failed to persist STK session for user {self.user_id}: {e}")

    def is_authenticated(self) -> bool:
        return self.client is not None

    def get_signin_url(self) -> str:
        self.oauth = stkclient.OAuth2()
        url = self.oauth.get_signin_url()
        logger.info(f"Generated STK sign-in URL for user {self.user_id}")
        return url

    def complete_authorization(self, redirect_url: str) -> bool:
        if not self.oauth:
            self.oauth = stkclient.OAuth2()

        try:
            self.client = self.oauth.create_client(redirect_url)
        except Exception as e:
            logger.error(f"STK authorization failed for user {self.user_id}: {e}")
            return False

        self._save_client()
        self._consecutive_failures = 0
        self._last_definitive_failure_at = 0.0
        self._last_token_refresh_at = time.time()  # recién logueado = token fresco
        logger.info(f"STK authorization completed for user {self.user_id}")
        return True

    def _is_definitive_expiry(self, error_message: str) -> bool:
        """
        Retorna True SOLO cuando Amazon confirma definitivamente que el token
        está revocado/inválido. Los errores 403 genéricos (rate limit, caída
        temporal) NO cuentan — son transitorios y NO deben borrar la sesión.
        """
        error_str = str(error_message).lower()
        return any(signal in error_str for signal in _DEFINITIVE_EXPIRY_SIGNALS)

    def _is_temporary_error(self, error_message: str) -> bool:
        """Errores transitorios que no indican token expirado."""
        error_str = str(error_message).lower()
        return any(s in error_str for s in [
            'timeout', 'connection', 'network', 'temporarily',
            'retry', 'service unavailable', '503', '502', '429',
        ])

    def _record_failure(self, error_message: str) -> bool:
        """
        Registra un fallo y decide si la sesión debe borrarse.
        Retorna True si la sesión debe eliminarse (fallo definitivo confirmado).

        BURST DETECTION: múltiples fallos dentro de BURST_WINDOW_SECONDS (ej: 9 EPUBs
        enviados en bucle, todos fallando) cuentan como UNA sola operación fallida,
        no como N fallos independientes. Esto evita que un único envío múltiple
        borre la sesión aunque Amazon devuelva 403 transitorios en cada fichero.
        """
        if self._is_definitive_expiry(error_message):
            now = time.time()
            time_since_last = now - self._last_definitive_failure_at

            if time_since_last < BURST_WINDOW_SECONDS:
                # Mismo burst (misma operación de envío) — no incrementar el contador
                logger.warning(
                    f"STK fallo definitivo (burst, {time_since_last:.0f}s desde anterior) "
                    f"para user {self.user_id} — sesión intacta: {error_message}"
                )
            else:
                # Nueva operación fallida (fuera de burst) — incrementar
                self._consecutive_failures += 1
                self._last_definitive_failure_at = now
                logger.warning(
                    f"STK fallo definitivo #{self._consecutive_failures}/{MAX_CONSECUTIVE_FAILURES} "
                    f"para user {self.user_id}: {error_message}"
                )

                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error(
                        f"STK sesión usuario {self.user_id} revocada tras "
                        f"{MAX_CONSECUTIVE_FAILURES} operaciones fallidas — requiere re-auth"
                    )
                    return True

        elif self._is_temporary_error(error_message):
            logger.warning(f"STK error temporal (no borra sesión) user {self.user_id}: {error_message}")
        else:
            # 403 genérico, forbidden, u otro error desconocido: loguear, NO borrar
            logger.warning(
                f"STK error no clasificado (no borra sesión) user {self.user_id}: {error_message}. "
                f"Si persiste, revisar manualmente."
            )
        return False

    def _reset_failure_count(self):
        """Resetea el contador de fallos tras una operación exitosa."""
        if self._consecutive_failures > 0:
            logger.info(f"STK user {self.user_id}: operación exitosa, reseteando contador de fallos.")
        self._consecutive_failures = 0
        self._last_definitive_failure_at = 0.0

    def get_devices(self) -> List[Dict[str, Any]]:
        if not self.client:
            return []

        try:
            devices_response = self.client.get_owned_devices()

            if isinstance(devices_response, list):
                devices = devices_response
            elif hasattr(devices_response, 'owned_devices'):
                devices = devices_response.owned_devices
            else:
                logger.warning(f"Unexpected devices response type: {type(devices_response)}")
                return []

            result = [
                {
                    'serial': d.device_serial_number,
                    'name': getattr(d, 'device_name', 'Kindle'),
                    'type': getattr(d, 'device_type', 'Unknown')
                }
                for d in devices
            ]
            # Éxito: persistir cualquier token auto-refrescado y resetear contador
            self._save_client()
            self._reset_failure_count()
            return result
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to get Kindle devices for user {self.user_id}: {error_msg}")
            # Solo borra la sesión si es un fallo definitivo confirmado múltiples veces
            if self._record_failure(error_msg):
                self.logout()
            return []

    def ensure_healthy(self) -> bool:
        """
        Verifica salud de la sesión y persiste tokens auto-refrescados al disco.
        Retorna True si la sesión está activa.

        NOTA: Los errores temporales (403 de rate-limit, caída de red) NO borran
        la sesión — solo los fallos definitivos confirmados tras MAX_CONSECUTIVE_FAILURES.
        """
        if not self.client:
            return False
        devices = self.get_devices()
        if self.client:  # client puede haberse borrado si _record_failure() decidió logout
            logger.info(f"STK session healthy for user {self.user_id} ({len(devices)} devices)")
            return True
        logger.warning(f"STK session unhealthy for user {self.user_id} — needs re-auth")
        return False

    def _proactive_refresh(self):
        """
        Refresca proactivamente el token de sesión llamando a get_owned_devices().
        El cliente stkclient renueva el access token internamente; _save_client()
        persiste los tokens refrescados al disco.
        Solo actúa si han pasado más de TOKEN_REFRESH_INTERVAL segundos desde el
        último refresco (evita llamadas extra en envíos múltiples del mismo batch).
        """
        if not self.client:
            return
        now = time.time()
        if now - self._last_token_refresh_at < TOKEN_REFRESH_INTERVAL:
            return
        try:
            self.client.get_owned_devices()
            self._save_client()
            self._last_token_refresh_at = now
            logger.debug(f"STK token refreshed proactively for user {self.user_id}")
        except Exception as e:
            logger.warning(f"STK proactive refresh failed for user {self.user_id}: {e} — proceeding anyway")

    def send_file(
        self,
        file_path: Path,
        title: Optional[str] = None,
        author: Optional[str] = None,
        device_serials: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        if not self.client:
            return {'success': False, 'message': 'Not authenticated. Please authorize first.'}

        if not file_path.exists():
            return {'success': False, 'message': f'File not found: {file_path}'}

        # Refresco proactivo: si el token tiene >6h sin refrescarse, llamamos a
        # get_owned_devices() primero para que stkclient renueve el access token.
        # Así evitamos los 403 "deviceinfotoken" por token de sesión caducado.
        self._proactive_refresh()

        try:
            if not device_serials:
                devices_response = self.client.get_owned_devices()
                if isinstance(devices_response, list):
                    devices = devices_response
                elif hasattr(devices_response, 'owned_devices'):
                    devices = devices_response.owned_devices
                else:
                    return {'success': False, 'message': f'Unexpected devices response: {type(devices_response)}'}
                device_serials = [d.device_serial_number for d in devices]

            if not device_serials:
                return {'success': False, 'message': 'No Kindle devices found'}

            if not title:
                title = file_path.stem

            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            logger.info(f"Sending {file_path.name} ({file_size_mb:.0f}MB) to {len(device_serials)} device(s) for user {self.user_id}")

            file_ext = file_path.suffix.lower()
            file_format = 'EPUB' if file_ext == '.epub' else ('MOBI' if file_ext in ['.mobi', '.azw', '.azw3'] else 'EPUB')

            self.client.send_file(
                file_path,
                device_serials,
                author=author or "Unknown",
                title=title,
                format=file_format
            )

            logger.info(f"Successfully sent {file_path.name} to Kindle for user {self.user_id}")
            # Persist any auto-refreshed tokens back to disk
            self._save_client()
            return {'success': True, 'message': f'Sent to {len(device_serials)} device(s)'}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send to Kindle for user {self.user_id}: {error_msg}")

            if self._record_failure(error_msg):
                self.logout()
                return {'success': False, 'message': 'STK session definitivamente revocada. Re-autentícate en Ajustes.'}

            # Error temporal o no clasificado: informar sin borrar sesión
            return {'success': False, 'message': str(e)}

    def logout(self):
        self.client = None
        _client_file(self.user_id).unlink(missing_ok=True)
        logger.info(f"STK session cleared for user {self.user_id}")


# Per-user registry: user_id → STKKindleSender
_senders: Dict[int, STKKindleSender] = {}


def get_stk_sender(user_id: int) -> STKKindleSender:
    """Get or create an STK sender instance for the given user"""
    if user_id not in _senders:
        _senders[user_id] = STKKindleSender(user_id)
    return _senders[user_id]


def remove_stk_sender(user_id: int) -> None:
    """Remove cached sender (call after logout so next access reloads fresh)"""
    _senders.pop(user_id, None)
