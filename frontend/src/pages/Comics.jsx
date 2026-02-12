import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { comicApi } from '../services/api';
import ComicGrid from '../components/ComicGrid';
import {
  FaMask,
  FaFilter,
  FaSync,
  FaSortAmountDown,
  FaSearch,
  FaPlus,
  FaSpinner,
  FaCheck
} from 'react-icons/fa';

const Comics = () => {
  const navigate = useNavigate();
  const [comics, setComics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState({
    monitored: null,
    publisher: '',
    search: '',
  });
  const [sortBy, setSortBy] = useState('title');

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [addingComic, setAddingComic] = useState(null);

  useEffect(() => {
    loadLibrary();
    loadStats();
  }, [filter]);

  const loadLibrary = async () => {
    try {
      setLoading(true);
      const params = {};
      if (filter.monitored !== null) params.monitored = filter.monitored;
      if (filter.publisher) params.publisher = filter.publisher;
      if (filter.search) params.search = filter.search;

      const response = await comicApi.getLibrary(params);
      setComics(response.data);
    } catch (error) {
      console.error('Error loading library:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await comicApi.getStats();
      setStats(response.data);
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    
    try {
      setSearching(true);
      const response = await comicApi.search(searchQuery);
      setSearchResults(response.data.results || []);
    } catch (error) {
      console.error('Error searching:', error);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleAddComic = async (comicvineId) => {
    try {
      setAddingComic(comicvineId);
      await comicApi.addComic(comicvineId);
      // Refresh library and search results
      await loadLibrary();
      await loadStats();
      // Update search results to show "in library"
      setSearchResults(prev => 
        prev.map(c => 
          c.comicvine_id === comicvineId 
            ? { ...c, in_library: true } 
            : c
        )
      );
    } catch (error) {
      console.error('Error adding comic:', error);
      alert(error.response?.data?.detail || 'Error añadiendo cómic');
    } finally {
      setAddingComic(null);
    }
  };

  // Sort comics
  const sortedComics = [...comics].sort((a, b) => {
    switch (sortBy) {
      case 'year':
        return (b.start_year || 0) - (a.start_year || 0);
      case 'issues':
        return (b.count_of_issues || 0) - (a.count_of_issues || 0);
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
              <FaMask className="text-red-500" />
              Comics
            </h1>
            <p className="text-gray-400 mt-2">
              Gestiona tu coleccion de comics americanos
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowSearch(!showSearch)}
              className="btn bg-red-500 hover:bg-red-600 text-white flex items-center gap-2"
            >
              <FaSearch />
              <span>Buscar Comics</span>
            </button>
            <button
              onClick={loadLibrary}
              className="btn btn-secondary flex items-center gap-2"
            >
              <FaSync />
            </button>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Total Cómics</p>
              <p className="text-2xl font-bold">{stats.total_comics}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Monitorizados</p>
              <p className="text-2xl font-bold">{stats.monitored_comics}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Total Issues</p>
              <p className="text-2xl font-bold">{stats.total_issues}</p>
            </div>
            <div className="card p-4">
              <p className="text-gray-400 text-sm">Descargados</p>
              <p className="text-2xl font-bold">{stats.downloaded_issues}</p>
            </div>
          </div>
        )}

        {/* Search Panel */}
        {showSearch && (
          <div className="card p-6 mb-6" style={{ borderTop: '4px solid #EF4444' }}>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <FaSearch className="text-red-500" />
              Buscar en ComicVine
            </h3>
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                placeholder="Buscar comics (ej: Spider-Man, Batman, X-Men)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="input flex-1 focus:border-red-500"
              />
              <button
                onClick={handleSearch}
                disabled={searching || !searchQuery.trim()}
                className="btn bg-red-500 hover:bg-red-600 text-white"
              >
                {searching ? <FaSpinner className="animate-spin" /> : <FaSearch />}
              </button>
            </div>

            {/* Search Results */}
            {searchResults.length > 0 && (
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {searchResults.map((comic) => (
                  <div
                    key={comic.comicvine_id}
                    className="flex gap-4 p-3 bg-surface-light rounded-lg hover:bg-surface-lighter transition-colors"
                  >
                    {/* Cover */}
                    <div className="w-16 h-24 flex-shrink-0">
                      {comic.cover_image ? (
                        <img
                          src={comic.cover_image}
                          alt={comic.title}
                          className="w-full h-full object-cover rounded"
                        />
                      ) : (
                        <div className="w-full h-full bg-gray-700 rounded flex items-center justify-center">
                          <FaMask className="text-gray-500" />
                        </div>
                      )}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <h4 className="font-bold truncate">{comic.title}</h4>
                      <div className="flex items-center gap-2 text-sm text-gray-400">
                        {comic.publisher && <span>{comic.publisher}</span>}
                        {comic.start_year && <span>({comic.start_year})</span>}
                        {comic.count_of_issues && (
                          <span className="text-red-400">{comic.count_of_issues} issues</span>
                        )}
                      </div>
                      {comic.description && (
                        <p className="text-sm text-gray-500 line-clamp-2 mt-1">
                          {comic.description}
                        </p>
                      )}
                    </div>

                    {/* Add button */}
                    <div className="flex-shrink-0">
                      {comic.in_library ? (
                        <span className="btn btn-secondary text-green-500 cursor-default">
                          <FaCheck /> En biblioteca
                        </span>
                      ) : (
                        <button
                          onClick={() => handleAddComic(comic.comicvine_id)}
                          disabled={addingComic === comic.comicvine_id}
                          className="btn bg-red-500 hover:bg-red-600 text-white"
                        >
                          {addingComic === comic.comicvine_id ? (
                            <FaSpinner className="animate-spin" />
                          ) : (
                            <><FaPlus /> Anadir</>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {searchResults.length === 0 && searchQuery && !searching && (
              <p className="text-gray-500 text-center py-4">
                No se encontraron resultados para "{searchQuery}"
              </p>
            )}
          </div>
        )}

        {/* Filters */}
        <div className="card p-4">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <FaFilter className="text-gray-400" />
              <span className="font-medium">Filtros:</span>
            </div>

            {/* Search in library */}
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

            {/* Publisher filter */}
            <input
              type="text"
              placeholder="Editorial..."
              value={filter.publisher}
              onChange={(e) => setFilter({ ...filter, publisher: e.target.value })}
              className="input w-32"
            />

            {/* Sort */}
            <div className="flex items-center gap-2">
              <FaSortAmountDown className="text-gray-400" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="input"
              >
                <option value="title">Ordenar por título</option>
                <option value="year">Ordenar por año</option>
                <option value="issues">Más issues</option>
              </select>
            </div>

            {/* Clear filters */}
            {(filter.monitored !== null || filter.publisher || filter.search) && (
              <button
                onClick={() => setFilter({ monitored: null, publisher: '', search: '' })}
                className="btn btn-secondary text-sm"
              >
                Limpiar filtros
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Comics Grid */}
      {loading ? (
        <ComicGrid comics={[]} loading={true} />
      ) : sortedComics.length > 0 ? (
        <ComicGrid comics={sortedComics.map(c => ({ ...c, in_library: true }))} loading={false} />
      ) : (
        <div className="text-center py-20">
          <FaMask className="text-6xl text-gray-600 mx-auto mb-4" />
          <h3 className="text-2xl font-bold mb-2">Tu biblioteca de comics esta vacia</h3>
          <p className="text-gray-400 mb-6">
            Busca y anade comics desde ComicVine usando el boton de busqueda
          </p>
          <button
            onClick={() => setShowSearch(true)}
            className="btn bg-red-500 hover:bg-red-600 text-white"
          >
            <FaSearch className="mr-2" />
            Buscar Comics
          </button>
        </div>
      )}
    </div>
  );
};

export default Comics;
