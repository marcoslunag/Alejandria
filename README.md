# Alejandria

<div align="center">

**Tu biblioteca digital personal para manga, cómics y libros**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://reactjs.org/)

[Características](#-características) • [Instalación](#-instalación) • [Configuración](#-configuración) • [Uso](#-uso) • [API](#-api) • [Roadmap](#-roadmap)

</div>

---

## Descripción

**Alejandria** es una plataforma de gestión de biblioteca digital diseñada para manga, cómics y libros. Inspirada en herramientas como Radarr/Sonarr y Kaizoku, ofrece descarga automatizada, conversión a formatos Kindle y envío directo a tus dispositivos.

### ¿Por qué Alejandria?

- **Todo en uno**: Descarga, convierte y envía a tu Kindle automáticamente
- **Múltiples fuentes**: Soporte para TomosManga, MangaYComics y más
- **Integración AniList**: Busca y añade mangas directamente desde AniList
- **Archivos grandes**: Soporte para archivos >25MB usando STK (Send to Kindle API)
- **Auto-división**: Divide automáticamente tomos grandes en partes para cumplir límites
- **Interfaz moderna**: UI inspirada en Kaizoku con diseño oscuro y responsivo

---

## Características

### Biblioteca
- Gestión de biblioteca de manga/cómics
- Búsqueda en múltiples fuentes (TomosManga, MangaYComics, AniList)
- Metadatos automáticos desde AniList (portadas, sinopsis, autores)
- Estado de seguimiento por tomo (pendiente, descargado, convertido, enviado)

### Descargas
- Cola de descargas con prioridades
- Descargas concurrentes configurables
- Soporte para múltiples hosts (TeraBox, MediaFire, etc.)
- Reintentos automáticos en caso de error
- Cancelación de descargas en progreso

### Conversión
- Conversión automática a EPUB/MOBI usando KCC (Kindle Comic Converter)
- División automática de tomos grandes (>200MB)
- Perfiles optimizados para diferentes Kindles (KPW5, KO, K11, etc.)
- Metadatos ComicInfo.xml embebidos

### Kindle
- **Email**: Envío vía SMTP para archivos <25MB
- **STK (Send to Kindle API)**: Para archivos grandes con autenticación OAuth2
- Soporte multi-dispositivo
- División automática de envíos por partes

### Automatización
- Verificación periódica de nuevos capítulos (configurable)
- Descarga automática de nuevos tomos
- Conversión automática al detectar nuevos archivos
- Envío automático al Kindle (opcional)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                         ALEJANDRIA                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Frontend   │    │   Backend    │    │  KCC Worker  │     │
│  │  (React UI)  │───▶│  (FastAPI)   │───▶│  (Converter) │     │
│  │   :8888      │    │    :7878     │    │              │     │
│  └──────────────┘    └──────┬───────┘    └──────────────┘     │
│                             │                    │              │
│                             ▼                    ▼              │
│                    ┌──────────────┐      ┌──────────────┐      │
│                    │  PostgreSQL  │      │   /manga     │      │
│                    │   Database   │      │   /kindle    │      │
│                    └──────────────┘      └──────────────┘      │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Scrapers   │    │ Downloaders  │    │ Kindle Send  │     │
│  │ TomosManga   │    │   TeraBox    │    │  SMTP/STK    │     │
│  │ MangaYComics │    │  MediaFire   │    │   OAuth2     │     │
│  │   AniList    │    │   Generic    │    │              │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Instalación

### Requisitos

- Docker y Docker Compose
- 2GB RAM mínimo (4GB recomendado para conversiones)
- Cuenta SMTP para envío por email (Gmail, Outlook, etc.)
- Cuenta Amazon para STK (opcional, para archivos >25MB)

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/alejandria.git
cd alejandria
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus credenciales:

```env
# Kindle
KINDLE_EMAIL=tu-kindle@kindle.com

# SMTP (Gmail)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu-email@gmail.com
SMTP_PASSWORD=tu-app-password
SMTP_FROM_EMAIL=tu-email@gmail.com

# Base de datos
POSTGRES_USER=manga
POSTGRES_PASSWORD=tu-password-seguro
POSTGRES_DB=alejandria

# KCC
KCC_PROFILE=KPW5
KCC_FORMAT=MOBI
```

### 3. Iniciar servicios

```bash
docker-compose up -d
```

### 4. Acceder

- **Frontend**: http://localhost:8888
- **API Docs**: http://localhost:9878/docs
- **Calibre-Web** (opcional): http://localhost:8383

---

## Configuración

### SMTP (Gmail)

1. Habilita verificación en 2 pasos en tu cuenta Google
2. Genera una contraseña de aplicación: https://myaccount.google.com/apppasswords
3. Usa esa contraseña en `SMTP_PASSWORD`

### Kindle Email

1. Ve a Amazon > Contenido y Dispositivos > Preferencias
2. En "Configuración de documentos personales" anota tu email `@kindle.com`
3. Añade tu email SMTP a la lista de remitentes aprobados

### STK (Send to Kindle API) - Para archivos >25MB

1. En la interfaz web, ve a **Configuración > Kindle**
2. Click en "Autenticar con Amazon"
3. Inicia sesión con tu cuenta Amazon
4. Copia la URL de redirección y pégala
5. Selecciona tu dispositivo Kindle preferido

### Perfiles KCC

| Perfil | Dispositivo |
|--------|-------------|
| KPW5 | Kindle Paperwhite 5 (2021) |
| KPW4 | Kindle Paperwhite 4 (2018) |
| KO | Kindle Oasis |
| K11 | Kindle 11 |
| KS | Kindle Scribe |

---

## Uso

### Añadir manga

1. **Desde búsqueda**: Busca en la barra superior, selecciona de AniList o TomosManga
2. **Desde URL**: Pega directamente la URL de TomosManga o MangaYComics
3. **Desde AniList**: Busca por nombre y se vincula automáticamente con las fuentes

### Descargar tomos

1. Ve a la página del manga
2. Selecciona los tomos que quieres descargar
3. Click en "Descargar seleccionados"
4. Monitorea el progreso en la Cola de Descargas

### Enviar a Kindle

- **Automático**: Configura envío automático en Configuración
- **Manual**: Click en el botón "Kindle" en cualquier tomo convertido

---

## API

### Endpoints principales

#### Manga
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/manga/` | Listar biblioteca |
| GET | `/api/v1/manga/search` | Buscar manga |
| POST | `/api/v1/manga/add/anilist` | Añadir desde AniList |
| POST | `/api/v1/manga/add/url` | Añadir desde URL |
| GET | `/api/v1/manga/{id}` | Detalles de manga |
| DELETE | `/api/v1/manga/{id}` | Eliminar manga |
| POST | `/api/v1/manga/{id}/refresh` | Actualizar capítulos |

#### Capítulos
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/manga/{id}/chapters` | Listar capítulos |
| POST | `/api/v1/manga/{id}/chapters/download` | Descargar capítulos |

#### Cola
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/queue/` | Ver cola de descargas |
| POST | `/api/v1/queue/{id}/cancel` | Cancelar descarga |
| POST | `/api/v1/queue/{id}/retry` | Reintentar descarga |
| DELETE | `/api/v1/queue/{id}/file` | Eliminar archivo |

#### Kindle
| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/v1/kindle/send/{id}` | Enviar por email |
| POST | `/api/v1/kindle/stk/send/{id}` | Enviar por STK |
| GET | `/api/v1/kindle/stk/status` | Estado de autenticación |
| GET | `/api/v1/kindle/stk/devices` | Listar dispositivos |

Documentación completa en: http://localhost:9878/docs

---

## Estructura del Proyecto

```
alejandria/
├── backend/                    # API FastAPI
│   ├── app/
│   │   ├── api/v1/            # Endpoints REST
│   │   ├── models/            # Modelos SQLAlchemy
│   │   ├── schemas/           # Schemas Pydantic
│   │   ├── services/          # Lógica de negocio
│   │   │   ├── scraper.py     # Scraper genérico
│   │   │   ├── downloader.py  # Gestor de descargas
│   │   │   ├── scheduler.py   # Tareas programadas
│   │   │   ├── kindle_sender.py    # Envío por email
│   │   │   └── stk_kindle_sender.py # Envío por STK
│   │   └── main.py
│   └── Dockerfile
├── frontend/                   # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/        # Componentes reutilizables
│   │   ├── pages/             # Páginas principales
│   │   └── services/api.js    # Cliente API
│   └── Dockerfile
├── workers/
│   └── kcc-converter/         # Worker de conversión
│       ├── converter.py       # Lógica de conversión
│       └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Roadmap

### En desarrollo
- [ ] **Soporte para libros (EPUB/PDF)**
- [ ] **Soporte para cómics americanos**
- [ ] **Mejoras en TeraBox** - Resolver problemas de autenticación

### Planificado
- [ ] Notificaciones (Telegram, Discord, Email)
- [ ] Búsqueda en más fuentes (MangaDex, etc.)
- [ ] Importación masiva desde Calibre
- [ ] Estadísticas de lectura
- [ ] Sincronización con servicios de tracking (AniList, MAL)
- [ ] Modo offline / PWA
- [ ] Soporte multi-idioma

### Completado
- [x] Interfaz web moderna
- [x] Descarga automática desde TomosManga
- [x] Conversión a EPUB/MOBI con KCC
- [x] Envío a Kindle por email
- [x] STK para archivos grandes (>25MB)
- [x] División automática de tomos grandes
- [x] Integración con AniList
- [x] Cola de descargas con cancelación
- [x] Soporte multi-dispositivo Kindle

---

## Resolución de Problemas

### Error: "Archivos demasiado grandes para email"
Los archivos >25MB no se pueden enviar por email. Configura STK en Configuración > Kindle.

### Error: "STK not authenticated"
Ve a Configuración > Kindle y completa la autenticación con Amazon.

### La conversión falla
1. Verifica que el worker KCC está corriendo: `docker-compose logs kcc-converter`
2. Comprueba que KindleGen está instalado en el worker

### Las descargas se quedan "downloading"
```bash
# Reiniciar descargas atascadas
curl -X POST http://localhost:9878/api/v1/queue/reset-stuck
```

### Ver logs
```bash
# Todos los servicios
docker-compose logs -f

# Solo backend
docker-compose logs -f backend

# Solo conversor
docker-compose logs -f kcc-converter
```

---

## Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/NuevaCaracteristica`)
3. Commit tus cambios (`git commit -m 'Añade nueva característica'`)
4. Push a la rama (`git push origin feature/NuevaCaracteristica`)
5. Abre un Pull Request

---

## Licencia

Distribuido bajo la licencia MIT. Ver `LICENSE` para más información.

---

## Disclaimer

Este proyecto es solo para fines educativos y de uso personal. Respeta los derechos de autor y las leyes de tu país. Los desarrolladores no se hacen responsables del uso indebido de esta herramienta.

---

<div align="center">

Hecho con ❤️ para la comunidad

[Reportar Bug](https://github.com/tu-usuario/alejandria/issues) • [Solicitar Feature](https://github.com/tu-usuario/alejandria/issues)

</div>
