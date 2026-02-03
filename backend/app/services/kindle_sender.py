"""
Kindle Sender Service
Sends EPUB/MOBI files to Kindle via email
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class KindleSender:
    """
    Envía archivos EPUB/MOBI al Kindle vía email
    También puede usar Calibre-Web API si está disponible
    """

    # Límite de tamaño de Amazon para archivos adjuntos
    MAX_FILE_SIZE_MB = 50

    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_email: str
    ):
        """
        Initialize Kindle sender

        Args:
            smtp_server: SMTP server address
            smtp_port: SMTP server port
            smtp_user: SMTP username
            smtp_password: SMTP password
            from_email: From email address (must be whitelisted in Kindle)
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email

    def send_to_kindle(
        self,
        file_path: Path,
        kindle_email: str,
        subject: Optional[str] = None,
        body: Optional[str] = None
    ) -> bool:
        """
        Envía archivo EPUB/MOBI al Kindle por email

        Args:
            file_path: Path al archivo EPUB/MOBI
            kindle_email: Email del Kindle (xxx@kindle.com)
            subject: Asunto del email (opcional)
            body: Cuerpo del email (opcional)

        Returns:
            True si se envió correctamente
        """
        try:
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return False

            # Verificar extensión
            if file_path.suffix.lower() not in ['.epub', '.mobi', '.azw', '.pdf']:
                logger.error(f"Unsupported file format: {file_path.suffix}")
                return False

            # Verificar tamaño
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self.MAX_FILE_SIZE_MB:
                logger.error(f"File too large: {file_size_mb:.2f}MB (max {self.MAX_FILE_SIZE_MB}MB)")
                return False

            logger.info(f"Sending {file_path.name} ({file_size_mb:.2f}MB) to {kindle_email}")

            # Crear mensaje
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = kindle_email
            msg['Subject'] = subject or f"Manga: {file_path.stem}"

            # Añadir cuerpo del mensaje
            if body:
                msg.attach(MIMEText(body, 'plain'))
            else:
                msg.attach(MIMEText(f"Manga file: {file_path.name}", 'plain'))

            # Adjuntar archivo
            with open(file_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())

            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={file_path.name}'
            )
            msg.attach(part)

            # Enviar email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Successfully sent {file_path.name} to {kindle_email}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed. Check credentials.")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending to Kindle: {e}")
            return False

    def send_batch(
        self,
        file_paths: List[Path],
        kindle_email: str,
        send_individually: bool = True
    ) -> dict:
        """
        Envía múltiples archivos al Kindle

        Args:
            file_paths: Lista de paths a los archivos
            kindle_email: Email del Kindle
            send_individually: Si True, envía cada archivo en un email separado

        Returns:
            Dict con resultados: {'success': [], 'failed': []}
        """
        results = {
            'success': [],
            'failed': []
        }

        if send_individually:
            # Enviar cada archivo en un email separado
            for file_path in file_paths:
                success = self.send_to_kindle(file_path, kindle_email)
                if success:
                    results['success'].append(str(file_path))
                else:
                    results['failed'].append(str(file_path))
        else:
            # Enviar múltiples archivos en un solo email
            # TODO: Implementar envío múltiple (verificar límite de tamaño total)
            logger.warning("Batch send in single email not implemented yet")
            for file_path in file_paths:
                success = self.send_to_kindle(file_path, kindle_email)
                if success:
                    results['success'].append(str(file_path))
                else:
                    results['failed'].append(str(file_path))

        logger.info(f"Batch send completed: {len(results['success'])} success, {len(results['failed'])} failed")
        return results

    def test_connection(self) -> bool:
        """
        Prueba la conexión SMTP

        Returns:
            True si la conexión es exitosa
        """
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                logger.info("SMTP connection test successful")
                return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False

    def validate_kindle_email(self, email: str) -> bool:
        """
        Valida formato de email de Kindle

        Args:
            email: Email to validate

        Returns:
            True if valid Kindle email format
        """
        import re

        # Formato básico de email
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        if not re.match(email_pattern, email):
            return False

        # Verificar que sea un email de Kindle válido
        valid_domains = ['kindle.com', 'free.kindle.com']

        email_lower = email.lower()
        return any(email_lower.endswith(f'@{domain}') for domain in valid_domains)

    def get_max_file_size_mb(self) -> int:
        """
        Obtiene el tamaño máximo permitido para archivos

        Returns:
            Maximum file size in MB
        """
        return self.MAX_FILE_SIZE_MB


class CalibreWebSender:
    """
    Alternative sender using Calibre-Web API
    Can be used instead of or in addition to email sending
    """

    def __init__(self, calibre_web_url: str, api_key: Optional[str] = None):
        """
        Initialize Calibre-Web sender

        Args:
            calibre_web_url: Calibre-Web instance URL
            api_key: API key if authentication is required
        """
        self.base_url = calibre_web_url.rstrip('/')
        self.api_key = api_key

    def upload_to_library(self, file_path: Path, metadata: dict = None) -> bool:
        """
        Upload file to Calibre-Web library

        Args:
            file_path: Path to file
            metadata: Book metadata (title, author, etc)

        Returns:
            True if successful
        """
        # TODO: Implement Calibre-Web API integration
        logger.warning("Calibre-Web integration not implemented yet")
        return False

    def send_to_device(self, book_id: int, device_id: str) -> bool:
        """
        Send book from Calibre-Web to device

        Args:
            book_id: Book ID in Calibre library
            device_id: Device ID

        Returns:
            True if successful
        """
        # TODO: Implement device sending via Calibre-Web
        logger.warning("Calibre-Web device sending not implemented yet")
        return False
