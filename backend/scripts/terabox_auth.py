#!/usr/bin/env python3
"""
TeraBox Authentication Script
Script interactivo para autenticación inicial en TeraBox.
Este script abre un navegador visible donde el usuario puede hacer login manualmente.
Una vez autenticado, guarda el estado de sesión para uso posterior automatizado.
"""

import asyncio
import sys
import os

# Agregar el directorio del backend al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    """
    Proceso de autenticación manual para TeraBox.
    Abre un navegador visible y espera a que el usuario complete el login.
    """
    print("=" * 60)
    print("TERABOX - Autenticación Manual")
    print("=" * 60)
    print()
    print("Este script abrirá un navegador donde debes hacer login en TeraBox.")
    print("Una vez que estés logueado, presiona ENTER en esta terminal.")
    print()
    print("Importante:")
    print("  - Usa una cuenta de TeraBox válida")
    print("  - Completa cualquier verificación (CAPTCHA, 2FA, etc.)")
    print("  - Espera a que la página principal de TeraBox cargue")
    print("  - Luego vuelve a esta terminal y presiona ENTER")
    print()

    input("Presiona ENTER para abrir el navegador...")

    # Importar session manager
    try:
        from app.services.terabox_session import get_session_manager
        session_manager = get_session_manager()
    except ImportError:
        # Crear manualmente si no está disponible
        auth_dir = Path('/downloads/.terabox_auth')
        auth_dir.mkdir(parents=True, exist_ok=True)
        auth_state_path = auth_dir / 'terabox_session.json'

    async with async_playwright() as p:
        # Lanzar navegador en modo visible
        browser = await p.chromium.launch(
            headless=False,  # Modo visible
            args=[
                '--disable-blink-features=AutomationControlled',
                '--window-size=1280,800',
            ]
        )

        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            locale='en-US',
        )

        page = await context.new_page()

        # Navegar a TeraBox
        print()
        print("Navegando a TeraBox...")
        await page.goto('https://www.terabox.com/', wait_until='domcontentloaded')

        print()
        print("=" * 60)
        print("NAVEGADOR ABIERTO")
        print("=" * 60)
        print()
        print("1. Haz clic en 'Log in' o 'Sign in' en TeraBox")
        print("2. Ingresa tus credenciales y completa el login")
        print("3. Espera a que cargue la página principal de tu cuenta")
        print("4. Vuelve a esta terminal cuando estés logueado")
        print()

        input("Presiona ENTER cuando hayas completado el login...")

        # Verificar que el usuario está logueado
        print()
        print("Verificando sesión...")

        # Verificar indicadores de sesión
        try:
            # Esperar un momento para que la página se estabilice
            await asyncio.sleep(2)

            # Buscar indicadores de login
            cookies = await context.cookies()
            ndus_cookie = next((c for c in cookies if c['name'] == 'ndus'), None)

            if ndus_cookie:
                print(f"✅ Cookie 'ndus' encontrada (expira: {ndus_cookie.get('expires', 'N/A')})")
            else:
                print("⚠️  Cookie 'ndus' no encontrada - puede que el login no sea completo")

            # Guardar estado de sesión
            storage_state = await context.storage_state()

            try:
                session_manager.save_auth_state(storage_state, source="manual_login")
                auth_path = session_manager.get_auth_state_path()
                print(f"✅ Estado de sesión guardado en: {auth_path}")
            except:
                # Guardar manualmente si el session manager no está disponible
                import json
                auth_path = Path('/downloads/.terabox_auth/terabox_session.json')
                auth_path.parent.mkdir(parents=True, exist_ok=True)
                with open(auth_path, 'w') as f:
                    json.dump(storage_state, f, indent=2)
                print(f"✅ Estado de sesión guardado en: {auth_path}")

            # Mostrar resumen de cookies
            print()
            print("Cookies capturadas:")
            important_cookies = ['ndus', 'ndut_fmt', 'browserid', 'csrfToken', 'lang']
            for cookie in cookies:
                if cookie['name'] in important_cookies:
                    print(f"  - {cookie['name']}: {cookie['value'][:20]}...")

            print()
            print("=" * 60)
            print("✅ AUTENTICACIÓN COMPLETADA")
            print("=" * 60)
            print()
            print("El servicio de TeraBox ahora puede usar esta sesión para")
            print("descargar archivos automáticamente.")
            print()
            print("Nota: La sesión típicamente dura 24-72 horas.")
            print("Deberás repetir este proceso cuando expire.")
            print()

        except Exception as e:
            print(f"❌ Error durante la verificación: {e}")
            print()
            print("Puedes intentar continuar de todos modos.")

        await browser.close()

    print("Navegador cerrado. Proceso completado.")


if __name__ == '__main__':
    asyncio.run(main())
