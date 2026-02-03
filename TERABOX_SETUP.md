# Configuración de TeraBox

Para descargar archivos de TeraBox necesitas configurar los tokens de una cuenta.

## Paso 1: Crear cuenta en TeraBox

1. Ve a https://www.terabox.com
2. Regístrate con email o Google (es gratis, 1TB de almacenamiento)
3. Inicia sesión

## Paso 2: Obtener los tokens

Una vez logueado, abre las DevTools del navegador (F12) y sigue estos pasos:

### TERABOX_COOKIE

1. Ve a la pestaña **Application** (Chrome) o **Storage** (Firefox)
2. En el panel izquierdo, expande **Cookies** > `https://www.terabox.com`
3. Busca la cookie llamada `ndus`
4. Copia el valor completo
5. El formato final debe ser: `ndus=XXXXXXXXXXXXXXXX`

### TERABOX_JS_TOKEN

1. Abre cualquier carpeta compartida de TeraBox (por ejemplo, abre un link de descarga)
2. Ve a la pestaña **Console** en DevTools
3. Ejecuta este comando:
   ```javascript
   document.body.innerHTML.match(/fn%28%22([^%]+)%22%29/)?.[1] || "No encontrado - prueba con otra página"
   ```
4. Copia el resultado (es una cadena larga de caracteres)

### TERABOX_DP_LOGID

1. En la misma página de TeraBox
2. En la **Console**, ejecuta:
   ```javascript
   document.body.innerHTML.match(/dp-logid=([^&"]+)/)?.[1] || "No encontrado"
   ```
3. Copia el resultado

## Paso 3: Configurar en .env

Crea o edita el archivo `.env` en la raíz del proyecto:

```env
# TeraBox Configuration
TERABOX_COOKIE=ndus=XXXXXXXXXXXXXXXX
TERABOX_JS_TOKEN=YYYYYYYYYYYYYYYY
TERABOX_DP_LOGID=ZZZZZZZZZZZZZZZZ
```

## Paso 4: Reiniciar el backend

```bash
docker-compose restart backend
```

## Verificar configuración

Los logs del backend mostrarán si TeraBox está configurado correctamente:
- `TeraBox: Using configured account tokens` = Configurado correctamente
- `TeraBox: No configurado - necesita TERABOX_COOKIE y TERABOX_JS_TOKEN` = Falta configuración

## Notas importantes

- Los tokens pueden expirar después de un tiempo. Si las descargas de TeraBox fallan, obtén nuevos tokens.
- La cookie `ndus` es la más importante y suele durar varios días/semanas.
- El `JS_TOKEN` puede cambiar más frecuentemente.
- Si solo configuras `TERABOX_COOKIE`, podrás obtener información de archivos pero no descargar.

## Solución de problemas

### Error "errno 9019"
- El token ha expirado. Obtén nuevos tokens.

### Error "errno 31034"
- Límite de descargas alcanzado. Espera unas horas o usa otra cuenta.

### Error "errno -6"
- El archivo ha sido eliminado o el link no es válido.
