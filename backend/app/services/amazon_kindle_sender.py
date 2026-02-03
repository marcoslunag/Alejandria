"""
Amazon Send to Kindle Service
Uses Playwright to automate sending files to Kindle via Amazon's web service
Supports large files (up to 200MB) that can't be sent via email
"""

import asyncio
import logging
import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Storage for cookies/session
COOKIES_FILE = Path("/app/data/amazon_cookies.json")


class AmazonKindleSender:
    """
    Sends files to Kindle using Amazon's "Send to Kindle" web service
    Uses Playwright for browser automation
    """

    SEND_TO_KINDLE_URL = "https://www.amazon.com/sendtokindle"
    AMAZON_LOGIN_URL = "https://www.amazon.com/ap/signin"
    MAX_FILE_SIZE_MB = 200  # Amazon's limit for Send to Kindle

    def __init__(self, amazon_email: str, amazon_password: str):
        """
        Initialize Amazon Kindle sender

        Args:
            amazon_email: Amazon account email
            amazon_password: Amazon account password
        """
        self.amazon_email = amazon_email
        self.amazon_password = amazon_password
        self.browser = None
        self.context = None
        self.page = None

    async def _init_browser(self):
        """Initialize Playwright browser"""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )

        # Load cookies if available
        cookies = self._load_cookies()

        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        if cookies:
            await self.context.add_cookies(cookies)
            logger.info("Loaded existing Amazon cookies")

        self.page = await self.context.new_page()

    async def _close_browser(self):
        """Close browser and cleanup"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    def _save_cookies(self, cookies: list):
        """Save cookies to file for future sessions"""
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f)
        logger.info("Saved Amazon cookies")

    def _load_cookies(self) -> Optional[list]:
        """Load cookies from file"""
        if COOKIES_FILE.exists():
            try:
                with open(COOKIES_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cookies: {e}")
        return None

    async def _is_logged_in(self) -> bool:
        """Check if we're logged into Amazon"""
        try:
            await self.page.goto(self.SEND_TO_KINDLE_URL, wait_until='networkidle', timeout=30000)

            # Check if we're on the login page or the Send to Kindle page
            current_url = self.page.url

            if 'signin' in current_url or 'ap/signin' in current_url:
                return False

            # Check for Send to Kindle elements
            try:
                await self.page.wait_for_selector('input[type="file"]', timeout=5000)
                return True
            except:
                return False

        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return False

    async def _login(self) -> bool:
        """
        Login to Amazon account

        Returns:
            True if login successful
        """
        try:
            logger.info("Logging into Amazon...")

            await self.page.goto(self.AMAZON_LOGIN_URL, wait_until='networkidle', timeout=30000)

            # Enter email
            email_input = await self.page.wait_for_selector('#ap_email', timeout=10000)
            await email_input.fill(self.amazon_email)

            # Click continue (some Amazon pages have this step)
            continue_btn = await self.page.query_selector('#continue')
            if continue_btn:
                await continue_btn.click()
                await self.page.wait_for_load_state('networkidle')

            # Enter password
            password_input = await self.page.wait_for_selector('#ap_password', timeout=10000)
            await password_input.fill(self.amazon_password)

            # Click sign in
            signin_btn = await self.page.wait_for_selector('#signInSubmit', timeout=5000)
            await signin_btn.click()

            # Wait for navigation
            await self.page.wait_for_load_state('networkidle', timeout=30000)

            # Check for 2FA or CAPTCHA
            current_url = self.page.url

            if 'ap/cvf' in current_url or 'ap/mfa' in current_url:
                logger.error("Amazon requires 2FA verification. Please login manually first.")
                return False

            if 'ap/signin' in current_url:
                # Check for error message
                error_msg = await self.page.query_selector('#auth-error-message-box')
                if error_msg:
                    error_text = await error_msg.inner_text()
                    logger.error(f"Amazon login failed: {error_text}")
                    return False

            # Save cookies for future sessions
            cookies = await self.context.cookies()
            self._save_cookies(cookies)

            logger.info("Successfully logged into Amazon")
            return True

        except Exception as e:
            logger.error(f"Amazon login error: {e}")
            return False

    async def send_to_kindle(
        self,
        file_path: Path,
        device_name: Optional[str] = None
    ) -> bool:
        """
        Send file to Kindle using Amazon's Send to Kindle service

        Args:
            file_path: Path to EPUB/MOBI file
            device_name: Specific Kindle device name (optional, sends to all if not specified)

        Returns:
            True if sent successfully
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return False

        # Check file size
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.MAX_FILE_SIZE_MB:
            logger.error(f"File too large for Amazon Send to Kindle: {file_size_mb:.0f}MB (max {self.MAX_FILE_SIZE_MB}MB)")
            return False

        try:
            await self._init_browser()

            # Check if logged in, login if needed
            if not await self._is_logged_in():
                if not await self._login():
                    logger.error("Failed to login to Amazon")
                    return False

                # Navigate to Send to Kindle after login
                await self.page.goto(self.SEND_TO_KINDLE_URL, wait_until='networkidle', timeout=30000)

            logger.info(f"Uploading {file_path.name} ({file_size_mb:.0f}MB) to Send to Kindle...")

            # Find the file input
            file_input = await self.page.wait_for_selector('input[type="file"]', timeout=10000)

            # Upload file
            await file_input.set_input_files(str(file_path))

            # Wait for upload to complete (this can take a while for large files)
            await self.page.wait_for_timeout(2000)

            # Look for the send/deliver button
            # Amazon's UI may vary, try different selectors
            send_selectors = [
                'button:has-text("Send")',
                'button:has-text("Deliver")',
                'input[type="submit"][value*="Send"]',
                '#send-button',
                '.send-button'
            ]

            send_btn = None
            for selector in send_selectors:
                try:
                    send_btn = await self.page.wait_for_selector(selector, timeout=5000)
                    if send_btn:
                        break
                except:
                    continue

            if not send_btn:
                logger.error("Could not find Send button on Amazon page")
                # Take screenshot for debugging
                await self.page.screenshot(path='/app/data/amazon_debug.png')
                return False

            # Select specific device if specified
            if device_name:
                try:
                    device_selector = await self.page.query_selector(f'text="{device_name}"')
                    if device_selector:
                        await device_selector.click()
                except:
                    logger.warning(f"Could not select device: {device_name}, sending to all devices")

            # Click send
            await send_btn.click()

            # Wait for confirmation
            await self.page.wait_for_timeout(3000)

            # Check for success message
            success_indicators = [
                'text="successfully"',
                'text="sent"',
                'text="delivered"',
                '.success-message'
            ]

            for indicator in success_indicators:
                try:
                    element = await self.page.query_selector(indicator)
                    if element:
                        logger.info(f"Successfully sent {file_path.name} to Kindle!")
                        return True
                except:
                    continue

            # If no clear success indicator, assume success if no error
            logger.info(f"File {file_path.name} appears to have been sent to Kindle")
            return True

        except Exception as e:
            logger.error(f"Error sending to Kindle: {e}")
            return False

        finally:
            await self._close_browser()

    async def test_connection(self) -> dict:
        """
        Test Amazon connection and authentication

        Returns:
            dict with status and message
        """
        try:
            await self._init_browser()

            if await self._is_logged_in():
                return {
                    'success': True,
                    'message': 'Connected to Amazon (using saved session)'
                }

            if await self._login():
                return {
                    'success': True,
                    'message': 'Successfully logged into Amazon'
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to login to Amazon. Check credentials or verify no 2FA is required.'
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Connection error: {str(e)}'
            }

        finally:
            await self._close_browser()

    async def get_kindle_devices(self) -> List[str]:
        """
        Get list of registered Kindle devices

        Returns:
            List of device names
        """
        devices = []
        try:
            await self._init_browser()

            if not await self._is_logged_in():
                if not await self._login():
                    return devices

                await self.page.goto(self.SEND_TO_KINDLE_URL, wait_until='networkidle')

            # Look for device list
            device_elements = await self.page.query_selector_all('.device-name, .kindle-device')

            for element in device_elements:
                name = await element.inner_text()
                if name:
                    devices.append(name.strip())

        except Exception as e:
            logger.error(f"Error getting Kindle devices: {e}")

        finally:
            await self._close_browser()

        return devices


# Synchronous wrapper for use in scheduler
def send_to_kindle_sync(
    amazon_email: str,
    amazon_password: str,
    file_path: Path,
    device_name: Optional[str] = None
) -> bool:
    """
    Synchronous wrapper for send_to_kindle

    Args:
        amazon_email: Amazon account email
        amazon_password: Amazon account password
        file_path: Path to file
        device_name: Optional specific device

    Returns:
        True if successful
    """
    sender = AmazonKindleSender(amazon_email, amazon_password)
    return asyncio.run(sender.send_to_kindle(file_path, device_name))
