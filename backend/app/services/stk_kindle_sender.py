"""
STKClient Kindle Sender Service
Uses stkclient library for Amazon's Send to Kindle API

Cada usuario tiene su sesión STK aislada en /stk-data/stk_{user_id}.json
(STK_DATA_DIR env, volumen Docker para persistir entre reinicios).

═══════════════════════════════════════════════════════════════════════
MODELO DE SESIÓN (verificado leyendo la fuente de stkclient):
═══════════════════════════════════════════════════════════════════════
- `Client.dumps()` persiste SOLO `device_info` = {adp_token, device_private_key (RSA), ...}.
  NO persiste ningún access token ni refresh token.
- El access token OAuth2 se usa UNA SOLA VEZ: token_exchange() → register_device_with_token()
  → devuelve el adp_token + RSA key, y luego se descarta el access token.
- Todas las llamadas posteriores (get_owned_devices, send_file) se firman EN VIVO con
  RSA key + adp_token (signer.digest_header_for_request).

CONCLUSIÓN CRÍTICA:
- El `adp_token` es una credencial de DISPOSITIVO de LARGA DURACIÓN que NO expira por
  calendario. No hay "token que renovar": la sesión ES el archivo JSON.
- Por tanto, la sesión SÓLO muere si NUESTRO código borra ese archivo → `logout()`,
  disparado por `_record_failure()` tras MAX_CONSECUTIVE_FAILURES fallos "definitivos".

BUG QUE PROVOCABA "la sesión muere cada día" (ya corregido):
1. `deviceinfotoken` (un 403 TRANSITORIO de Amazon: rate-limit, mantenimiento) estaba en
   la lista de señales de expiración DEFINITIVA → se contaban como "token revocado".
2. El health-check del scheduler (cada 8h) llamaba get_devices(), que alimenta
   _record_failure(); Amazon un poco justo → acumulación silenciosa → logout() → el usuario
   tenía que volver a meter Amazon. El mecanismo pensado para mantener viva la sesión
   era el que la eliminaba.

DISEÑO CORREGIDO (objetivo del usuario: meter Amazon UNA vez y no volver a meterlo
nuevamente salvo logout manual):
- El auto-logout es prácticamente imposible: umbral alto (20 fallos) y solo señales de
  revocación REAL del dispositivo. Los 403 transitorios NUNCA cuentan.
- `heartbeat()` (para el scheduler) NUNCA borra la sesión: solo verifica y persiste.
- La única forma de resetear es el botón "Desconectar" (logout manual).
- Si Amazon revoca el dispositivo de verdad (p. ej. el usuario borra la app en Amazon),
  los envíos fallan con un mensaje claro y el usuario pulsa logout y reconecta.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
import stkclient

logger = logging.getLogger(__name__)

# Fallos DEFINITIVOS consecutivos (fuera de burst) antes de considerar que la sesión
# requiere re-auth. Valor alto a propósito: la credencial larga (adp_token) no expira,
# así que solo un problema REAL y persistido (Amazon revocó el dispositivo) debería
# llegar aquí. En la práctica el usuario hará logout manual antes.
MAX_CONSECUTIVE_FAILURES = 20

# Ventana en segundos: fallos dentro de esta ventana = mismo burst = 1 solo fallo de
# operación. Protege contra enviar N EPUBs en bucle con Amazon un poco justo.
BURST_WINDOW_SECONDS = 120

# Palabras clave que Amazon devuelve cuando el dispositivo/ADP token está DEFINITIVAMENTE
# revocado. 'deviceinfotoken' fue RETIRADO: es un 403 transitorio (rate-limit,
# mantenimiento) y contarlo como definitivo era la causa principal de la muerte diaria.
# '403' y 'forbidden' NO están aquí: demasiado genéricos (rate limit, etc.).
_DEFINITIVE_EXPIRY_SIGNALS = [
    'device not registered',   # dispositivo eliminado de la cuenta Amazon
    'invalid adp token',
    'adp_token is invalid',
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
    Sends files to Kindle using stkclient (Amazon's Send to Kindle API).
    Usa credencial de larga duración (adp_token + RSA) — no hay token que expire.
    Cada instancia está vinculada a un user_id concreto.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.client: Optional[stkclient.Client] = None
        self.oauth: Optional[stkclient.OAuth2] = None
        self._consecutive_failures: int = 0        # operaciones fallidas (no ficheros individuales)
        self._last_definitive_failure_at: float = 0.0  # timestamp del último fallo de operación
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
        """Persist the (long-lived) credential to disk. No-op práctico si no cambió,
        pero garantiza que el adp_token + RSA estén en disco tras cada auth/llamada."""
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
        logger.info(f"STK authorization completed for user {self.user_id}")
        return True

    def _is_definitive_expiry(self, error_message: str) -> bool:
        """
        Retorna True SOLO cuando Amazon confirma que el dispositivo/ADP token está
        revocado. Los 403 transitorios (rate limit, caída) NO cuentan — no deben
        borrar la sesión.
        """
        error_str = str(error_message).lower()
        return any(signal in error_str for signal in _DEFINITIVE_EXPIRY_SIGNALS)

    def _is_temporary_error(self, error_message: str) -> bool:
        """Errores transitorios que no indican token expirado."""
        error_str = str(error_message).lower()
        return any(s in error_str for s in [
            'timeout', 'connection', 'network', 'temporarily',
            'retry', 'service unavailable', '503', '502', '429', '403', 'forbidden',
        ])

    def _record_failure(self, error_message: str) -> bool:
        """
        Registra un fallo y decide si la sesión debe borrarse.
        Retorna True si la sesión debe eliminarse (fallo definitivo confirmado
        tras MAX_CONSECUTIVE_FAILURES operaciones fallidas, fuera de burst).

        BURST DETECTION: múltiples fallos dentro de BURST_WINDOW_SECONDS (ej: 9 EPUBs
        enviados en bucle, todos fallando) cuentan como UNA sola operación fallida,
        no como N fallos independientes.
        """
        if self._is_definitive_expiry(error_message):
            now = time.time()
            time_since_last = now - self._last_definitive_failure_at

            if time_since_last < BURST_WINDOW_SECONDS:
                logger.warning(
                    f"STK fallo definitivo (burst, {time_since_last:.0f}s desde anterior) "
                    f"para user {self.user_id} — sesión intacta: {error_message}"
                )
            else:
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

    def heartbeat(self) -> bool:
        """
        Heartbeat de verificación: llama a get_owned_devices() para confirmar que la
        sesión sigue viva y persistir la credencial al disco.

        NO DESTRUCTIVO: NUNCA borra la sesión ni acumula fallos hacia logout(). Solo
        loguea y resetea el contador si todo va bien. Pensado para el scheduler:
        detecta (con log) si Amazon está fallando sin riesgo de destruir la credencial
        persistente que no expira.

        Retorna True si la sesión responde.
        """
        if not self.client:
            return False
        try:
            self.client.get_owned_devices()
            self._save_client()
            self._reset_failure_count()
            return True
        except Exception as e:
            # Loguear SIN destruir: la credencial larga no expira por calendario.
            logger.warning(
                f"STK heartbeat fallo para user {self.user_id} (transitorio, sesión intacta): {e}"
            )
            return False

    def ensure_healthy(self) -> bool:
        """Backward-compat: ahora no-destruible. Delega en heartbeat()."""
        return self.heartbeat()

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
            # Éxito: persistir la credencial y resetear contador
            self._save_client()
            self._reset_failure_count()
            return result
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to get Kindle devices for user {self.user_id}: {error_msg}")
            # Solo borra si es un fallo definitivo confirmado múltiples veces (umbral alto)
            if self._record_failure(error_msg):
                self.logout()
            return []

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
            self._save_client()
            self._reset_failure_count()
            return {'success': True, 'message': f'Sent to {len(device_serials)} device(s)'}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send to Kindle for user {self.user_id}: {error_msg}")

            if self._record_failure(error_msg):
                self.logout()
                return {'success': False, 'message': 'STK sesión revocada por Amazon. Reconecta en Ajustes → Amazon Send to Kindle.'}

            # Error temporal o no clasificado: informar sin borrar sesión
            return {'success': False, 'message': str(e)}

    def logout(self):
        """Logout MANUAL (botón Desconectar). Borra la credencial persistida."""
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
