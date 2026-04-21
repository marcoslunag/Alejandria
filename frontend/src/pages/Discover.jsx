import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { recommendationsApi, mangaApi, bookApi } from '../services/api';
import { FaCompass, FaSync, FaFire } from 'react-icons/fa';
import ContentCard from '../components/ContentCard';

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

const Discover = () => {
  const navigate = useNavigate();
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState('all');
  const [addedIds, setAddedIds] = useState(new Set());
  const [usingFallback, setUsingFallback] = useState(false);

  useEffect(() => {
    loadRecommendations();
  }, [typeFilter]);

  const loadRecommendations = async () => {
    setLoading(true);
    setUsingFallback(false);
    try {
      const { data } = await recommendationsApi.get({ limit: 24, type: typeFilter });
      const recs = data.recommendations || [];
      if (recs.length > 0) {
        setRecommendations(recs);
      } else {
        // Fallback: show AniList trending when library is empty or no recs
        const trendingData = await mangaApi.getTrending(1, 24);
        const rawTrending = Array.isArray(trendingData.data) ? trendingData.data : (trendingData.data?.results || []);
        const trending = rawTrending.map(m => ({
          content_type: 'manga',
          external_id: String(m.anilist_id || m.id),
          title: m.title,
          cover: m.cover_image || m.cover,
          authors: m.authors || [],
          score: m.average_score,
          anilist_id: m.anilist_id || m.id,
          recommendation_score: 0,
          reason_label: null,
        }));
        setRecommendations(trending);
        setUsingFallback(trending.length > 0);
      }
    } catch (err) {
      if (err.response?.status === 401) return;
      toast.error('Error cargando recomendaciones');
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async (rec) => {
    try {
      if (rec.content_type === 'manga' && rec.anilist_id) {
        await mangaApi.addFromAnilist({ anilist_id: rec.anilist_id });
        toast.success(`"${rec.title}" añadido a tu biblioteca`);
      } else if (rec.content_type === 'book' && rec.google_books_id) {
        await bookApi.addFromGoogleBooks({ google_books_id: rec.google_books_id });
        toast.success(`"${rec.title}" añadido a tu biblioteca`);
      } else {
        toast.error('No se puede añadir este tipo de contenido directamente');
        return;
      }
      setAddedIds((prev) => new Set([...prev, rec.external_id]));
    } catch (err) {
      if (err.response?.status === 409) {
        const { matched_title } = err.response.data;
        toast(`Ya tienes "${matched_title}" en tu biblioteca`, { icon: 'ℹ️' });
        setAddedIds((prev) => new Set([...prev, rec.external_id]));
      } else {
        toast.error('Error al añadir');
      }
    }
  };

  const typeFilters = [
    { value: 'all', label: 'Todo' },
    { value: 'books', label: 'Libros' },
    { value: 'manga', label: 'Manga' },
  ];

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      {/* Hero section */}
      <div className="bg-dark-card rounded-xl px-6 py-5 mb-6 border border-white/5 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-transparent to-gold/[0.03] pointer-events-none" />
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

      {/* Fallback banner */}
      {!loading && usingFallback && (
        <div className="mb-4 flex items-center gap-2 bg-orange-500/10 border border-orange-500/20 rounded-lg px-4 py-2 text-sm text-orange-300">
          <FaFire className="flex-shrink-0" />
          <span>Tendencias de AniList · Añade contenido a tu biblioteca para recibir recomendaciones personalizadas</span>
          <button onClick={() => navigate('/search')} className="ml-auto underline text-orange-200 hover:text-white">
            Explorar
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && recommendations.length === 0 && (
        <div className="text-center py-20 text-gray-500">
          <FaCompass className="text-6xl mx-auto mb-4 opacity-30" />
          <p className="text-lg">No hay recomendaciones disponibles</p>
          <p className="text-sm mt-1">Añade contenido a tu biblioteca para empezar</p>
          <button
            onClick={() => navigate('/search')}
            className="mt-4 px-4 py-2 bg-gold text-dark-base font-semibold rounded-lg hover:bg-gold-light transition-colors text-sm"
          >
            Explorar contenido
          </button>
        </div>
      )}

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
    </div>
  );
};

export default Discover;
