import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { mangaApi } from '../services/api';
import SearchBar from '../components/SearchBar';
import MangaCard from '../components/MangaCard';
import { FaSearch } from 'react-icons/fa';

const Search = () => {
  const [searchParams] = useSearchParams();
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const initialQuery = searchParams.get('q') || '';
  const [hasSearched, setHasSearched] = useState(!!initialQuery);

  useEffect(() => {
    if (initialQuery) {
      handleSearch(initialQuery);
    }
  }, []);

  const handleSearch = async (query) => {
    if (!query.trim()) return;

    try {
      setLoading(true);
      setHasSearched(true);
      // Solo buscar en AniList
      const response = await mangaApi.search(query, 'anilist');
      setResults(response.data.results);
    } catch (error) {
      console.error('Error buscando:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddManga = async (manga) => {
    try {
      await mangaApi.addFromAnilist({
        anilist_id: manga.anilist_id,
        monitored: true,
        auto_download: true,
      });
      alert(`"${manga.title}" añadido a la biblioteca!`);
      // Re-search to update results
      const query = searchParams.get('q') || initialQuery;
      if (query) handleSearch(query);
    } catch (error) {
      console.error('Error añadiendo manga:', error);
      alert('Error al añadir el manga. Inténtalo de nuevo.');
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-bold mb-2">Buscar Manga</h1>
        <p className="text-gray-400 mb-6">
          Busca en la base de datos de AniList
        </p>

        {/* Search Bar */}
        <SearchBar
          onSearch={handleSearch}
          placeholder="Buscar por titulo..."
          autoFocus={!initialQuery}
        />
      </div>

      {/* Results */}
      {loading && (
        <div className="text-center py-20">
          <div className="spinner border-4 border-primary border-t-transparent rounded-full w-12 h-12 mx-auto mb-4" />
          <p className="text-gray-400">Buscando en AniList...</p>
        </div>
      )}

      {!loading && hasSearched && results.length === 0 && (
        <div className="text-center py-20">
          <FaSearch className="text-6xl text-gray-600 mx-auto mb-4" />
          <h3 className="text-2xl font-bold mb-2">Sin resultados</h3>
          <p className="text-gray-400">Prueba con otro termino de busqueda</p>
        </div>
      )}

      {!loading && results.length > 0 && (
        <div>
          <h2 className="text-xl font-bold mb-6 text-gray-400">
            {results.length} resultado(s) encontrado(s)
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
            {results.map((manga) => (
              <MangaCard
                key={manga.anilist_id}
                manga={manga}
                showAddButton={true}
                onAdd={handleAddManga}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty state (no search yet) */}
      {!loading && !hasSearched && (
        <div className="text-center py-20">
          <FaSearch className="text-6xl text-gray-600 mx-auto mb-4" />
          <h3 className="text-2xl font-bold mb-2">Empieza a buscar</h3>
          <p className="text-gray-400">
            Introduce un titulo para buscar manga
          </p>
        </div>
      )}
    </div>
  );
};

export default Search;
