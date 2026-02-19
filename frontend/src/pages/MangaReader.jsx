import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { FaArrowLeft, FaArrowRight, FaChevronLeft, FaExpand, FaCompress, FaTimes } from 'react-icons/fa';
import api from '../services/api';

export default function MangaReader() {
  const { mangaId, chapterId } = useParams();
  const navigate = useNavigate();

  const [pages, setPages] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [chapterInfo, setChapterInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [showUI, setShowUI] = useState(true);
  const [uiTimeout, setUiTimeout] = useState(null);

  useEffect(() => {
    loadPages();
  }, [mangaId, chapterId]);

  const loadPages = async () => {
    try {
      setLoading(true);
      const { data } = await api.get(`/manga/${mangaId}/chapters/${chapterId}/pages`);
      setChapterInfo(data);
      setPages(data.pages || []);
      setCurrentPage(0);
    } catch (e) {
      setError(e.response?.data?.detail || 'Error cargando capítulo');
    } finally {
      setLoading(false);
    }
  };

  const goTo = useCallback((idx) => {
    if (idx >= 0 && idx < pages.length) {
      setCurrentPage(idx);
    }
  }, [pages.length]);

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') goTo(currentPage + 1);
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') goTo(currentPage - 1);
      else if (e.key === 'Escape') navigate(-1);
      else if (e.key === 'f') toggleFullscreen();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [currentPage, goTo]);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.();
      setFullscreen(true);
    } else {
      document.exitFullscreen?.();
      setFullscreen(false);
    }
  };

  // Auto-hide UI on mouse stop
  const resetUiTimer = useCallback(() => {
    setShowUI(true);
    if (uiTimeout) clearTimeout(uiTimeout);
    const t = setTimeout(() => setShowUI(false), 3000);
    setUiTimeout(t);
  }, [uiTimeout]);

  useEffect(() => {
    window.addEventListener('mousemove', resetUiTimer);
    return () => window.removeEventListener('mousemove', resetUiTimer);
  }, [resetUiTimer]);

  const pageUrl = (idx) => {
    const base = `${import.meta.env.VITE_API_URL || ''}/api/v1/manga/${mangaId}/chapters/${chapterId}/pages/${idx}`;
    const token = localStorage.getItem('token');
    return token ? `${base}?token=${encodeURIComponent(token)}` : base;
  };

  if (loading) return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <div className="text-white text-lg">Cargando capítulo...</div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen bg-black flex items-center justify-center flex-col gap-4">
      <div className="text-red-400 text-lg">{error}</div>
      <button onClick={() => navigate(-1)} className="text-gray-400 hover:text-white flex items-center gap-2">
        <FaChevronLeft /> Volver
      </button>
    </div>
  );

  return (
    <div
      className="min-h-screen bg-black relative overflow-hidden select-none"
      onMouseMove={resetUiTimer}
    >
      {/* Top bar */}
      <div className={`fixed top-0 left-0 right-0 z-50 bg-gradient-to-b from-black/90 to-transparent px-4 py-3 flex items-center gap-4 transition-opacity duration-300 ${showUI ? 'opacity-100' : 'opacity-0'}`}>
        <button
          onClick={() => navigate(-1)}
          className="text-white hover:text-gray-300 flex items-center gap-2 text-sm"
        >
          <FaTimes /> Cerrar
        </button>
        {chapterInfo && (
          <span className="text-gray-300 text-sm">
            {chapterInfo.chapter_title || `Capítulo ${chapterInfo.chapter_number}`}
          </span>
        )}
        <div className="ml-auto flex items-center gap-3">
          <span className="text-gray-400 text-sm">
            {currentPage + 1} / {pages.length}
          </span>
          <button onClick={toggleFullscreen} className="text-white hover:text-gray-300">
            {fullscreen ? <FaCompress /> : <FaExpand />}
          </button>
        </div>
      </div>

      {/* Page image */}
      <div className="flex items-center justify-center min-h-screen" onClick={() => setShowUI(v => !v)}>
        {pages.length > 0 && (
          <img
            key={currentPage}
            src={pageUrl(currentPage)}
            alt={`Página ${currentPage + 1}`}
            className="max-h-screen max-w-full object-contain"
            style={{ minHeight: '200px' }}
          />
        )}
      </div>

      {/* Left/right click areas */}
      <button
        onClick={(e) => { e.stopPropagation(); goTo(currentPage - 1); }}
        className="fixed left-0 top-0 bottom-0 w-1/4 z-40 flex items-center justify-start pl-4 group"
        disabled={currentPage === 0}
      >
        <div className={`transition-opacity duration-200 ${showUI && currentPage > 0 ? 'opacity-100' : 'opacity-0'} group-hover:opacity-100`}>
          <div className="bg-black/50 rounded-full p-3">
            <FaArrowLeft className="text-white text-xl" />
          </div>
        </div>
      </button>

      <button
        onClick={(e) => { e.stopPropagation(); goTo(currentPage + 1); }}
        className="fixed right-0 top-0 bottom-0 w-1/4 z-40 flex items-center justify-end pr-4 group"
        disabled={currentPage === pages.length - 1}
      >
        <div className={`transition-opacity duration-200 ${showUI && currentPage < pages.length - 1 ? 'opacity-100' : 'opacity-0'} group-hover:opacity-100`}>
          <div className="bg-black/50 rounded-full p-3">
            <FaArrowRight className="text-white text-xl" />
          </div>
        </div>
      </button>

      {/* Bottom progress bar */}
      <div className={`fixed bottom-0 left-0 right-0 z-50 bg-gradient-to-t from-black/90 to-transparent px-4 py-4 transition-opacity duration-300 ${showUI ? 'opacity-100' : 'opacity-0'}`}>
        {/* Thumbnail strip */}
        <div className="flex gap-1 justify-center mb-3 overflow-x-auto max-w-2xl mx-auto">
          {pages.map((_, i) => (
            <button
              key={i}
              onClick={() => goTo(i)}
              className={`flex-shrink-0 w-2 h-2 rounded-full transition-all ${
                i === currentPage ? 'bg-white scale-125' : 'bg-gray-600 hover:bg-gray-400'
              }`}
            />
          ))}
        </div>

        {/* Progress bar */}
        <div className="w-full bg-gray-700 rounded-full h-1">
          <div
            className="bg-blue-500 h-1 rounded-full transition-all duration-200"
            style={{ width: pages.length > 1 ? `${(currentPage / (pages.length - 1)) * 100}%` : '100%' }}
          />
        </div>
      </div>
    </div>
  );
}
