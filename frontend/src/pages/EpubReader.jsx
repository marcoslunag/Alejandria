import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import ePub from 'epubjs';
import { bookApi, api } from '../services/api';
import {
  FaArrowLeft,
  FaChevronLeft,
  FaChevronRight,
  FaSun,
  FaMoon,
  FaBookReader,
  FaSpinner,
} from 'react-icons/fa';

// Tema del reader (independiente del tema de la app) — roadmap #8
const READER_THEMES = {
  light: { background: '#ffffff', color: '#26221c' },
  dark: { background: '#121118', color: '#e5e1d8' },
  sepia: { background: '#f4ecd8', color: '#5b4636' },
};

const FONT_MIN = 12;
const FONT_MAX = 30;

const EpubReader = () => {
  const { id: bookId, chapterId } = useParams();
  const containerRef = useRef(null);
  const bookRef = useRef(null);
  const renditionRef = useRef(null);
  const markReadSentRef = useRef(false);
  const uiTimeoutRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [bookTitle, setBookTitle] = useState('Libro');
  const [chapterLabel, setChapterLabel] = useState('');
  const [progress, setProgress] = useState(0);
  const [showUI, setShowUI] = useState(true);
  const [fontSize, setFontSize] = useState(() => {
    const v = parseInt(localStorage.getItem('epub-font-size'), 10);
    return v >= FONT_MIN && v <= FONT_MAX ? v : 18;
  });
  const [theme, setTheme] = useState(() => {
    const v = localStorage.getItem('epub-theme');
    return v && READER_THEMES[v] ? v : 'light';
  });

  const applySettings = useCallback((rendition, size, th) => {
    const t = READER_THEMES[th] || READER_THEMES.light;
    rendition.themes.register('alejandria', {
      body: {
        background: t.background,
        color: t.color,
        margin: '0',
        'line-height': '1.7',
      },
      p: { 'text-indent': '1em' },
      h1: { 'text-align': 'center', 'text-indent': '0' },
      h2: { 'text-align': 'center', 'text-indent': '0' },
      h3: { 'text-align': 'center', 'text-indent': '0' },
      h4: { 'text-align': 'center', 'text-indent': '0' },
    });
    rendition.themes.select('alejandria');
    rendition.themes.fontSize(`${size}px`);
  }, []);

  // Carga del EPUB (una vez por libro/capítulo)
  useEffect(() => {
    let disposed = false;
    markReadSentRef.current = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        setProgress(0);

        // Metadatos para la barra (no bloquean la carga del archivo)
        const [bookResp, chResp] = await Promise.all([
          bookApi.getBook(bookId).catch(() => null),
          bookApi.getChapters(bookId).catch(() => null),
        ]);
        if (disposed) return;
        const ch = (chResp?.data || []).find(c => c.id === Number(chapterId));
        setBookTitle(bookResp?.data?.title || 'Libro');
        setChapterLabel(ch ? (ch.title || `Volumen ${ch.number}`) : '');

        // Fetch del EPUB con header Bearer (axios) → ArrayBuffer → epub.js
        const { data } = await api.get(
          `/books/${bookId}/chapters/${chapterId}/epub`,
          { responseType: 'arraybuffer' }
        );
        if (disposed) return;

        const book = ePub(data);
        bookRef.current = book;
        const rendition = book.renderTo(containerRef.current, {
          width: '100%',
          height: '100%',
          flow: 'paginated',
          allowScriptedContent: false,
        });
        renditionRef.current = rendition;

        rendition.on('relocated', (location) => {
          const pct = location?.start?.percentAfter != null
            ? Math.round(location.start.percentAfter * 100)
            : 0;
          setProgress(pct);
          // Marcar leído al llegar al final (una sola vez)
          if (location?.start?.percentAfter >= 0.98 && !markReadSentRef.current) {
            markReadSentRef.current = true;
            bookApi.markChapterRead(bookId, chapterId).catch(() => {});
          }
        });

        applySettings(rendition, fontSize, theme);
        await rendition.display();
        if (!disposed) setLoading(false);
      } catch (err) {
        if (disposed) return;
        console.error('Error cargando EPUB:', err);
        setError(
          err.response?.status === 404
            ? 'El EPUB todavía no está descargado en el servidor.'
            : 'Error al cargar el EPUB. Inténtalo de nuevo.'
        );
        setLoading(false);
      }
    };

    load();
    return () => {
      disposed = true;
      bookRef.current?.destroy();
      bookRef.current = null;
      renditionRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId, chapterId]);

  // Persistir y aplicar cambios de tamaño de fuente
  useEffect(() => {
    localStorage.setItem('epub-font-size', String(fontSize));
    renditionRef.current?.themes.fontSize(`${fontSize}px`);
  }, [fontSize]);

  // Persistir y aplicar cambios de tema
  useEffect(() => {
    localStorage.setItem('epub-theme', theme);
    if (renditionRef.current) {
      const t = READER_THEMES[theme] || READER_THEMES.light;
      renditionRef.current.themes.register('alejandria', {
        body: { background: t.background, color: t.color, margin: '0', 'line-height': '1.7' },
        p: { 'text-indent': '1em' },
        h1: { 'text-align': 'center' },
        h2: { 'text-align': 'center' },
        h3: { 'text-align': 'center' },
        h4: { 'text-align': 'center' },
      });
      renditionRef.current.themes.select('alejandria');
    }
  }, [theme]);

  const next = useCallback(() => renditionRef.current?.next(), []);
  const prev = useCallback(() => renditionRef.current?.prev(), []);

  // Auto-ocultar UI al leer (misma sensación que el reader de manga)
  const pokeUI = useCallback(() => {
    setShowUI(true);
    if (uiTimeoutRef.current) clearTimeout(uiTimeoutRef.current);
    uiTimeoutRef.current = setTimeout(() => setShowUI(false), 3000);
  }, []);

  useEffect(() => {
    pokeUI();
    return () => {
      if (uiTimeoutRef.current) clearTimeout(uiTimeoutRef.current);
    };
  }, [pokeUI]);

  // Navegación con teclado
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {
        e.preventDefault();
        next();
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault();
        prev();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [next, prev]);

  const themeBtn = (key, Icon, label) => (
    <button
      key={key}
      onClick={() => setTheme(key)}
      title={label}
      className={`p-2 rounded-lg transition-colors ${
        theme === key
          ? 'bg-primary text-dark'
          : 'bg-dark-lighter text-gray-400 hover:text-white'
      }`}
    >
      <Icon />
    </button>
  );

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-dark-base">
        <div className="text-center">
          <FaSpinner className="text-4xl text-primary animate-spin mb-4" />
          <p className="text-gray-400">Cargando EPUB...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-dark-base">
        <div className="card p-8 text-center max-w-md">
          <p className="text-red-400 mb-4">{error}</p>
          <Link
            to={`/books/${bookId}`}
            className="btn btn-secondary inline-flex items-center gap-2"
          >
            <FaArrowLeft />
            Volver al libro
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col"
      style={{ background: (READER_THEMES[theme] || READER_THEMES.light).background }}
      onMouseMove={pokeUI}
      onClick={pokeUI}
    >
      {/* Barra superior */}
      <div
        className={`flex items-center gap-3 px-4 py-3 transition-opacity duration-300 ${
          showUI ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        style={{
          background: 'linear-gradient(to bottom, rgba(0,0,0,0.55), transparent)',
        }}
      >
        <Link
          to={`/books/${bookId}`}
          className="p-2 rounded-lg bg-black/30 text-white hover:bg-black/50 transition-colors"
          title="Volver"
        >
          <FaArrowLeft />
        </Link>
        <div className="flex-1 min-w-0">
          <p className="text-white font-medium truncate">{bookTitle}</p>
          {chapterLabel && <p className="text-white/70 text-xs truncate">{chapterLabel}</p>}
        </div>
        <span className="text-white/80 text-sm tabular-nums">{progress}%</span>
      </div>

      {/* Área de lectura */}
      <div ref={containerRef} className="flex-1 w-full" />

      {/* Barras laterales (navegación por zonas, como el reader de manga) */}
      <button
        className="absolute left-0 top-0 bottom-0 w-1/4 z-10 flex items-center justify-start pl-3"
        onClick={(e) => { e.stopPropagation(); prev(); }}
        aria-label="Página anterior"
      >
        <span className={`p-2 rounded-full bg-black/40 text-white transition-opacity duration-300 ${showUI ? 'opacity-80' : 'opacity-0'}`}>
          <FaChevronLeft />
        </span>
      </button>
      <button
        className="absolute right-0 top-0 bottom-0 w-1/4 z-10 flex items-center justify-end pr-3"
        onClick={(e) => { e.stopPropagation(); next(); }}
        aria-label="Página siguiente"
      >
        <span className={`p-2 rounded-full bg-black/40 text-white transition-opacity duration-300 ${showUI ? 'opacity-80' : 'opacity-0'}`}>
          <FaChevronRight />
        </span>
      </button>

      {/* Barra inferior: controles */}
      <div
        className={`px-4 py-3 transition-opacity duration-300 ${
          showUI ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        style={{
          background: 'linear-gradient(to top, rgba(0,0,0,0.55), transparent)',
        }}
      >
        <div className="flex items-center justify-center gap-4 flex-wrap">
          {/* Navegación */}
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); prev(); }}
              className="p-2 rounded-lg bg-black/30 text-white hover:bg-black/50"
              title="Anterior"
            >
              <FaChevronLeft />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); next(); }}
              className="p-2 rounded-lg bg-black/30 text-white hover:bg-black/50"
              title="Siguiente"
            >
              <FaChevronRight />
            </button>
          </div>

          {/* Tamaño de fuente */}
          <div className="flex items-center gap-1">
            <button
              onClick={(e) => { e.stopPropagation(); setFontSize(f => Math.max(FONT_MIN, f - 2)); }}
              disabled={fontSize <= FONT_MIN}
              className="px-2.5 py-1.5 rounded-lg bg-black/30 text-white text-xs hover:bg-black/50 disabled:opacity-40"
              title="Reducir fuente"
            >
              A-
            </button>
            <span className="text-white/80 text-xs w-8 text-center tabular-nums">{fontSize}px</span>
            <button
              onClick={(e) => { e.stopPropagation(); setFontSize(f => Math.min(FONT_MAX, f + 2)); }}
              disabled={fontSize >= FONT_MAX}
              className="px-2.5 py-1.5 rounded-lg bg-black/30 text-white text-sm hover:bg-black/50 disabled:opacity-40"
              title="Aumentar fuente"
            >
              A+
            </button>
          </div>

          {/* Tema */}
          <div className="flex items-center gap-1.5">
            {themeBtn('light', FaSun, 'Tema claro')}
            {themeBtn('sepia', FaBookReader, 'Tema sepia')}
            {themeBtn('dark', FaMoon, 'Tema oscuro')}
          </div>
        </div>
      </div>
    </div>
  );
};

export default EpubReader;
