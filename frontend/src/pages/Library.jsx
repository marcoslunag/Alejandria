import { useEffect, useState } from 'react';
import { mangaApi } from '../services/api';
import MangaGrid from '../components/MangaGrid';
import { FaBook, FaFilter, FaSync, FaSortAmountDown } from 'react-icons/fa';

const Library = () => {
  const [manga, setManga] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState({
    monitored: null,
    status: '',
    search: '',
  });
  const [sortBy, setSortBy] = useState('title'); // title, rating, recent, tomos

  useEffect(() => {
    loadLibrary();
    loadStats();
  }, [filter]);

  const loadLibrary = async () => {
    try {
      setLoading(true);
      const params = {};
      if (filter.monitored !== null) params.monitored = filter.monitored;
      if (filter.status) params.status = filter.status;
      if (filter.search) params.search = filter.search;

      const response = await mangaApi.getLibrary(params);
      setManga(response.data);
    } catch (error) {
      console.error('Error loading library:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await mangaApi.getLibraryStats();
      setStats(response.data);
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  // Sort manga based on sortBy
  const sortedManga = [...manga].sort((a, b) => {
    switch (sortBy) {
      case 'rating':
        return (b.average_score || 0) - (a.average_score || 0);
      case 'recent':
        return new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at);
      case 'tomos':
        return (b.total_chapters || 0) - (a.total_chapters || 0);
      case 'title':
      default:
        return (a.title || '').localeCompare(b.title || '');
    }
  });

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-4xl font-bold flex items-center gap-3">
              <FaBook className="text-primary" />
              Mi Biblioteca
            </h1>
            <p className="text-gray-400 mt-2">
              Gestiona tu colección de manga
            </p>
          </div>
          <button
            onClick={loadLibrary}
            className="btn btn-secondary flex items-center gap-2"
          >
            <FaSync />
            <span>Actualizar</span>
          </button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Total Manga</p>
              <p className="text-2xl font-bold">{stats.total_manga}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Monitorizados</p>
              <p className="text-2xl font-bold">{stats.monitored_manga}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Total Tomos</p>
              <p className="text-2xl font-bold">{stats.total_chapters}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Descargados</p>
              <p className="text-2xl font-bold">{stats.downloaded_chapters}</p>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="card p-4">
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
              <option value="true">Monitorizados</option>
              <option value="false">No monitorizados</option>
            </select>

            {/* Status filter */}
            <select
              value={filter.status}
              onChange={(e) => setFilter({ ...filter, status: e.target.value })}
              className="input"
            >
              <option value="">Todos los estados</option>
              <option value="RELEASING">En publicación</option>
              <option value="FINISHED">Finalizado</option>
              <option value="NOT_YET_RELEASED">Por publicar</option>
            </select>

            {/* Sort */}
            <div className="flex items-center gap-2">
              <FaSortAmountDown className="text-gray-400" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="input"
              >
                <option value="title">Ordenar por título</option>
                <option value="rating">Ordenar por puntuación</option>
                <option value="recent">Últimos actualizados</option>
                <option value="tomos">Más tomos</option>
              </select>
            </div>

            {/* Clear filters */}
            {(filter.monitored !== null || filter.status || filter.search) && (
              <button
                onClick={() => setFilter({ monitored: null, status: '', search: '' })}
                className="btn btn-secondary text-sm"
              >
                Limpiar filtros
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Manga Grid */}
      <MangaGrid manga={sortedManga} loading={loading} />

      {/* Empty state */}
      {!loading && manga.length === 0 && (
        <div className="text-center py-20">
          <FaBook className="text-6xl text-gray-600 mx-auto mb-4" />
          <h3 className="text-2xl font-bold mb-2">Tu biblioteca está vacía</h3>
          <p className="text-gray-400 mb-6">
            Comienza descubriendo y añadiendo manga desde la página de inicio
          </p>
          <a href="/" className="btn btn-primary">
            Descubrir Manga
          </a>
        </div>
      )}
    </div>
  );
};

export default Library;
