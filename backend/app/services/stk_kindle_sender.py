"""
STKClient Kindle Sender Service
Uses stkclient library for Amazon's Send to Kindle API
Supports OAuth2 authentication and large files (>10MB)
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import stkclient

logger = logging.getLogger(__name__)

# Storage for serialized client
CLIENT_FILE = Path("/app/data/stk_client.json")


class STKKindleSender:
    """
    Sends files to Kindle using stkclient (Amazon's Send to Kindle API)
    Uses OAuth2 authentication - user authorizes once via browser
    """

    def __init__(self):
        self.client: Optional[stkclient.Client] = None
        self.oauth: Optional[stkclient.OAuth2] = None
        self._load_client()

    def _load_client(self) -> bool:
        """Load saved client from file"""
        if CLIENT_FILE.exists():
            try:
                with open(CLIENT_FILE, 'r') as f:
                    data = f.read()
                self.client = stkclient.Client.loads(data)
                logger.info("Loaded existing STK client session")
                return True
            except Exception as e:
                logger.warning(f"Failed to load STK client: {e}")
                CLIENT_FILE.unlink(missing_ok=True)
        return False

    def _save_client(self):
        """Save client to file for future sessions"""
        if self.client:
            CLIENT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CLIENT_FILE, 'w') as f:
                f.write(self.client.dumps())
            logger.info("Saved STK client session")

    def is_authenticated(self) -> bool:
        """Check if we have a valid authenticated client"""
        return self.client is not None

    def get_signin_url(self) -> str:
        """
        Get the Amazon OAuth2 sign-in URL
        User must open this URL in browser and authorize

        Returns:
            Sign-in URL to open in browser
        """
        self.oauth = stkclient.OAuth2()
        url = self.oauth.get_signin_url()
        logger.info(f"Generated STK sign-in URL")
        return url

    def complete_authorization(self, redirect_url: str) -> bool:
        """
        Complete OAuth2 authorization with the redirect URL

        Args:
            redirect_url: The URL from the browser after authorization

        Returns:
            True if authorization successful
        """
        if not self.oauth:
            self.oauth = stkclient.OAuth2()

        try:
            self.client = self.oauth.create_client(redirect_url)
            self._save_client()
            logger.info("STK authorization completed successfully")
            return True
        except Exception as e:
            logger.error(f"STK authorization failed: {e}")
            return False

    def get_devices(self) -> List[Dict[str, Any]]:
        """
        Get list of Kindle devices

        Returns:
            List of device info dicts
        """
        if not self.client:
            return []

        try:
            devices_response = self.client.get_owned_devices()

            # Handle both formats: list directly or object with owned_devices attribute
            if isinstance(devices_response, list):
                devices = devices_response
            elif hasattr(devices_response, 'owned_devices'):
                devices = devices_response.owned_devices
            else:
                logger.warning(f"Unexpected devices response type: {type(devices_response)}")
                return []

            result = []
            for d in devices:
                result.append({
                    'serial': d.device_serial_number,
                    'name': getattr(d, 'device_name', 'Kindle'),
                    'type': getattr(d, 'device_type', 'Unknown')
                })
            return result
        except Exception as e:
            logger.error(f"Failed to get Kindle devices: {e}")
            return []

    def send_file(
        self,
        file_path: Path,
        title: Optional[str] = None,
        author: Optional[str] = None,
        device_serials: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send file to Kindle

        Args:
            file_path: Path to EPUB/MOBI file
            title: Book title (optional, extracted from filename if not provided)
            author: Author name (optional)
            device_serials: List of device serial numbers (sends to all if not specified)

        Returns:
            Dict with success status and message
        """
        if not self.client:
            return {
                'success': False,
                'message': 'Not authenticated. Please authorize first.'
            }

        if not file_path.exists():
            return {
                'success': False,
                'message': f'File not found: {file_path}'
            }

        try:
            # Get devices if not specified
            if not device_serials:
                devices_response = self.client.get_owned_devices()
                # Handle both formats: list directly or object with owned_devices attribute
                if isinstance(devices_response, list):
                    devices = devices_response
                elif hasattr(devices_response, 'owned_devices'):
                    devices = devices_response.owned_devices
                else:
                    return {
                        'success': False,
                        'message': f'Unexpected devices response format: {type(devices_response)}'
                    }
                device_serials = [d.device_serial_number for d in devices]

            if not device_serials:
                return {
                    'success': False,
                    'message': 'No Kindle devices found'
                }

            # Extract title from filename if not provided
            if not title:
                title = file_path.stem

            # Send file
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            logger.info(f"Sending {file_path.name} ({file_size_mb:.0f}MB) to {len(device_serials)} device(s)")

            # Determine format from file extension
            file_ext = file_path.suffix.lower()
            if file_ext == '.epub':
                file_format = 'EPUB'
            elif file_ext in ['.mobi', '.azw', '.azw3']:
                file_format = 'MOBI'
            else:
                file_format = 'EPUB'  # Default to EPUB

            self.client.send_file(
                file_path,
                device_serials,
                author=author or "Unknown",
                title=title,
                format=file_format
            )

            logger.info(f"Successfully sent {file_path.name} to Kindle")
            return {
                'success': True,
                'message': f'Sent to {len(device_serials)} device(s)'
            }

        except Exception as e:
            logger.error(f"Failed to send to Kindle: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    def logout(self):
        """Clear saved session"""
        self.client = None
        CLIENT_FILE.unlink(missing_ok=True)
        logger.info("STK session cleared")


# Global instance
_sender: Optional[STKKindleSender] = None


def get_stk_sender() -> STKKindleSender:
    """Get or create the global STK sender instance"""
    global _sender
    if _sender is None:
        _sender = STKKindleSender()
    return _sender
