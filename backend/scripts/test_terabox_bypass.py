#!/usr/bin/env python3
"""
Script de prueba para bypass de TeraBox
Prueba múltiples métodos con las cookies proporcionadas
"""

import asyncio
import json
import logging
import os
import sys
import time
import re
import requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URL de prueba
TEST_URL = "https://www.terabox.com/spanish/sharing/link?surl=4LpF4n6kZZO8p8p7TO3w2Q"

# Cookies proporcionadas (formato export de navegador)
RAW_COOKIES = [
    {
        "name": "ndus",
        "value": "YfNzRr3teHuia6Q7URN2rVcurJn62FP9BRx0EuuD",
        "domain": ".terabox.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "expirationDate": 1801244131.682
    },
    {
        "name": "csrfToken",
        "value": "1KKyYQDCrpcJ9OhKv-VUmmfp",
        "domain": "www.terabox.com",
        "path": "/",
        "secure": False,
        "httpOnly": False
    },
    {
        "name": "PANWEB",
        "value": "1",
        "domain": ".terabox.com",
        "path": "/",
        "expirationDate": 1801159301.884
    },
    {
        "name": "browserid",
        "value": "5tO98R8t61oFUYdbRY6GDgUMAlaX13lEK0dEn_lCYIlKHf8acGLU5GTpJzk=",
        "domain": ".terabox.com",
        "path": "/",
        "expirationDate": 1774807303.174
    },
    {
        "name": "ndut_fmt",
        "value": "2B09EB1D66C1C6C01F429ACEF802114AFC07C1060DFA9769D652D75A6866AD02",
        "domain": "www.terabox.com",
        "path": "/",
        "expirationDate": 1772704072
    },
    {
        "name": "lang",
        "value": "es",
        "domain": ".terabox.com",
        "path": "/",
        "expirationDate": 1772704071.983
    },
    {
        "name": "TSID",
        "value": "iqnJ1oEhSdSQtaf2uMVvE9jn9Zm1VhKb",
        "domain": ".terabox.com",
        "path": "/",
        "expirationDate": 1801159303.525
    },
    {
        "name": "__bid_n",
        "value": "19c05c4b6483bd38d84207",
        "domain": ".terabox.com",
        "path": "/",
        "expirationDate": 1804672072.342
    },
    {
        "name": "ndut_fmv",
        "value": "bfac02e969efc325b0f7579efe0f1a9029b474a47c4df45006d835036427b4ecbc33cf3b20683159f38b92436e44c1e541ddbe69bcffa47e1078e61ee69e3b74042705838b38a13b6d333ce7cdd7e75637896b5dec0deb08c592a5b1ff910b8dca266230f544d2a80286651e09169452",
        "domain": "www.terabox.com",
        "path": "/"
    }
]


def get_cookie_string():
    """Convierte cookies a formato string para requests."""
    return "; ".join(f"{c['name']}={c['value']}" for c in RAW_COOKIES)


def extract_surl(url: str) -> str:
    """Extrae el surl de la URL."""
    # Formato ?surl=xxx
    if 'surl=' in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if 'surl' in params:
            return params['surl'][0]
    
    # Formato /s/1xxx
    match = re.search(r'/s/1?([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    return ""


class TeraBoxBypassTest:
    """Clase de prueba para diferentes métodos de bypass."""
    
    def __init__(self):
        self.session = requests.Session()
        self.cookie_string = get_cookie_string()
        
    def _setup_session(self):
        """Configura la sesión con headers realistas."""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'DNT': '1',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Cookie': self.cookie_string
        })
        
    def test_method_1_share_list(self, url: str) -> dict:
        """
        Método 1: API share/list directa
        """
        print("\n" + "="*60)
        print("MÉTODO 1: API share/list directa")
        print("="*60)
        
        self._setup_session()
        surl = extract_surl(url)
        
        if not surl:
            return {"error": "No se pudo extraer surl"}
            
        print(f"surl extraído: {surl}")
        
        # Primero visitar la página para obtener tokens
        page_url = f"https://www.terabox.com/sharing/link?surl={surl}"
        self.session.headers['Referer'] = page_url
        
        try:
            # Obtener la página primero
            print(f"Visitando página: {page_url}")
            page_resp = self.session.get(page_url, timeout=30, allow_redirects=True)
            print(f"Status página: {page_resp.status_code}")
            print(f"URL final: {page_resp.url}")
            
            # Extraer jsToken del HTML
            html = page_resp.text
            js_token = ""
            
            # Buscar jsToken en diferentes formatos
            patterns = [
                r'fn%28%22([^%]+)%22%29',  # URL encoded
                r'fn\("([^"]+)"\)',          # Normal
                r'"jsToken"\s*:\s*"([^"]+)"', # JSON
                r"jsToken['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", # Varios
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    js_token = match.group(1)
                    print(f"jsToken encontrado: {js_token[:30]}...")
                    break
            
            # Extraer bdstoken
            bdstoken_match = re.search(r'"bdstoken"\s*:\s*"([^"]+)"', html)
            bdstoken = bdstoken_match.group(1) if bdstoken_match else ""
            if bdstoken:
                print(f"bdstoken encontrado: {bdstoken[:20]}...")
            
            # Ahora llamar a la API
            api_url = "https://www.terabox.com/share/list"
            
            params = {
                'app_id': '250528',
                'web': '1',
                'channel': 'dubox',
                'clienttype': '0',
                'dp-logid': '',
                'page': '1',
                'num': '20',
                'by': 'name',
                'order': 'asc',
                'shorturl': surl,
                'root': '1'
            }
            
            if js_token:
                params['jsToken'] = js_token
                
            print(f"\nLlamando API: {api_url}")
            print(f"Params: {params}")
            
            response = self.session.get(api_url, params=params, timeout=30)
            print(f"Status API: {response.status_code}")
            
            try:
                data = response.json()
                print(f"Respuesta JSON: {json.dumps(data, indent=2)[:500]}...")
                
                if data.get('errno') == 0 and 'list' in data:
                    print("\n✅ ÉXITO! Archivos encontrados:")
                    for f in data['list'][:5]:
                        print(f"  - {f.get('server_filename')} ({f.get('size')} bytes)")
                        if f.get('dlink'):
                            print(f"    dlink: {f.get('dlink')[:80]}...")
                    return {"ok": True, "data": data}
                else:
                    print(f"\n❌ Error API: errno={data.get('errno')}, msg={data.get('errmsg')}")
                    return {"error": data.get('errmsg', 'Unknown error'), "errno": data.get('errno')}
                    
            except json.JSONDecodeError:
                print(f"Respuesta no es JSON: {response.text[:500]}")
                return {"error": "Respuesta no es JSON"}
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return {"error": str(e)}
            
    def test_method_2_share_wxlist(self, url: str) -> dict:
        """
        Método 2: API share/wxlist (alternativa)
        """
        print("\n" + "="*60)
        print("MÉTODO 2: API share/wxlist")
        print("="*60)
        
        self._setup_session()
        surl = extract_surl(url)
        
        api_url = "https://www.terabox.com/share/wxlist"
        
        params = {
            'app_id': '250528',
            'channel': 'dubox',
            'clienttype': '0',
            'web': '1',
            'shorturl': surl,
            'root': '1',
            'page': '1',
            'num': '20'
        }
        
        print(f"Llamando API: {api_url}")
        
        try:
            response = self.session.get(api_url, params=params, timeout=30)
            print(f"Status: {response.status_code}")
            
            data = response.json()
            print(f"Respuesta: {json.dumps(data, indent=2)[:500]}...")
            
            if data.get('errno') == 0:
                print("\n✅ ÉXITO!")
                return {"ok": True, "data": data}
            else:
                return {"error": data.get('errmsg'), "errno": data.get('errno')}
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return {"error": str(e)}
            
    def test_method_3_terabox_app_domain(self, url: str) -> dict:
        """
        Método 3: Usar dominio terabox.app
        """
        print("\n" + "="*60)
        print("MÉTODO 3: Dominio terabox.app")
        print("="*60)
        
        self._setup_session()
        surl = extract_surl(url)
        
        # Cambiar dominio
        self.session.headers['Host'] = 'www.terabox.app'
        self.session.headers['Referer'] = f'https://www.terabox.app/sharing/link?surl={surl}'
        
        api_url = "https://www.terabox.app/share/list"
        
        params = {
            'app_id': '250528',
            'web': '1',
            'channel': 'dubox',
            'clienttype': '0',
            'shorturl': surl,
            'root': '1'
        }
        
        print(f"Llamando API: {api_url}")
        
        try:
            response = self.session.get(api_url, params=params, timeout=30)
            print(f"Status: {response.status_code}")
            
            data = response.json()
            print(f"Respuesta: {json.dumps(data, indent=2)[:500]}...")
            
            if data.get('errno') == 0:
                print("\n✅ ÉXITO!")
                return {"ok": True, "data": data}
            else:
                return {"error": data.get('errmsg'), "errno": data.get('errno')}
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return {"error": str(e)}

    def test_method_4_api_public(self, url: str) -> dict:
        """
        Método 4: APIs públicas de terceros (terabox-dl)
        """
        print("\n" + "="*60)
        print("MÉTODO 4: APIs públicas de terceros")
        print("="*60)
        
        # Probar algunas APIs públicas conocidas
        apis = [
            {
                "name": "TeraBox DL API 1",
                "url": "https://teraboxdownloader.online/api/get-download-link",
                "method": "POST",
                "data": {"url": url}
            },
            {
                "name": "1024TeraBox API",
                "url": f"https://1024terabox.com/api/get-download-link?url={url}",
                "method": "GET"
            }
        ]
        
        for api in apis:
            print(f"\nProbando: {api['name']}")
            try:
                if api['method'] == 'POST':
                    resp = requests.post(api['url'], json=api.get('data', {}), timeout=30)
                else:
                    resp = requests.get(api['url'], timeout=30)
                    
                print(f"Status: {resp.status_code}")
                print(f"Respuesta: {resp.text[:500]}")
                
                if resp.ok:
                    try:
                        data = resp.json()
                        if data.get('download_link') or data.get('dlink'):
                            return {"ok": True, "data": data, "source": api['name']}
                    except:
                        pass
            except Exception as e:
                print(f"Error: {e}")
                
        return {"error": "Ninguna API pública funcionó"}
        
    def test_method_5_direct_parsing(self, url: str) -> dict:
        """
        Método 5: Parsear HTML directamente para extraer enlaces
        """
        print("\n" + "="*60)
        print("MÉTODO 5: Parseo directo de HTML")
        print("="*60)
        
        self._setup_session()
        surl = extract_surl(url)
        page_url = f"https://www.terabox.com/sharing/link?surl={surl}"
        
        try:
            response = self.session.get(page_url, timeout=30)
            print(f"Status: {response.status_code}")
            
            html = response.text
            
            # Buscar datos embebidos en el HTML
            patterns = [
                r'"dlink"\s*:\s*"([^"]+)"',
                r'"download_link"\s*:\s*"([^"]+)"',
                r'href="([^"]*download[^"]*)"',
                r'"server_filename"\s*:\s*"([^"]+)"',
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.yunData\s*=\s*({.+?});',
            ]
            
            results = {}
            for pattern in patterns:
                matches = re.findall(pattern, html)
                if matches:
                    print(f"Patrón '{pattern[:30]}...' encontró {len(matches)} coincidencias")
                    results[pattern[:30]] = matches[:3]
                    
            # Buscar JSON embebido
            json_patterns = [
                r'<script[^>]*>.*?locals\.mbox\s*=\s*({.+?})\s*;.*?</script>',
                r'<script[^>]*>\s*var\s+context\s*=\s*({.+?})\s*;?\s*</script>',
            ]
            
            for pattern in json_patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        print(f"JSON encontrado: {json.dumps(data, indent=2)[:500]}")
                        results['json'] = data
                    except:
                        pass
                        
            if results:
                return {"ok": True, "results": results}
            else:
                return {"error": "No se encontraron datos útiles en HTML"}
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return {"error": str(e)}


async def test_playwright_method(url: str, cookies: list):
    """
    Método 6: Playwright con cookies inyectadas
    """
    print("\n" + "="*60)
    print("MÉTODO 6: Playwright con cookies")
    print("="*60)
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ Playwright no instalado")
        return {"error": "Playwright not installed"}
        
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            )
            
            # Convertir cookies al formato de Playwright
            playwright_cookies = []
            for c in cookies:
                pc = {
                    'name': c['name'],
                    'value': c['value'],
                    'domain': c.get('domain', '.terabox.com'),
                    'path': c.get('path', '/'),
                }
                # Solo agregar expires si existe y es válido
                if c.get('expirationDate'):
                    pc['expires'] = c['expirationDate']
                playwright_cookies.append(pc)
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            )
            
            # Inyectar cookies
            await context.add_cookies(playwright_cookies)
            print(f"✓ {len(playwright_cookies)} cookies inyectadas")
            
            page = await context.new_page()
            
            # Inyectar script anti-detección
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            surl = extract_surl(url)
            page_url = f"https://www.terabox.com/sharing/link?surl={surl}"
            
            print(f"Navegando a: {page_url}")
            response = await page.goto(page_url, wait_until='networkidle', timeout=60000)
            
            print(f"Status: {response.status if response else 'None'}")
            print(f"URL final: {page.url}")
            
            # Esperar a que cargue
            await asyncio.sleep(3)
            
            # Tomar screenshot para debug
            await page.screenshot(path='/tmp/terabox_test.png')
            print("Screenshot guardado en /tmp/terabox_test.png")
            
            # Buscar info del archivo
            content = await page.content()
            
            # Buscar botón de descarga
            download_selectors = [
                '.download-btn',
                'button:has-text("Download")',
                'button:has-text("Descargar")',
                '[class*="download"]',
                '.action-bar-download',
            ]
            
            for selector in download_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        is_visible = await btn.is_visible()
                        print(f"Botón encontrado: {selector} (visible: {is_visible})")
                except:
                    pass
            
            # Buscar nombre de archivo
            for selector in ['.file-name', '.filename', '[class*="file-name"]']:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        text = await elem.inner_text()
                        print(f"Archivo: {text}")
                        break
                except:
                    pass
            
            # Extraer cookies actualizadas
            new_cookies = await context.cookies()
            print(f"Cookies después de navegación: {len(new_cookies)}")
            
            # Verificar si estamos autenticados
            auth_indicators = ['.user-avatar', '.user-name', '[class*="user-info"]']
            is_logged_in = False
            for selector in auth_indicators:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        is_logged_in = True
                        print(f"✓ Usuario logueado (indicador: {selector})")
                        break
                except:
                    pass
            
            if not is_logged_in:
                print("⚠ No parece haber sesión activa")
            
            # Intentar interceptar API calls
            print("\nIntentando llamar API desde página...")
            
            # Ejecutar JavaScript para obtener datos
            try:
                data = await page.evaluate("""
                    () => {
                        // Buscar datos en variables globales
                        if (window.yunData) return window.yunData;
                        if (window.__INITIAL_STATE__) return window.__INITIAL_STATE__;
                        if (window.locals && window.locals.mbox) return window.locals.mbox;
                        
                        // Intentar extraer del DOM
                        const scripts = document.querySelectorAll('script');
                        for (const script of scripts) {
                            const text = script.textContent;
                            if (text.includes('file_list') || text.includes('dlink')) {
                                const match = text.match(/\{[^{}]*file_list[^{}]*\}/);
                                if (match) {
                                    try { return JSON.parse(match[0]); } catch(e) {}
                                }
                            }
                        }
                        return null;
                    }
                """)
                
                if data:
                    print(f"Datos encontrados via JS: {json.dumps(data, indent=2)[:500]}")
                    return {"ok": True, "data": data, "method": "playwright_js"}
            except Exception as e:
                print(f"Error ejecutando JS: {e}")
            
            await browser.close()
            
            return {"ok": False, "error": "Could not extract data", "logged_in": is_logged_in}
            
    except Exception as e:
        print(f"❌ Error Playwright: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def main():
    """Ejecuta todas las pruebas."""
    print("="*60)
    print("PRUEBAS DE BYPASS TERABOX")
    print(f"URL de prueba: {TEST_URL}")
    print("="*60)
    
    tester = TeraBoxBypassTest()
    
    results = {}
    
    # Método 1
    results['method_1'] = tester.test_method_1_share_list(TEST_URL)
    
    # Método 2
    results['method_2'] = tester.test_method_2_share_wxlist(TEST_URL)
    
    # Método 3
    results['method_3'] = tester.test_method_3_terabox_app_domain(TEST_URL)
    
    # Método 5
    results['method_5'] = tester.test_method_5_direct_parsing(TEST_URL)
    
    # Método 6 (Playwright)
    print("\nProbando Playwright...")
    results['method_6'] = asyncio.run(test_playwright_method(TEST_URL, RAW_COOKIES))
    
    # Resumen
    print("\n" + "="*60)
    print("RESUMEN DE RESULTADOS")
    print("="*60)
    
    for method, result in results.items():
        status = "✅ ÉXITO" if result.get('ok') else f"❌ FALLO: {result.get('error', 'Unknown')}"
        print(f"{method}: {status}")
        
    # Identificar mejor método
    for method, result in results.items():
        if result.get('ok'):
            print(f"\n🎉 Método exitoso: {method}")
            print(f"Datos: {json.dumps(result, indent=2)[:1000]}")
            break
    else:
        print("\n⚠ Ningún método funcionó. Se necesita investigación adicional.")


if __name__ == "__main__":
    main()
