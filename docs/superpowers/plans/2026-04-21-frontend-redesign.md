# Frontend Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rediseñar el frontend de Alejandría con estética cinematográfica/premium: negro profundo, acentos dorados, Playfair Display para títulos de contenido y Outfit para UI.

**Architecture:** Design Tokens primero — actualizar `tailwind.config.js` e `index.css` con la nueva paleta y fuentes, luego propagar los cambios a componentes y páginas en orden de impacto. Sin cambios al backend ni a la API. Sin nuevas funcionalidades.

**Tech Stack:** React 18, Vite, Tailwind CSS 3.4, react-icons 4.12, react-hot-toast, Google Fonts (Playfair Display + Outfit)

---

## Archivos afectados

| Archivo | Cambio |
|---|---|
| `frontend/index.html` | Google Fonts + theme-color |
| `frontend/tailwind.config.js` | Nueva paleta + fuentes + animaciones |
| `frontend/src/index.css` | font-family body + keyframes shimmer + page-in |
| `frontend/src/App.jsx` | Toaster colors + `animate-page-in` en `<main>` |
| `frontend/src/components/ContentGrid.jsx` | Skeleton con shimmer |
| `frontend/src/components/Navbar.jsx` | Logo A dorado, active gold, texto siempre visible, separador |
| `frontend/src/components/ContentCard.jsx` | font-serif, colores por tipo, sombra, hover sutil, barra progreso |
| `frontend/src/components/ContentDetailPage.jsx` | Banner cinematográfico, font-serif título, genres pill, stats row, action bar |
| `frontend/src/pages/Discover.jsx` | Hero section, pills filtro, eliminar RecommendationCard |
| `frontend/src/pages/Queue.jsx` | Miniaturas, react-icons, barra progreso, borders por estado |
| `frontend/src/pages/Search.jsx` | Unificar tarjetas de resultado con ContentCard |
| `frontend/src/pages/Home.jsx` | Aplicar nuevos tokens a stats cards |

---

## Task 1: Design tokens — tailwind.config.js + index.html + index.css

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`

- [ ] **Step 1.1: Actualizar tailwind.config.js**

Reemplazar el contenido completo de `frontend/tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Playfair Display"', 'Georgia', 'serif'],
        sans:  ['Outfit', 'system-ui', 'sans-serif'],
      },
      colors: {
        primary: {
          DEFAULT: '#c9a84c',
          dark:    '#a8893a',
          light:   '#e2b96a',
        },
        dark: {
          base:    '#07070b',
          DEFAULT: '#0d1117',
          card:    '#161b22',
          lighter: '#21262d',
        },
        gold: {
          DEFAULT: '#c9a84c',
          light:   '#e2b96a',
        },
        manga: {
          DEFAULT: '#6b9bd2',
        },
        comic: {
          DEFAULT: '#c07a5a',
        },
        book: {
          DEFAULT: '#7aa67a',
        },
      },
      animation: {
        'fade-in':  'fadeIn 0.3s ease-in',
        'slide-up': 'slideUp 0.3s ease-out',
        'shimmer':  'shimmer 1.8s linear infinite',
        'page-in':  'pageIn 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',    opacity: '1' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        pageIn: {
          '0%':   { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 1.2: Añadir Google Fonts a index.html**

En `frontend/index.html`, añadir dentro de `<head>` justo antes del cierre `</head>`:

```html
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
```

También cambiar el `theme-color` existente:
```html
    <meta name="theme-color" content="#07070b" />
```

- [ ] **Step 1.3: Actualizar index.css**

Reemplazar el contenido completo de `frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  * {
    @apply border-gray-700;
  }

  body {
    @apply bg-dark text-gray-100 antialiased;
    font-family: 'Outfit', system-ui, sans-serif;
  }
}

@layer components {
  .btn {
    @apply px-4 py-2 rounded-lg font-medium transition-all duration-200;
  }

  .btn-primary {
    @apply bg-gold hover:bg-gold-light text-dark-base font-semibold;
  }

  .btn-secondary {
    @apply bg-dark-card hover:bg-dark-lighter text-white border border-white/8;
  }

  .card {
    @apply bg-dark-card rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.4)] overflow-hidden;
  }

  .input {
    @apply bg-dark-lighter border border-gray-700 rounded-lg px-4 py-2 text-white
           focus:outline-none focus:border-gold transition-colors font-sans;
  }
}

/* Shimmer skeleton */
.skeleton-shimmer {
  background: linear-gradient(
    90deg,
    theme('colors.dark.card') 0%,
    theme('colors.dark.lighter') 50%,
    theme('colors.dark.card') 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.8s linear infinite;
}

/* Page transition */
@media (prefers-reduced-motion: no-preference) {
  .animate-page-in {
    animation: pageIn 0.2s ease-out;
  }
}

/* Scrollbar */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #21262d; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #30363d; }
```

- [ ] **Step 1.4: Verificar build**

```bash
cd frontend && npm run build
```

Esperado: build sin errores. Si hay error de fuente no encontrada, verificar que `font-family` en index.css usa comillas para "Playfair Display".

- [ ] **Step 1.5: Commit**

```bash
git add frontend/tailwind.config.js frontend/index.html frontend/src/index.css
git commit -m "feat: design tokens — gold palette, Playfair+Outfit fonts, shimmer animation"
```

---

## Task 2: App.jsx — Toaster y transición de página

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 2.1: Actualizar Toaster colors y añadir animate-page-in**

En `frontend/src/App.jsx`:

1. Añadir `useLocation` al import de react-router-dom (ya está importado, solo verificar):
```js
import { BrowserRouter as Router, Routes, Route, Outlet, Navigate, useLocation } from 'react-router-dom';
```

2. En `ProtectedLayout`, añadir `useLocation`:
```jsx
function ProtectedLayout() {
  const { mustChangePassword, isAdmin, deviceSetupCompleted, loading } = useAuth();
  const location = useLocation();
  // ... resto del código ...

  return (
    <ProtectedRoute>
      <Navbar />
      <main key={location.key} className="animate-page-in">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </ProtectedRoute>
  );
}
```

3. Actualizar `AdminLayout` igual:
```jsx
function AdminLayout() {
  const { isAdmin, mustChangePassword, loading } = useAuth();
  const location = useLocation();
  // ... guards ...

  return (
    <ProtectedRoute>
      <Navbar />
      <main key={location.key} className="animate-page-in">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </ProtectedRoute>
  );
}
```

4. Actualizar Toaster en `App()`:
```jsx
<Toaster
  position="top-right"
  toastOptions={{
    duration: 4000,
    style: {
      background: '#161b22',
      color: '#f3f4f6',
      border: '1px solid rgba(201,168,76,0.2)',
      fontFamily: 'Outfit, system-ui, sans-serif',
    },
    success: {
      iconTheme: { primary: '#7aa67a', secondary: '#f3f4f6' },
    },
    error: {
      duration: 5000,
      iconTheme: { primary: '#ef4444', secondary: '#f3f4f6' },
    },
  }}
/>
```

5. Cambiar el fondo raíz:
```jsx
<div className="min-h-screen bg-dark-base">
```

- [ ] **Step 2.2: Verificar build**

```bash
cd frontend && npm run build
```

Esperado: sin errores.

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: page transition animation + gold toaster theme"
```

---

## Task 3: ContentGrid — Skeleton shimmer

**Files:**
- Modify: `frontend/src/components/ContentGrid.jsx`

- [ ] **Step 3.1: Reemplazar animate-pulse por shimmer**

En `frontend/src/components/ContentGrid.jsx`, reemplazar el bloque `if (loading)`:

```jsx
if (loading) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
      {[...Array(12)].map((_, i) => (
        <div key={i} className="rounded-xl overflow-hidden bg-dark-card">
          <div className="aspect-[2/3] skeleton-shimmer" />
          <div className="p-4 space-y-2">
            <div className="h-4 skeleton-shimmer rounded w-3/4" />
            <div className="h-3 skeleton-shimmer rounded w-1/2" />
            <div className="h-3 skeleton-shimmer rounded w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3.2: Verificar build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3.3: Commit**

```bash
git add frontend/src/components/ContentGrid.jsx
git commit -m "feat: shimmer skeleton loader in ContentGrid"
```

---

## Task 4: Navbar — Logo, active state, separador

**Files:**
- Modify: `frontend/src/components/Navbar.jsx`

- [ ] **Step 4.1: Reemplazar logo emoji por logo tipográfico**

En `frontend/src/components/Navbar.jsx`, reemplazar el bloque del logo:

```jsx
{/* Logo */}
<Link to={isAdmin ? '/admin/users' : '/'} className="flex items-center gap-3">
  <div className="w-8 h-8 bg-gradient-to-br from-gold to-gold-light rounded-lg flex items-center justify-center flex-shrink-0">
    <span className="font-serif font-black text-dark-base text-lg leading-none">A</span>
  </div>
  <div>
    <h1 className="font-serif text-lg font-bold text-white leading-tight">Alejandría</h1>
    <p className="text-[10px] text-gray-500 leading-tight">
      {isAdmin ? 'Administración' : 'Tu biblioteca digital'}
    </p>
  </div>
</Link>
```

- [ ] **Step 4.2: Actualizar función navLinkClass para estado activo dorado**

Reemplazar la función `navLinkClass`:

```jsx
const navLinkClass = ({ isActive }) =>
  `flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${
    isActive
      ? 'bg-gold/10 border border-gold/25 text-gold font-semibold'
      : 'text-gray-400 hover:text-white hover:bg-dark-lighter border border-transparent'
  }`;
```

- [ ] **Step 4.3: Mostrar texto de nav siempre en desktop (quitar lg:inline)**

En los `<NavLink>` del desktop, cambiar `hidden lg:inline` por `hidden md:inline`:

```jsx
<span className="hidden md:inline">{item.label}</span>
```

(Buscar todas las ocurrencias de `hidden lg:inline` en el componente y cambiar a `hidden md:inline`.)

- [ ] **Step 4.4: Añadir separador dorado inferior a la navbar**

Al final del `<nav>`, justo antes del cierre `</nav>`, añadir:

```jsx
{/* Gold accent line */}
<div className="h-px bg-gradient-to-r from-transparent via-gold/20 to-transparent" />
```

- [ ] **Step 4.5: Actualizar estado activo del menú móvil**

En el menú móvil, reemplazar la clase del item activo de `bg-primary text-white` por `bg-gold/10 border-l-2 border-gold text-gold`:

```jsx
className={isLibraryActive
  ? `flex items-center gap-3 px-3 py-3 rounded-lg transition-colors bg-gold/10 border-l-2 border-gold text-gold`
  : ({ isActive }) =>
      `flex items-center gap-3 px-3 py-3 rounded-lg transition-colors ${
        isActive ? 'bg-gold/10 border-l-2 border-gold text-gold' : 'text-gray-400 hover:text-white hover:bg-dark-lighter'
      }`
}
```

- [ ] **Step 4.6: Actualizar admin NavLink a dorado**

Reemplazar `bg-purple-600` por `bg-gold/10 border border-gold/25 text-gold` en el NavLink del admin.

- [ ] **Step 4.7: Verificar build**

```bash
cd frontend && npm run build
```

- [ ] **Step 4.8: Commit**

```bash
git add frontend/src/components/Navbar.jsx
git commit -m "feat: navbar — logo tipográfico A dorado, active state gold, separador inferior"
```

---

## Task 5: ContentCard — Tipografía, colores por tipo, sombra, hover

**Files:**
- Modify: `frontend/src/components/ContentCard.jsx`

- [ ] **Step 5.1: Actualizar config de colores por tipo**

En `frontend/src/components/ContentCard.jsx`, reemplazar el objeto `config` con los nuevos valores de color. Localizar el bloque que empieza con `const config = {` y reemplazarlo:

```jsx
const config = {
  manga: {
    accentColor: item.cover_color || '#6b9bd2',
    icon: FaBook,
    hoverTextClass: 'group-hover:text-manga',
    badgeClass: 'bg-manga',
    typeTextClass: 'text-manga',
    typeBgClass: 'bg-manga/10 border border-manga/20',
    addBtnClass: 'btn btn-primary',
    progressGradient: 'from-manga to-manga/60',
    borderTopColor: item.cover_color || '#6b9bd2',
    detailPath: '/manga',
    getLink: () => {
      const id = item.library_id || (item.id && item.id > 0 ? item.id : null);
      return id ? `/manga/${id}` : null;
    },
    getCover: () => item.cover_image || item.cover,
    getScore: () => item.average_score ? (item.average_score / 10).toFixed(1) : null,
    getSubInfo: () => item.genres?.slice(0, 3).map(g => ({ key: g, label: g })) || [],
    getStats: () => {
      const parts = [];
      if (item.average_score) parts.push({ type: 'score', value: (item.average_score / 10).toFixed(1) });
      if (item.chapters_total) parts.push({ type: 'count', label: `${item.chapters_total} tomos` });
      if (item.format) parts.push({ type: 'text', label: item.format });
      return parts;
    },
    getProgress: () => ({
      current: item.downloaded_chapters || 0,
      total: item.chapters_total || 0,
      show: item.in_library && item.downloaded_chapters !== undefined,
    }),
    getStatusBadge: () => item.status ? {
      label: item.status,
      className: item.status === 'RELEASING' ? 'bg-manga/20 text-manga border border-manga/30' : item.status === 'FINISHED' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'bg-gray-500/20 text-gray-400',
    } : null,
  },
  comic: {
    accentColor: '#c07a5a',
    icon: FaMask,
    hoverTextClass: 'group-hover:text-comic',
    badgeClass: 'bg-comic',
    typeTextClass: 'text-comic',
    typeBgClass: 'bg-comic/10 border border-comic/20',
    addBtnClass: 'btn bg-comic hover:bg-comic/80 text-white',
    progressGradient: 'from-comic to-comic/60',
    borderTopColor: '#c07a5a',
    detailPath: '/comics',
    getLink: () => {
      const id = item.library_id || item.id;
      return id ? `/comics/${id}` : null;
    },
    getCover: () => item.cover_image,
    getScore: () => null,
    getSubInfo: () => {
      const parts = [];
      if (item.publisher) parts.push({ key: 'pub', label: item.publisher });
      if (item.start_year) parts.push({ key: 'year', label: `${item.start_year}` });
      return parts;
    },
    getStats: () => {
      const total = item.count_of_issues || item.total_issues || '?';
      return [{ type: 'count', label: `${item.downloaded_issues || 0}/${total} issues`, className: 'text-comic' }];
    },
    getProgress: () => ({
      current: item.downloaded_issues || 0,
      total: item.count_of_issues || item.total_issues || 0,
      show: item.in_library && (item.count_of_issues || item.total_issues) > 0,
    }),
    getStatusBadge: () => item.downloaded_issues > 0 ? { label: 'Descargado', className: 'bg-comic/20 text-comic border border-comic/30' } : null,
  },
  book: {
    accentColor: '#7aa67a',
    icon: FaBookReader,
    hoverTextClass: 'group-hover:text-book',
    badgeClass: 'bg-book',
    typeTextClass: 'text-book',
    typeBgClass: 'bg-book/10 border border-book/20',
    addBtnClass: 'btn btn-primary',
    progressGradient: 'from-book to-book/60',
    borderTopColor: '#7aa67a',
    detailPath: '/books',
    getLink: () => {
      const id = item.library_id || item.id;
      return id ? `/books/${id}` : null;
    },
    getCover: () => item.cover_image || item.thumbnail,
    getScore: () => item.average_rating ? item.average_rating.toFixed(1) : null,
    getSubInfo: () => item.authors?.slice(0, 2).map((a, i) => ({ key: i, label: a })) || [],
    getStats: () => {
      const parts = [];
      if (item.average_rating) parts.push({ type: 'score', value: item.average_rating.toFixed(1) });
      if (item.page_count) parts.push({ type: 'count', label: `${item.page_count}p` });
      if (item.language) parts.push({ type: 'text', label: item.language.toUpperCase() });
      return parts;
    },
    getProgress: () => ({
      current: item.downloaded_chapters || 0,
      total: item.total_chapters || 0,
      show: item.in_library && item.total_chapters > 0,
    }),
    getStatusBadge: () => item.downloaded_chapters > 0 ? { label: 'Descargado', className: 'bg-book/20 text-book border border-book/30' } : null,
  },
};
```

- [ ] **Step 5.2: Actualizar CardContent — borde superior, sombra, hover**

Localizar el `<div>` raíz de `CardContent` y actualizar:

```jsx
const CardContent = () => (
  <div
    className="card group cursor-pointer transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_12px_40px_rgba(0,0,0,0.6)] relative"
    onMouseEnter={() => setIsHovered(true)}
    onMouseLeave={() => setIsHovered(false)}
    style={{ borderTop: `2px solid ${c.borderTopColor}` }}
  >
```

- [ ] **Step 5.3: Actualizar título a font-serif**

Localizar el `<h3>` del título y cambiar:

```jsx
<h3 className={`font-serif font-bold text-lg mb-1 line-clamp-2 ${c.hoverTextClass} transition-colors`}>
  {item.title}
</h3>
```

- [ ] **Step 5.4: Añadir subtítulo de autor/tipo debajo del título**

Justo después del `<h3>`, añadir:

```jsx
{/* Autor o tipo como subtítulo */}
{subInfo.length > 0 && (
  <p className={`text-xs font-semibold uppercase tracking-wider mb-2 ${c.typeTextClass}`}>
    {subInfo[0].label}
  </p>
)}
```

Y eliminar el bloque de `subInfo` completo que viene después (el `{subInfo.length > 0 && (...)}`).

- [ ] **Step 5.5: Actualizar badges de género restantes**

Si `subInfo.length > 1`, mostrar los géneros adicionales como pills. Añadir después del subtítulo:

```jsx
{subInfo.length > 1 && (
  <div className="flex flex-wrap gap-1 mb-2">
    {subInfo.slice(1).map((info) => (
      <span
        key={info.key}
        className={`text-[10px] px-2 py-0.5 rounded ${c.typeBgClass} ${c.typeTextClass}`}
      >
        {info.label}
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 5.6: Actualizar rating a color dorado**

Localizar el bloque de score en el stats row y actualizar:

```jsx
if (stat.type === 'score') {
  return (
    <div key={i} className="flex items-center gap-1">
      <FaStar className="text-gold text-xs" />
      <span className="text-gold font-semibold text-sm">{stat.value}</span>
    </div>
  );
}
```

- [ ] **Step 5.7: Actualizar barra de progreso a degradado**

Localizar el bloque de progress bar y actualizar:

```jsx
{progress.show && progress.total > 0 && (
  <div className="mt-2">
    <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1 font-light">
      <span>{progress.current} de {progress.total}</span>
      <span>{Math.round((progress.current / progress.total) * 100)}%</span>
    </div>
    <div className="w-full bg-dark-base rounded-full h-[3px]">
      <div
        className={`bg-gradient-to-r ${c.progressGradient} h-[3px] rounded-full transition-all`}
        style={{ width: `${(progress.current / progress.total) * 100}%` }}
      />
    </div>
  </div>
)}
```

- [ ] **Step 5.8: Verificar build**

```bash
cd frontend && npm run build
```

Si hay error por clases dinámicas de Tailwind (ej: `bg-manga/10` no generada), añadir safelist en tailwind.config.js:

```js
safelist: [
  { pattern: /bg-(manga|comic|book)(\/\d+)?/ },
  { pattern: /text-(manga|comic|book)/ },
  { pattern: /border-(manga|comic|book)(\/\d+)?/ },
  { pattern: /from-(manga|comic|book)/ },
],
```

- [ ] **Step 5.9: Commit**

```bash
git add frontend/src/components/ContentCard.jsx frontend/tailwind.config.js
git commit -m "feat: ContentCard — font-serif, type colors, gold rating, gradient progress bar"
```

---

## Task 6: ContentDetailPage — Banner, título serif, genres, stats row, actions

**Files:**
- Modify: `frontend/src/components/ContentDetailPage.jsx`

- [ ] **Step 6.1: Mejorar banner y añadir overlay cinematográfico**

Localizar el bloque del banner (empieza en `{coverImage && (`) y reemplazarlo:

```jsx
{/* Banner */}
<div className="w-full h-56 relative overflow-hidden">
  {bannerImage ? (
    <div
      className="absolute inset-0 bg-cover bg-center"
      style={{ backgroundImage: `url(${sanitizeUrl(bannerImage)})` }}
    />
  ) : coverImage ? (
    <div
      className="absolute inset-0 bg-cover bg-center"
      style={{
        backgroundImage: `url(${sanitizeUrl(coverImage)})`,
        filter: 'blur(12px)',
        transform: 'scale(1.15)',
      }}
    />
  ) : (
    <div className="absolute inset-0 bg-gradient-to-br from-dark-card to-dark" />
  )}
  {/* Dark overlay */}
  <div className="absolute inset-0 bg-gradient-to-b from-dark-base/30 via-dark/60 to-dark" />
  {/* Bottom gradient */}
  <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-dark to-transparent" />
</div>
```

- [ ] **Step 6.2: Actualizar título h1 a font-serif**

Localizar `<h1 className="text-4xl font-bold mb-2">` y cambiar a:

```jsx
<h1 className="font-serif text-4xl font-bold mb-2 text-white/95">{title}</h1>
```

- [ ] **Step 6.3: Actualizar estilo de genres/pills**

Localizar el bloque de genres y reemplazarlo:

```jsx
{genres.length > 0 && (
  <div className="flex flex-wrap gap-2 mb-6">
    {genres.map((genre, i) => (
      <span
        key={i}
        className="px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wide border"
        style={{
          backgroundColor: `${accentColor}18`,
          color: accentColor,
          borderColor: `${accentColor}35`,
        }}
      >
        {genre}
      </span>
    ))}
  </div>
)}
```

- [ ] **Step 6.4: Actualizar score a color dorado**

Localizar el bloque del score y cambiar:

```jsx
{score != null && (
  <div className="flex items-center gap-2">
    <FaStar className="text-gold" />
    <span className="font-bold text-gold">
      {typeof score === 'number' && scoreMax > 10
        ? (score / (scoreMax / 10)).toFixed(1)
        : typeof score === 'number'
          ? score.toFixed(1)
          : score}
    </span>
  </div>
)}
```

- [ ] **Step 6.5: Mejorar stats cards**

Localizar el bloque de stats (`{stats.length > 0 && (`) y reemplazarlo:

```jsx
{stats.length > 0 && (
  <div className="mt-8">
    <div className="flex flex-wrap gap-4 bg-dark-card rounded-xl p-5 border border-white/5">
      {stats.map((stat, i) => (
        <div key={i} className="flex-1 min-w-[80px] text-center">
          <p
            className="text-2xl font-bold mb-1"
            style={{ color: stat.color || '#f8f4ef' }}
          >
            {stat.value}
          </p>
          <p className="text-xs text-gray-500 uppercase tracking-widest font-light">{stat.label}</p>
        </div>
      ))}
    </div>
  </div>
)}
```

- [ ] **Step 6.6: Aplicar btn-primary y btn-secondary al primer action**

Localizar el bloque de actions y actualizar para que el primer action sea dorado por defecto si no tiene className:

```jsx
{actions.length > 0 && (
  <div className="flex flex-wrap gap-3 mt-2">
    {actions.map((action, i) => (
      <div key={i} className="relative group">
        <button
          onClick={action.onClick}
          disabled={action.disabled}
          className={action.className || (i === 0 ? 'btn btn-primary flex items-center gap-2' : 'btn btn-secondary flex items-center gap-2')}
          title={action.title}
        >
          {action.icon && action.icon}
          {action.label}
        </button>
        {action.tooltip && (
          <div className="absolute bottom-full left-0 mb-2 hidden group-hover:block bg-dark-lighter text-sm text-gray-300 p-2 rounded shadow-lg w-64 z-10">
            {action.tooltip}
          </div>
        )}
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 6.7: Mejorar loading skeleton**

Reemplazar el bloque de loading:

```jsx
if (loading) {
  return (
    <div className="min-h-screen">
      <div className="h-56 skeleton-shimmer" />
      <div className="container mx-auto px-4 py-8 space-y-4">
        <div className="h-10 skeleton-shimmer rounded w-1/2" />
        <div className="h-5 skeleton-shimmer rounded w-1/3" />
        <div className="h-4 skeleton-shimmer rounded w-3/4" />
        <div className="h-4 skeleton-shimmer rounded w-2/3" />
      </div>
    </div>
  );
}
```

- [ ] **Step 6.8: Verificar build**

```bash
cd frontend && npm run build
```

- [ ] **Step 6.9: Commit**

```bash
git add frontend/src/components/ContentDetailPage.jsx
git commit -m "feat: ContentDetailPage — banner cinematográfico, font-serif, gold score, stats mejoradas"
```

---

## Task 7: Discover — Hero section, pills, eliminar RecommendationCard

**Files:**
- Modify: `frontend/src/pages/Discover.jsx`

- [ ] **Step 7.1: Añadir función adaptadora para ContentCard**

Al inicio del componente `Discover` (después de los imports), añadir la función adaptadora:

```jsx
// Adapta un objeto recommendation al shape que espera ContentCard
const adaptRecToItem = (rec) => ({
  id: rec.anilist_id || rec.google_books_id || rec.external_id,
  library_id: null,
  title: rec.title,
  cover_image: rec.cover,
  cover: rec.cover,
  description: rec.reason_label || '',
  average_score: rec.score,
  average_rating: rec.score,
  authors: rec.authors || [],
  genres: rec.genres || [],
  in_library: false,
  reading_status: 'not_started',
  anilist_id: rec.anilist_id,
  google_books_id: rec.google_books_id,
});
```

- [ ] **Step 7.2: Añadir import de ContentCard**

Añadir al inicio del archivo:

```jsx
import ContentCard from '../components/ContentCard';
```

- [ ] **Step 7.3: Reemplazar RecommendationCard y SkeletonCard**

Eliminar completamente los componentes `RecommendationCard` y `SkeletonCard` del archivo, y reemplazar en el JSX del grid:

```jsx
{/* Grid */}
<div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
  {loading
    ? Array.from({ length: 10 }).map((_, i) => (
        <div key={i} className="rounded-xl overflow-hidden bg-dark-card">
          <div className="aspect-[2/3] skeleton-shimmer" />
          <div className="p-4 space-y-2">
            <div className="h-4 skeleton-shimmer rounded w-3/4" />
            <div className="h-3 skeleton-shimmer rounded w-1/2" />
            <div className="h-8 skeleton-shimmer rounded mt-3" />
          </div>
        </div>
      ))
    : recommendations.map((rec, i) => (
        <ContentCard
          key={`${rec.content_type}-${rec.external_id || i}`}
          item={adaptRecToItem(rec)}
          type={rec.content_type === 'comic' ? 'comic' : rec.content_type === 'book' ? 'book' : 'manga'}
          showAddButton={!addedIds.has(rec.external_id)}
          onAdd={() => handleAdd(rec)}
        />
      ))}
</div>
```

- [ ] **Step 7.4: Reemplazar header por hero section**

Localizar el bloque `{/* Header */}` y reemplazarlo:

```jsx
{/* Hero section */}
<div className="bg-dark-card rounded-xl px-6 py-5 mb-6 border border-white/5 relative overflow-hidden">
  <div className="absolute inset-0 bg-gradient-to-r from-transparent to-gold/3 pointer-events-none" />
  <div className="relative">
    <p className="text-[10px] font-semibold text-gold uppercase tracking-[3px] mb-1">
      Recomendado para ti
    </p>
    <h1 className="font-serif text-3xl font-bold mb-1">Descubrir</h1>
    <p className="text-gray-500 text-sm mb-4">
      {usingFallback ? 'Tendencias de AniList' : 'Basado en tu biblioteca'}
      {!loading && recommendations.length > 0 && ` · ${recommendations.length} sugerencias`}
    </p>
    <div className="flex items-center gap-2 flex-wrap">
      {/* Type filter — pills */}
      <div className="flex gap-2">
        {typeFilters.map((f) => (
          <button
            key={f.value}
            onClick={() => setTypeFilter(f.value)}
            className={`px-4 py-1.5 rounded-full text-xs font-semibold transition-colors border ${
              typeFilter === f.value
                ? 'bg-gold/15 border-gold/30 text-gold'
                : 'bg-transparent border-white/10 text-gray-500 hover:text-white hover:border-white/20'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      <button
        onClick={loadRecommendations}
        className="ml-auto text-gray-500 hover:text-white p-1.5 rounded-lg hover:bg-dark-lighter transition-colors"
        title="Actualizar recomendaciones"
      >
        <FaSync className={`text-sm ${loading ? 'animate-spin' : ''}`} />
      </button>
    </div>
  </div>
</div>
```

- [ ] **Step 7.5: Verificar build**

```bash
cd frontend && npm run build
```

- [ ] **Step 7.6: Commit**

```bash
git add frontend/src/pages/Discover.jsx
git commit -m "feat: Discover — hero section, filter pills, unify con ContentCard"
```

---

## Task 8: Queue — Miniaturas, react-icons, progress bar, bordes por estado

**Files:**
- Modify: `frontend/src/pages/Queue.jsx`

- [ ] **Step 8.1: Actualizar imports — añadir FiIcons y quitar los no usados**

En `frontend/src/pages/Queue.jsx`, añadir imports de react-icons/fi:

```jsx
import {
  FiClock,
  FiDownload,
  FiCheckCircle,
  FiAlertCircle,
  FiSettings,
  FiSend,
  FiRefreshCw,
} from 'react-icons/fi';
```

- [ ] **Step 8.2: Reemplazar ACTIVITY_ICONS con react-icons**

Localizar `const ACTIVITY_ICONS` y reemplazar:

```jsx
const ACTIVITY_ICONS = {
  queued:      { Icon: FiClock,        colorClass: 'text-gray-400' },
  downloading: { Icon: FiDownload,     colorClass: 'text-manga' },
  completed:   { Icon: FiCheckCircle,  colorClass: 'text-book' },
  failed:      { Icon: FiAlertCircle,  colorClass: 'text-red-400' },
  converting:  { Icon: FiSettings,     colorClass: 'text-purple-400' },
  sent_kindle: { Icon: FiSend,         colorClass: 'text-gold' },
};
```

- [ ] **Step 8.3: Actualizar renderizado de cada item de cola**

Buscar en el JSX dónde se renderizan los items de la cola (buscar `item.status` o el mapeo del array `queue`). Actualizar el item para incluir miniatura, tipografía serif en el título, y bordes de color por estado.

En el componente de cada item de la cola, buscar el bloque que renderiza un item individual y actualizarlo. La estructura típica es un `div` con la info del item. Reemplazar para incluir:

```jsx
// Dentro del map de items de cola — buscar el JSX que renderiza cada queue item
// Añadir miniatura a la izquierda:
<div
  className={`bg-dark-card rounded-xl p-3 flex items-center gap-3 border transition-colors ${
    item.status === 'downloading' ? 'border-manga/25' :
    item.status === 'completed'   ? 'border-book/25' :
    item.status === 'failed'      ? 'border-red-500/25' :
    item.status === 'converting'  ? 'border-purple-500/25' :
    item.status === 'sent_kindle' ? 'border-gold/25' :
    'border-white/5'
  }`}
>
  {/* Miniatura */}
  {item.cover ? (
    <img
      src={item.cover}
      alt=""
      className="w-9 h-12 object-cover rounded flex-shrink-0"
      loading="lazy"
    />
  ) : (
    <div className="w-9 h-12 bg-dark-lighter rounded flex-shrink-0 flex items-center justify-center">
      <FiDownload className="text-gray-600 text-xs" />
    </div>
  )}
  {/* Info */}
  <div className="flex-1 min-w-0">
    <p className="font-serif text-sm text-white truncate">{item.title || item.chapter_title}</p>
    <p className={`text-xs font-semibold uppercase tracking-wide ${ITEM_TYPE_COLORS[item.content_type] || 'text-gray-400'}`}>
      {item.content_type}
      {item.status && ` · ${item.status}`}
    </p>
    {/* Barra de progreso si descargando */}
    {item.status === 'downloading' && (
      <div className="mt-1 h-[3px] bg-dark-base rounded-full overflow-hidden">
        <div className="h-full bg-gradient-to-r from-manga to-manga/60 rounded-full w-1/2 animate-pulse" />
      </div>
    )}
  </div>
</div>
```

**Nota:** La estructura exacta del map de items depende de cómo Queue.jsx organiza la lista filtrada. Buscar el `queue.filter(...)` y el `map` subsiguiente para encontrar el punto exacto de renderizado.

- [ ] **Step 8.4: Actualizar ACTIVITY_ICONS en el log de actividad**

En el log de actividad, el renderizado usa `ACTIVITY_ICONS[status].icon` (emoji). Actualizar para usar el `Icon` (componente):

```jsx
// Buscar donde se usa ACTIVITY_ICONS en el JSX del log de actividad
// Cambiar de: {ACTIVITY_ICONS[item.status]?.icon}
// A:
{(() => {
  const cfg = ACTIVITY_ICONS[item.status];
  if (!cfg) return null;
  const { Icon, colorClass } = cfg;
  return <Icon className={`${colorClass} text-sm flex-shrink-0`} />;
})()}
```

- [ ] **Step 8.5: Verificar build**

```bash
cd frontend && npm run build
```

- [ ] **Step 8.6: Commit**

```bash
git add frontend/src/pages/Queue.jsx
git commit -m "feat: Queue — miniaturas, react-icons, barra progreso, bordes por estado"
```

---

## Task 9: Search — Unificar tarjetas de resultado con ContentCard

**Files:**
- Modify: `frontend/src/pages/Search.jsx`

- [ ] **Step 9.1: Identificar las tarjetas custom de resultado**

En `frontend/src/pages/Search.jsx`, buscar el JSX de renderizado de resultados (buscar `results.map`). Actualmente hay tarjetas custom por tipo.

- [ ] **Step 9.2: Añadir función adaptadora por tipo**

Añadir antes del return del componente `Search`:

```jsx
// Adapta un resultado de búsqueda al shape de ContentCard
const adaptSearchResult = (item, tab) => {
  if (tab === 'manga') {
    return {
      ...item,
      cover_image: item.cover_image || item.cover,
      in_library: !!item.library_id,
    };
  }
  if (tab === 'comics') {
    return {
      ...item,
      cover_image: item.cover_image,
      in_library: !!item.library_id,
    };
  }
  // books
  return {
    ...item,
    cover_image: item.cover_image || item.thumbnail,
    in_library: !!item.library_id,
  };
};
```

- [ ] **Step 9.3: Reemplazar tarjetas custom por ContentCard**

Localizar el bloque de renderizado de `results` y reemplazarlo:

```jsx
{/* Resultados */}
{hasSearched && !loading && results.length === 0 && (
  <div className="text-center py-16 text-gray-500">
    <FaSearch className="text-4xl mx-auto mb-3 opacity-20" />
    <p>No se encontraron resultados para "{lastQuery}"</p>
  </div>
)}

{results.length > 0 && (
  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
    {results.map((item, i) => {
      const type = activeTab === 'manga' ? 'manga' : activeTab === 'comics' ? 'comic' : 'book';
      const adapted = adaptSearchResult(item, activeTab);
      const onAdd = activeTab === 'manga' ? handleAddManga
                  : activeTab === 'comics' ? handleAddComic
                  : handleAddBook;
      return (
        <ContentCard
          key={item.anilist_id || item.comicvine_id || item.google_books_id || item.source_url || i}
          item={adapted}
          type={type}
          showAddButton={!adapted.in_library}
          onAdd={onAdd}
        />
      );
    })}
  </div>
)}
```

- [ ] **Step 9.4: Actualizar tabs de búsqueda al nuevo estilo**

Localizar los botones de tabs (Manga / Cómics / Libros) y actualizar su estilo activo:

```jsx
<button
  onClick={() => { setActiveTab(tab.value); if (lastQuery) handleSearch(lastQuery, tab.value); }}
  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors border ${
    activeTab === tab.value
      ? 'bg-gold/10 border-gold/25 text-gold'
      : 'border-transparent text-gray-400 hover:text-white hover:bg-dark-lighter'
  }`}
>
```

- [ ] **Step 9.5: Verificar build**

```bash
cd frontend && npm run build
```

- [ ] **Step 9.6: Commit**

```bash
git add frontend/src/pages/Search.jsx
git commit -m "feat: Search — unificar resultados con ContentCard, tabs dorados"
```

---

## Task 10: Home — Stats cards con nuevos tokens

**Files:**
- Modify: `frontend/src/pages/Home.jsx`

- [ ] **Step 10.1: Actualizar stats cards de biblioteca**

En `frontend/src/pages/Home.jsx`, localizar el grid de stats cards (donde se usan `TYPE_CONFIG`) y mejorar:

```jsx
<button
  key={type}
  onClick={() => navigate(cfg.path)}
  className="bg-dark-card rounded-xl p-4 text-left hover:ring-1 hover:ring-gold/20 transition-all border border-white/5"
>
  <div className="flex items-center gap-3">
    <div className={`w-10 h-10 rounded-lg ${cfg.bg} flex items-center justify-center`}>
      <Icon className={`${cfg.color} text-lg`} />
    </div>
    <div>
      <p className="font-serif text-2xl font-bold">{count}</p>
      <p className="text-xs text-gray-500 uppercase tracking-wide">{cfg.label}</p>
    </div>
  </div>
</button>
```

- [ ] **Step 10.2: Actualizar secciones h2 a font-serif**

Localizar todos los `<h2>` de Home.jsx y añadir `font-serif`:

```jsx
<h2 className="font-serif text-xl font-semibold mb-4 text-gray-200">Mi Biblioteca</h2>
// ... repetir para "Almacenamiento" y "Enviados a Kindle"
```

- [ ] **Step 10.3: Verificar build final**

```bash
cd frontend && npm run build
```

Esperado: build limpio sin warnings de Tailwind ni errores de React.

- [ ] **Step 10.4: Verificar app en navegador**

```bash
cd frontend && npm run dev
```

Abrir `http://localhost:5173` y verificar:
- [ ] Navbar muestra logo `A` dorado
- [ ] Nav activo tiene fondo ámbar, no azul
- [ ] Discover muestra hero section con filtros pill
- [ ] ContentCards tienen título en Playfair Display
- [ ] Rating es dorado
- [ ] Tarjetas tienen más profundidad (fondo distinto al body)
- [ ] Transición suave al navegar entre páginas

- [ ] **Step 10.5: Commit final**

```bash
git add frontend/src/pages/Home.jsx
git commit -m "feat: Home — stats cards con font-serif y hover dorado"
```

---

## Self-review checklist

- [x] **Spec coverage:** Tokens ✓ · Navbar ✓ · ContentCard ✓ · ContentDetailPage ✓ · Discover ✓ · Queue ✓ · Search ✓ · Home ✓ · Transiciones ✓ · Skeleton shimmer ✓ · Unificación RecommendationCard ✓ · Iconos Queue ✓ · Toaster ✓
- [x] **Placeholders:** ningún TBD ni "implementar después"
- [x] **Tipos consistentes:** `adaptRecToItem` devuelve shape compatible con ContentCard props. `adaptSearchResult` mantiene los campos que usan `handleAddManga/Comic/Book`. `ACTIVITY_ICONS` usa `{ Icon, colorClass }` consistentemente en tasks 8.2 y 8.4.
- [x] **Safelist Tailwind:** incluida en Task 5.8 para clases dinámicas `bg-manga/comic/book`
- [x] **Orden de tasks:** tokens → app shell → componentes base → páginas. Cada task produce un commit funcional independiente.
