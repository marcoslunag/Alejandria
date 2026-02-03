#!/usr/bin/env python3
"""
Script simple de prueba para el bypass de TeraBox
Prueba multiples APIs proxy
"""

import sys
import os

# Agregar el path del backend al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
import re
from urllib.parse import urlparse, parse_qs

# URL de prueba
TEST_URL = "https://www.terabox.com/spanish/sharing/link?surl=4LpF4n6kZZO8p8p7TO3w2Q"

# Cookies proporcionadas por el usuario
USER_COOKIES = {
    'ndus': 'YfNzRr3teHuia6Q7URN2rVcurJn62FP9BRx0EuuD',
    'csrfToken': '1KKyYQDCrpcJ9OhKv-VUmmfp',
    'PANWEB': '1',
    'browserid': '5tO98R8t61oFUYdbRY6GDgUMAlaX13lEK0dEn_lCYIlKHf8acGLU5GTpJzk=',
    'ndut_fmt': '2B09EB1D66C1C6C01F429ACEF802114AFC07C1060DFA9769D652D75A6866AD02',
    'lang': 'es',
    'TSID': 'iqnJ1oEhSdSQtaf2uMVvE9jn9Zm1VhKb',
    '__bid_n': '19c05c4b6483bd38d84207',
    'ndut_fmv': 'bfac02e969efc325b0f7579efe0f1a9029b474a47c4df45006d835036427b4ecbc33cf3b20683159f38b92436e44c1e541ddbe69bcffa47e1078e61ee69e3b74042705838b38a13b6d333ce7cdd7e75637896b5dec0deb08c592a5b1ff910b8dca266230f544d2a80286651e09169452',
}

def extract_short_url(url: str) -> str:
    """Extrae el short_url de la URL."""
    if '/s/' in url:
        match = re.search(r'/s/(1?)([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(2)
    
    if 'surl=' in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if 'surl' in params:
            return params['surl'][0]
    
    return ""


def find_between(string, start, end):
    """Extrae substring entre dos marcadores."""
    start_index = string.find(start) + len(start)
    if start_index == len(start) - 1:
        return ""
    end_index = string.find(end, start_index)
    if end_index == -1:
        return ""
    return string[start_index:end_index]


def test_vercel_api():
    """Prueba la API de Vercel (teraboxapi-phi.vercel.app)."""
    print("=" * 60)
    print("PRUEBA 1: API Vercel (teraboxapi-phi.vercel.app)")
    print("=" * 60)
    
    api_url = f"https://teraboxapi-phi.vercel.app/api?url={TEST_URL}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    try:
        print(f"Llamando: {api_url}")
        response = requests.get(api_url, headers=headers, timeout=60)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Respuesta: {json.dumps(data, indent=2, ensure_ascii=False)[:1500]}")
            
            if data.get('status') == 'success' and data.get('Extracted Info'):
                print("\n[OK] API Vercel funciono!")
                return data
        else:
            print(f"Error HTTP: {response.status_code}")
            print(f"Respuesta: {response.text[:500]}")
            
    except Exception as e:
        print(f"[ERROR]: {e}")
    
    return None


def test_1024tera_direct():
    """Prueba acceso directo a 1024tera.com con cookies del usuario."""
    print("\n" + "=" * 60)
    print("PRUEBA 2: API directa 1024tera.com (con cookies)")
    print("=" * 60)
    
    short_url = extract_short_url(TEST_URL)
    print(f"Short URL: {short_url}")
    
    # Paso 1: Obtener información del archivo
    print("\n--- Paso 1: Obtener información ---")
    
    info_url = "https://terabox-dl.qtcloud.workers.dev/api/get-info"
    params = {
        'shorturl': short_url,
        'pwd': ''
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    try:
        response = requests.get(info_url, params=params, headers=headers, timeout=30)
        print(f"Status: {response.status_code}")
        
        data = response.json()
        print(f"Respuesta: {json.dumps(data, indent=2, ensure_ascii=False)[:1500]}")
        
        if data.get('ok') == False:
            print(f"\n❌ Error: {data.get('message')}")
            return None
        
        print(f"\n✅ Información obtenida correctamente!")
        
        # Extraer datos importantes
        shareid = data.get('shareid')
        uk = data.get('uk')
        sign = data.get('sign')
        timestamp = data.get('timestamp')
        file_list = data.get('list', [])
        
        print(f"\n  shareid: {shareid}")
        print(f"  uk: {uk}")
        print(f"  sign: {sign}")
        print(f"  timestamp: {timestamp}")
        print(f"  Archivos encontrados: {len(file_list)}")
        
        # Mostrar archivos
        def show_files(items, indent=0):
            for item in items:
                prefix = "  " * indent
                is_dir = item.get('is_dir') == 1 or item.get('is_dir') == '1'
                name = item.get('filename') or item.get('server_filename', 'unknown')
                
                if is_dir:
                    print(f"{prefix}📁 {name}/")
                    children = item.get('children', [])
                    if children:
                        show_files(children, indent + 1)
                else:
                    size = item.get('size', 0)
                    size_mb = size / (1024 * 1024) if size else 0
                    fs_id = item.get('fs_id')
                    print(f"{prefix}📄 {name} ({size_mb:.2f} MB) [fs_id: {fs_id}]")
        
        print("\n  Estructura de archivos:")
        show_files(file_list, indent=1)
        
        # Paso 2: Obtener enlace de descarga del primer archivo
        print("\n--- Paso 2: Obtener enlace de descarga ---")
        
        # Encontrar primer archivo (no carpeta)
        def find_first_file(items):
            for item in items:
                is_dir = item.get('is_dir') == 1 or item.get('is_dir') == '1'
                if is_dir:
                    children = item.get('children', [])
                    result = find_first_file(children)
                    if result:
                        return result
                else:
                    return item
            return None
        
        first_file = find_first_file(file_list)
        
        if not first_file:
            print("❌ No se encontraron archivos para descargar")
            return data
        
        fs_id = first_file.get('fs_id')
        filename = first_file.get('filename') or first_file.get('server_filename')
        
        print(f"  Archivo objetivo: {filename}")
        print(f"  fs_id: {fs_id}")
        
        download_url = "https://terabox-dl.qtcloud.workers.dev/api/get-download"
        body = {
            'shareid': str(shareid),
            'uk': str(uk),
            'sign': sign,
            'timestamp': str(timestamp),
            'fs_id': str(fs_id),
        }
        
        response2 = requests.post(download_url, json=body, headers=headers, timeout=30)
        print(f"  Status: {response2.status_code}")
        
        data2 = response2.json()
        print(f"  Respuesta: {json.dumps(data2, indent=2)[:500]}")
        
        if data2.get('ok') == False:
            print(f"\n❌ Error obteniendo enlace: {data2.get('message')}")
            return data
        
        download_link = data2.get('downloadLink')
        print(f"\n✅ Enlace de descarga obtenido:")
        print(f"  {download_link[:100]}...")
        
        return {
            "info": data,
            "download_link": download_link,
            "filename": filename
        }
        
    except requests.exceptions.Timeout:
        print("❌ Timeout en la petición")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de red: {e}")
        return None
    except json.JSONDecodeError:
        print(f"❌ Respuesta no es JSON válido: {response.text[:500]}")
        return None
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_download(download_link: str, filename: str):
    """Prueba la descarga real del archivo."""
    print("\n" + "=" * 60)
    print("PRUEBA: Descarga de archivo")
    print("=" * 60)
    
    if not download_link:
        print("❌ No hay enlace de descarga para probar")
        return
    
    print(f"Archivo: {filename}")
    print(f"Enlace: {download_link[:80]}...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.terabox.com/',
    }
    
    try:
        # Hacer petición HEAD primero para ver tamaño
        print("\nVerificando enlace...")
        head_response = requests.head(download_link, headers=headers, timeout=30, allow_redirects=True)
        print(f"Status: {head_response.status_code}")
        
        content_length = head_response.headers.get('content-length')
        content_type = head_response.headers.get('content-type')
        
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            print(f"Tamaño: {size_mb:.2f} MB")
        
        if content_type:
            print(f"Tipo: {content_type}")
        
        if head_response.status_code == 200:
            print("\n✅ Enlace de descarga válido y funcional!")
            print(f"\nPara descargar manualmente, usa:")
            print(f"  curl -L -o \"{filename}\" \"{download_link}\"")
        else:
            print(f"\n⚠ El enlace retornó status {head_response.status_code}")
            
    except Exception as e:
        print(f"❌ Error verificando enlace: {e}")


def main():
    """Ejecuta las pruebas."""
    print("\n" + "=" * 60)
    print("PRUEBAS DE BYPASS TERABOX - API PROXY")
    print("=" * 60 + "\n")
    
    result = test_proxy_api()
    
    if result and result.get('download_link'):
        test_download(result['download_link'], result.get('filename', 'archivo'))
    
    print("\n" + "=" * 60)
    print("FIN DE PRUEBAS")
    print("=" * 60)


if __name__ == "__main__":
    main()
