import { useEffect, useState } from 'react';
import { mangaApi } from '../services/api';
import MangaGrid from '../components/MangaGrid';
import { FaFire, FaStar, FaSortAmountDown } from 'react-icons/fa';

const Home = () => {
  const [trending, setTrending] = useState([]);
  const [popular, setPopular] = useState([]);
  const [loadingTrending, setLoadingTrending] = useState(true);
  const [loadingPopular, setLoadingPopular] = useState(true);
  const [activeTab, setActiveTab] = useState('trending');
  const [sortBy, setSortBy] = useState('default'); // default, rating, title, tomos

  useEffect(() => {
    loadTrending();
    loadPopular();
  }, []);

  const loadTrending = async () => {
    try {
      setLoadingTrending(true);
      const response = await mangaApi.getTrending(1, 18);
      setTrending(response.data);
    } catch (error) {
      console.error('Error cargando tendencias:', error);
    } finally {
      setLoadingTrending(false);
    }
  };

  const loadPopular = async () => {
    try {
      setLoadingPopular(true);
      const response = await mangaApi.getPopular(1, 18);
      setPopular(response.data);
    } catch (error) {
      console.error('Error cargando populares:', error);
    } finally {
      setLoadingPopular(false);
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
      // Reload data to update "in_library" status
      loadTrending();
      loadPopular();
    } catch (error) {
      console.error('Error añadiendo manga:', error);
      alert('Error al añadir el manga. Inténtalo de nuevo.');
    }
  };

  // Sort function
  const sortManga = (mangaList) => {
    if (sortBy === 'default') return mangaList;

    return [...mangaList].sort((a, b) => {
      switch (sortBy) {
        case 'rating':
          return (b.average_score || 0) - (a.average_score || 0);
        case 'title':
          return (a.title || '').localeCompare(b.title || '');
        case 'tomos':
          return (b.chapters || b.total_chapters || 0) - (a.chapters || a.total_chapters || 0);
        default:
          return 0;
      }
    });
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-bold mb-2">Descubrir Manga</h1>
        <p className="text-gray-400">Encuentra tu próximo manga favorito desde Anilist</p>
      </div>

      {/* Tabs and Sort */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-8 border-b border-gray-700 pb-4">
        <div className="flex gap-4">
          <button
            onClick={() => setActiveTab('trending')}
            className={`flex items-center gap-2 px-6 py-3 border-b-2 transition-colors ${
              activeTab === 'trending'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-400 hover:text-white'
            }`}
          >
            <FaFire />
            <span className="font-medium">Tendencias</span>
          </button>
          <button
            onClick={() => setActiveTab('popular')}
            className={`flex items-center gap-2 px-6 py-3 border-b-2 transition-colors ${
              activeTab === 'popular'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-400 hover:text-white'
            }`}
          >
            <FaStar />
            <span className="font-medium">Populares</span>
          </button>
        </div>

        {/* Sort Dropdown */}
        <div className="flex items-center gap-2">
          <FaSortAmountDown className="text-gray-400" />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="px-4 py-2 bg-dark-lighter rounded border border-gray-700 focus:border-primary focus:outline-none"
          >
            <option value="default">Orden por defecto</option>
            <option value="rating">Por puntuación</option>
            <option value="title">Por título</option>
            <option value="tomos">Por cantidad de tomos</option>
          </select>
        </div>
      </div>

      {/* Content */}
      {activeTab === 'trending' && (
        <div>
          <h2 className="text-2xl font-bold mb-6 flex items-center gap-2">
            <FaFire className="text-orange-500" />
            Tendencias Actuales
          </h2>
          <MangaGrid
            manga={sortManga(trending)}
            loading={loadingTrending}
            showAddButton={true}
            onAdd={handleAddManga}
          />
        </div>
      )}

      {activeTab === 'popular' && (
        <div>
          <h2 className="text-2xl font-bold mb-6 flex items-center gap-2">
            <FaStar className="text-yellow-500" />
            Más Populares
          </h2>
          <MangaGrid
            manga={sortManga(popular)}
            loading={loadingPopular}
            showAddButton={true}
            onAdd={handleAddManga}
          />
        </div>
      )}
    </div>
  );
};

export default Home;
