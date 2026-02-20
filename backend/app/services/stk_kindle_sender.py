"""
STKClient Kindle Sender Service
Uses stkclient library for Amazon's Send to Kindle API
Supports OAuth2 authentication and large files (>10MB)

Each user has their own isolated STK session stored at /app/data/stk_{user_id}.json
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import stkclient

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


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
        logger.info(f"STK authorization completed for user {self.user_id}")
        return True

    def _is_token_expired_error(self, error_message: str) -> bool:
        error_str = str(error_message).lower()
        return 'deviceinfotoken' in error_str or '403' in error_str or 'forbidden' in error_str

    def _handle_expired_token(self) -> None:
        logger.warning(f"STK token expired for user {self.user_id} - clearing session")
        self.logout()

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

            return [
                {
                    'serial': d.device_serial_number,
                    'name': getattr(d, 'device_name', 'Kindle'),
                    'type': getattr(d, 'device_type', 'Unknown')
                }
                for d in devices
            ]
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to get Kindle devices for user {self.user_id}: {error_msg}")
            if self._is_token_expired_error(error_msg):
                self._handle_expired_token()
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
            return {'success': True, 'message': f'Sent to {len(device_serials)} device(s)'}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send to Kindle for user {self.user_id}: {error_msg}")

            if self._is_token_expired_error(error_msg):
                self._handle_expired_token()
                return {'success': False, 'message': 'STK session expired. Please re-authenticate in Settings.'}

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
