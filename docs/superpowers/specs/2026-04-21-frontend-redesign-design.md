# Alejandría — Rediseño Frontend v3.2

**Fecha:** 2026-04-21  
**Estado:** Aprobado — pendiente de implementación  
**Alcance:** Frontend completo (React + Tailwind CSS)

---

## Resumen ejecutivo

Rediseño visual y de UX del frontend de Alejandría con estética **cinematográfica/premium**: negro profundo, acentos dorados, tipografía serif para títulos y sans-serif moderna para UI. El enfoque de implementación es **Design Tokens primero** — se actualiza el sistema de diseño base (colores, fuentes) y los cambios fluyen hacia todos los componentes y páginas.

El trabajo se divide en 4 áreas por orden de prioridad:
1. **A — Identidad visual y pulido** (design tokens, fuentes, fix de profundidad)
2. **D — Layout y jerarquía de páginas** (Discover, Detail page, Queue)
3. **C — Navegación y UX de flujos** (Navbar, móvil, transiciones)
4. **B — Componentes y consistencia** (unificación de cards, iconos)

---

## 1. Sistema de diseño (tokens)

### 1.1 Paleta de colores

Actualizar `frontend/tailwind.config.js`:

```js
colors: {
  // Fondos — 4 capas con profundidad real (actualmente dark-card = dark-lighter = mismo valor, sin diferencia)
  dark: {
    base:    '#07070b',  // fondo raíz del <body>
    DEFAULT: '#0d1117',  // fondo de páginas / contenedores
    card:    '#161b22',  // tarjetas, modales, dropdowns
    lighter: '#21262d',  // inputs, hover states, elementos elevados
  },
  // Acento principal — dorado/ámbar
  gold: {
    DEFAULT: '#c9a84c',  // botones, CTAs, nav activo
    light:   '#e2b96a',  // texto destacado, hover, iconos
    muted:   'rgba(201,168,76,0.12)',  // fondos de badges
  },
  // Acentos por tipo de contenido — versiones desaturadas para dark mode
  manga: {
    DEFAULT: '#6b9bd2',  // azul acero
    muted:   'rgba(107,155,210,0.12)',
  },
  comic: {
    DEFAULT: '#c07a5a',  // cobre/ladrillo
    muted:   'rgba(192,122,90,0.12)',
  },
  book: {
    DEFAULT: '#7aa67a',  // verde salvia
    muted:   'rgba(122,166,122,0.12)',
  },
}
```

**Fix crítico:** `dark-card` y `dark-lighter` actualmente tienen el mismo valor `#1E293B`. Separarlos en `#161b22` vs `#21262d` da profundidad real a todas las tarjetas sin tocar ningún componente.

### 1.2 Tipografía

Cargar desde Google Fonts en `frontend/index.html`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
```

Añadir a `tailwind.config.js`:
```js
fontFamily: {
  serif: ['"Playfair Display"', 'Georgia', 'serif'],
  sans:  ['Outfit', 'system-ui', 'sans-serif'],
}
```

Actualizar `frontend/src/index.css`:
```css
body {
  font-family: 'Outfit', system-ui, sans-serif;
}
```

**Uso:**
- `font-serif` — títulos de manga/cómic/libro (h1, h2 de contenido, nombre en cards y detail page)
- `font-sans font-700` — UI labels, botones, navegación
- `font-sans font-400` — cuerpo de texto, descripciones
- `font-sans font-300` — metadatos, fechas, texto secundario

### 1.3 Animaciones adicionales

Añadir a `tailwind.config.js`:
```js
keyframes: {
  shimmer: {
    '0%':   { backgroundPosition: '-200% 0' },
    '100%': { backgroundPosition: '200% 0' },
  },
  'page-in': {
    '0%':   { opacity: '0', transform: 'translateY(8px)' },
    '100%': { opacity: '1', transform: 'translateY(0)' },
  },
}
animation: {
  shimmer:  'shimmer 1.8s linear infinite',
  'page-in': 'page-in 0.2s ease-out',
}
```

---

## 2. Componentes principales

### 2.1 ContentCard

Cambios visuales (sin romper la API de props existente):

- **Borde superior:** 2px en color del tipo (`border-t-2 border-manga`) en vez de 4px azul fijo
- **Fondo:** `bg-dark-card` (ahora con profundidad real por el fix de tokens)
- **Sombra:** `shadow-[0_8px_32px_rgba(0,0,0,0.5)]` en vez de `shadow-lg`
- **Título:** añadir `font-serif` a `<h3>` del título del contenido
- **Autor/subtítulo:** texto en color del tipo con `uppercase tracking-wider text-xs font-semibold`
- **Badges de género:** fondo `{type}-muted`, borde `border border-{type}/20`, texto en `{type}`
- **Rating:** estrella y valor en `text-gold` en vez de `text-yellow-400`
- **Barra de progreso:** degradado `from-{type} to-{type}/60` y altura reducida a `h-[3px]`
- **Hover:** `hover:scale-[1.02]` en vez de `hover:scale-105` (más sutil)
- **Overlay de descripción:** mantener comportamiento, mejorar gradiente
- **Sección de reading status:** separador con `border-dark-lighter`, punto de color por estado

### 2.2 Navbar

- **Logo:** reemplazar emoji `📚` + texto por cuadrado dorado `32×32px` con `A` en Playfair Display 800 + `span` con nombre en `font-serif`
- **Nav activo:** `bg-gold/10 border border-gold/20 text-gold` en vez de `bg-primary text-white`
- **Texto en desktop:** visible en `md:` (quitar restricción `lg:inline` que solo lo muestra en pantallas grandes)
- **Separador inferior:** línea decorativa `h-px bg-gradient-to-r from-transparent via-gold/20 to-transparent`
- **Notificación dropdown:** actualizar colores a nuevos tokens
- **Toaster en App.jsx:** background `#161b22`, border `rgba(201,168,76,0.2)`

### 2.3 ContentGrid — Skeleton loader

Reemplazar `animate-pulse` estático por shimmer animado:
```jsx
// SkeletonCard con shimmer
<div className="h-full bg-gradient-to-r from-dark-card via-dark-lighter to-dark-card bg-[length:200%_100%] animate-shimmer rounded" />
```

---

## 3. Layout de páginas

### 3.1 Discover (`/`)

**Hero section** (nuevo bloque encima del grid):
```
┌─────────────────────────────────────────┐
│ RECOMENDADO PARA TI              [gold]  │
│ Descubrir                [Playfair 2xl]  │
│ Basado en tu biblioteca · 24 sugerencias │
│ [Todo] [Manga] [Libros]     [↻ Refresh] │
└─────────────────────────────────────────┘
```
- Fondo: `bg-dark-card` con sutil gradiente lateral
- Filtros: pills redondeados (`rounded-full`) en vez de `rounded-lg`
- Activo: `bg-gold/15 border-gold/30 text-gold`

**Grid:** reducir de `xl:grid-cols-6` a `xl:grid-cols-5` (tarjetas menos apretadas).

**Rating badge** en portada: `bg-black/70 text-gold text-xs` en esquina superior derecha de la imagen.

### 3.2 ContentDetailPage

**Banner + portada flotante:**
- Banner: `h-48` con `bg-gradient-to-br from-dark-card to-dark` + gradiente fade-out inferior
- Portada: `absolute bottom-[-40px] left-6` con `shadow-[0_8px_32px_rgba(0,0,0,0.6)]` y borde `border border-{type}/20`
- Espacio tras banner: `pt-14` para compensar la portada flotante

**Info section:**
- Tipo + géneros: `text-{type} text-xs font-semibold uppercase tracking-widest`
- Título: `font-serif text-3xl font-bold`
- Autor/editorial/año: `text-sm text-gray-500 font-light`

**Action bar (botones):**
- Principal (Descargar): `bg-gradient-to-r from-gold to-gold-light text-dark-base font-bold`
- Secundarios: `bg-dark-card border border-white/8 text-gray-400 hover:text-white`

**Stats row** (nuevo bloque):
```
┌──────────────────────────────────────────┐
│  28          40          70%     Leyendo  │
│  Descarg.    Total       Progreso Estado  │
└──────────────────────────────────────────┘
```
- Fondo `bg-dark-card rounded-xl`, separadores verticales `border-r border-white/6`
- "Progreso" en `text-gold`, "Estado" en color del tipo

**Lista de capítulos/tomos:**
- Punto de color `w-1.5 h-1.5 rounded-full` por estado: `bg-book` (leído), `bg-manga` (descargando), `bg-dark-lighter` (pendiente)
- Fila activa (descargando): borde izquierdo `border-l-2 border-{type}`

### 3.3 Queue (`/queue`)

**Items de cola:**
- Añadir miniatura de portada `w-9 h-12` a cada item
- Título en `font-serif text-sm`
- Subtipo con color: `text-{type} text-xs font-semibold uppercase tracking-wide`
- Barra de progreso con gradiente y `h-[3px]`
- Borde del item según estado: `border-{type}/20` (descargando), `border-book/20` (completado), `border-red-500/20` (error)
- Reemplazar emojis (🕐✅❌⚙️📤) por react-icons equivalentes: `FiClock, FiCheckCircle, FiAlertCircle, FiSettings, FiSend`

---

## 4. Navegación y transiciones

### 4.1 Transiciones de página

En `App.jsx`, añadir animación de entrada a `<main>`:
```jsx
// Usar location.key como key para re-montar en cada navegación
<main key={location.key} className="animate-page-in">
  <ErrorBoundary><Outlet /></ErrorBoundary>
</main>
```

En `index.css`:
```css
/* Asegurar que la animación no afecta al scroll */
@media (prefers-reduced-motion: no-preference) {
  .animate-page-in { animation: page-in 0.2s ease-out; }
}
```

### 4.2 Menú móvil

- Items: `py-2.5 px-3 rounded-lg` (más grandes, más fáciles de tocar)
- Icono siempre visible + texto
- Separador `hr` entre items de navegación y sección usuario/ajustes
- Activo: `bg-gold/10 text-gold` con borde izquierdo `border-l-2 border-gold`

---

## 5. Unificación de componentes

### 5.1 Discover — eliminar RecommendationCard

`Discover.jsx` tiene un componente `RecommendationCard` local con lógica duplicada respecto a `ContentCard`. Reemplazar por:
```jsx
<ContentCard
  item={adaptRecToItem(rec)}
  type={rec.content_type}
  showAddButton={!isAdded}
  onAdd={() => onAdd(rec)}
/>
```
Requiere una función adaptadora `adaptRecToItem(rec)` que mapee los campos de `rec` al shape de `item` que espera `ContentCard`.

### 5.2 Search — unificar tarjetas de resultados

`Search.jsx` renderiza tarjetas custom por tipo (manga, cómic, libro). Reemplazar por `ContentCard` con `showAddButton={!item.in_library}`. Los badges de scraper disponibles (✓ Encontrado, 📚 N tomos) se añaden como prop `badges` o se renderizan encima de la card.

### 5.3 Queue — iconos react-icons

Reemplazar constante `ACTIVITY_ICONS` de emojis por:
```js
import { FiClock, FiDownload, FiCheckCircle, FiAlertCircle, FiSettings, FiSend } from 'react-icons/fi';

const ACTIVITY_ICONS = {
  queued:      { Icon: FiClock,        colorClass: 'text-gray-400' },
  downloading: { Icon: FiDownload,     colorClass: 'text-manga' },
  completed:   { Icon: FiCheckCircle,  colorClass: 'text-book' },
  failed:      { Icon: FiAlertCircle,  colorClass: 'text-red-400' },
  converting:  { Icon: FiSettings,     colorClass: 'text-purple-400' },
  sent_kindle: { Icon: FiSend,         colorClass: 'text-gold' },
};
```

---

## 6. Archivos afectados

| Archivo | Tipo de cambio |
|---|---|
| `frontend/index.html` | Añadir Google Fonts |
| `frontend/tailwind.config.js` | Nueva paleta + fuentes + animaciones |
| `frontend/src/index.css` | font-family body + shimmer + page-in |
| `frontend/src/App.jsx` | Toaster colors + `animate-page-in` en main |
| `frontend/src/components/Navbar.jsx` | Logo, nav activo, texto desktop, separador |
| `frontend/src/components/ContentCard.jsx` | Fuente, colores por tipo, sombra, hover, barra |
| `frontend/src/components/ContentGrid.jsx` | Skeleton shimmer |
| `frontend/src/components/ContentDetailPage.jsx` | Banner, portada flotante, stats row, action bar |
| `frontend/src/pages/Discover.jsx` | Hero section, pills, eliminar RecommendationCard |
| `frontend/src/pages/Queue.jsx` | Items con portada, react-icons, barra progreso |
| `frontend/src/pages/Search.jsx` | Unificar con ContentCard |
| `frontend/src/pages/Home.jsx` | Aplicar nuevos tokens (stats cards) |

---

## 7. No incluido en este diseño

- Cambios al backend o API
- Nuevas funcionalidades (solo mejora visual/UX)
- Rediseño del MangaReader (fullscreen, lógica propia)
- Página de Login/Register (fuera del flujo principal)
- Página AdminUsers (uso ocasional)

---

## 8. Criterios de éxito

- Las tarjetas tienen profundidad visual visible (card ≠ background)
- Los títulos de contenido usan Playfair Display
- El logo ya no es un emoji
- Navegar entre páginas tiene transición suave
- La Cola muestra miniaturas y sin emojis mezclados
- La página de detalle tiene portada flotante y stats row
- Discover tiene hero section con filtros pill
