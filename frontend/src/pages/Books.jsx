import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { bookApi } from '../services/api';
import ContentGrid from '../components/ContentGrid';
import LibraryTabs from '../components/LibraryTabs';
import {
  FaBookReader,
  FaSync,
  FaSearch,
  FaFilter,
  FaSortAmountDown,
  FaEye,
} from 'react-icons/fa';

const Books = () => {
  const navigate = useNavigate();
  const [books, setBooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState({
    monitored: null,
    search: '',
    category: '',
    language: '',
  });
  const [sortBy, setSortBy] = useState('title');

  useEffect(() => {
    loadLibrary();
    loadStats();
  }, [filter]);

  const loadLibrary = async () => {
    try {
      setLoading(true);
      const params = { sort: sortBy };
      if (filter.monitored !== null) params.monitored = filter.monitored;
      if (filter.search) params.search = filter.search;

      const response = await bookApi.getLibrary(params);
      setBooks(response.data);
    } catch (error) {
      console.error('Error loading library:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await bookApi.getStats();
      setStats(response.data);
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  const handleToggleMonitor = async (item) => {
    try {
      const newValue = !item.monitored;
      await bookApi.updateBook(item.id, { monitored: newValue });
      setBooks(prev => prev.map(b => b.id === item.id ? { ...b, monitored: newValue } : b));
      toast(newValue ? `Siguiendo "${item.title}"` : `Dejaste de seguir "${item.title}"`, {
        icon: newValue ? '👁' : '👁‍🗨',
      });
    } catch {
      toast.error('Error al actualizar el seguimiento');
    }
  };

  // Extract unique categories and languages from loaded books
  const availableCategories = [...new Set(books.flatMap(b => b.categories || []))].sort();
  const LANG_LABELS = { es: 'Español', en: 'Inglés', fr: 'Francés', de: 'Alemán', it: 'Italiano', pt: 'Portugués' };
  const availableLanguages = [...new Set(books.map(b => b.language).filter(Boolean))].sort();

  // Client-side category/language filter
  const filteredBooks = books.filter(b => {
    if (filter.category && !(b.categories || []).includes(filter.category)) return false;
    if (filter.language && b.language !== filter.language) return false;
    return true;
  });

  // Sort books
  const sortedBooks = [...filteredBooks].sort((a, b) => {
    switch (sortBy) {
      case 'rating':
        return (b.average_rating || 0) - (a.average_rating || 0);
      case 'recent':
        return new Date(b.created_at) - new Date(a.created_at);
      case 'title':
      default:
        return (a.title || '').localeCompare(b.title || '');
    }
  });

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Unified library tabs */}
      <LibraryTabs />

      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-4xl font-bold flex items-center gap-3">
              <FaBookReader className="text-emerald-500" />
              Mi Biblioteca de Libros
            </h1>
            <p className="text-gray-400 mt-2">
              Gestiona tu biblioteca de libros
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => navigate('/search')}
              className="btn bg-emerald-500 hover:bg-emerald-600 text-white flex items-center gap-2"
            >
              <FaSearch />
              <span>Buscar libros</span>
            </button>
            <button
              onClick={loadLibrary}
              className="btn btn-secondary"
              title="Actualizar"
            >
              <FaSync />
            </button>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Total Libros</p>
              <p className="text-2xl font-bold">{stats.total_books}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Monitoreados</p>
              <p className="text-2xl font-bold">{stats.monitored_books}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Archivos Descargados</p>
              <p className="text-2xl font-bold">{stats.downloaded_files}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Enviados a Kindle</p>
              <p className="text-2xl font-bold">{stats.sent_files}</p>
            </div>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="card p-4 mb-6">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <FaFilter className="text-gray-400" />
            <span className="font-medium">Filtros:</span>
          </div>

          {/* Search */}
          <input
            type="text"
            placeholder="Buscar en biblioteca..."
            value={filter.search}
            onChange={(e) => setFilter({ ...filter, search: e.target.value })}
            className="input flex-1 min-w-[200px]"
          />

          {/* Monitored filter */}
          <select
            value={filter.monitored === null ? 'all' : filter.monitored}
            onChange={(e) =>
              setFilter({
                ...filter,
                monitored: e.target.value === 'all' ? null : e.target.value === 'true',
              })
            }
            className="input"
          >
            <option value="all">Todos</option>
            <option value="true">Monitoreados</option>
            <option value="false">No monitoreados</option>
          </select>

          {/* Category filter */}
          {availableCategories.length > 0 && (
            <select
              value={filter.category}
              onChange={(e) => setFilter({ ...filter, category: e.target.value })}
              className="input"
            >
              <option value="">Todas las categorías</option>
              {availableCategories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          )}

          {/* Language filter */}
          {availableLanguages.length > 0 && (
            <select
              value={filter.language}
              onChange={(e) => setFilter({ ...filter, language: e.target.value })}
              className="input"
            >
              <option value="">Todos los idiomas</option>
              {availableLanguages.map(l => <option key={l} value={l}>{LANG_LABELS[l] || l}</option>)}
            </select>
          )}

          {/* Sort */}
          <div className="flex items-center gap-2">
            <FaSortAmountDown className="text-gray-400" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="input"
            >
              <option value="title">Ordenar por titulo</option>
              <option value="rating">Ordenar por valoracion</option>
              <option value="recent">Ultimos agregados</option>
            </select>
          </div>

          {/* Clear filters */}
          {(filter.monitored !== null || filter.search || filter.category || filter.language) && (
            <button
              onClick={() => setFilter({ monitored: null, search: '', category: '', language: '' })}
              className="btn btn-secondary text-sm"
            >
              Limpiar filtros
            </button>
          )}
        </div>
      </div>

      {/* Books Grid */}
      <ContentGrid
        items={sortedBooks}
        type="book"
        loading={loading}
        onToggleMonitor={handleToggleMonitor}
      />

      {/* Empty state */}
      {!loading && books.length === 0 && (
        <div className="text-center py-20">
          <FaBookReader className="text-6xl text-gray-600 mx-auto mb-4" />
          <h3 className="text-2xl font-bold mb-2">Tu biblioteca esta vacia</h3>
          <p className="text-gray-400 mb-6">
            Comienza buscando libros en Google Books o en los scrapers
          </p>
          <button
            onClick={() => navigate('/search')}
            className="btn bg-emerald-500 hover:bg-emerald-600 text-white"
          >
            <FaSearch className="mr-2 inline" />
            Buscar libros
          </button>
        </div>
      )}
    </div>
  );
};

export default Books;
