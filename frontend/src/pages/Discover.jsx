import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { recommendationsApi, mangaApi, bookApi } from '../services/api';
import { FaCompass, FaSync, FaStar, FaPlus, FaCheck, FaFire } from 'react-icons/fa';

const TYPE_LABELS = {
  manga: { label: 'Manga', color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  comic: { label: 'Cómic', color: 'bg-red-500/20 text-red-400 border-red-500/30' },
  book: { label: 'Libro', color: 'bg-green-500/20 text-green-400 border-green-500/30' },
};

const RecommendationCard = ({ rec, onAdd, addedIds }) => {
  const typeConfig = TYPE_LABELS[rec.content_type] || TYPE_LABELS.manga;
  const isAdded = addedIds.has(rec.external_id);
  const score = rec.score ? Math.round(rec.score) : null;

  return (
    <div className="bg-dark-card rounded-lg overflow-hidden flex flex-col hover:ring-1 hover:ring-gray-600 transition-all">
      {/* Cover */}
      <div className="relative aspect-[2/3] bg-dark-lighter overflow-hidden">
        {rec.cover ? (
          <img
            src={rec.cover}
            alt={rec.title}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-600 text-4xl">
            📚
          </div>
        )}
        {score !== null && (
          <div className="absolute top-2 right-2 bg-black/70 text-yellow-400 text-xs px-1.5 py-0.5 rounded flex items-center gap-1">
            <FaStar className="text-[9px]" />
            {score}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3 flex-1 flex flex-col gap-2">
        <div>
          <h3 className="font-medium text-sm line-clamp-2 leading-tight">{rec.title}</h3>
          {rec.authors?.length > 0 && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{rec.authors[0]}</p>
          )}
        </div>

        <div className="flex flex-wrap gap-1 mt-auto">
          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${typeConfig.color}`}>
            {typeConfig.label}
          </span>
          {rec.recommendation_score > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded border border-purple-500/30">
              {Math.round(rec.recommendation_score * 100)}% match
            </span>
          )}
        </div>

        {rec.reason_label && (
          <p className="text-[10px] text-gray-500 italic">{rec.reason_label}</p>
        )}

        <button
          onClick={() => onAdd(rec)}
          disabled={isAdded}
          className={`mt-1 w-full py-1.5 rounded text-xs font-medium flex items-center justify-center gap-1.5 transition-colors ${
            isAdded
              ? 'bg-green-600/20 text-green-400 cursor-default'
              : 'bg-primary hover:bg-primary/80 text-white'
          }`}
        >
          {isAdded ? <><FaCheck className="text-[9px]" /> Añadido</> : <><FaPlus className="text-[9px]" /> Añadir</>}
        </button>
      </div>
    </div>
  );
};

const SkeletonCard = () => (
  <div className="bg-dark-card rounded-lg overflow-hidden animate-pulse">
    <div className="aspect-[2/3] bg-dark-lighter" />
    <div className="p-3 space-y-2">
      <div className="h-3 bg-dark-lighter rounded w-3/4" />
      <div className="h-3 bg-dark-lighter rounded w-1/2" />
      <div className="h-6 bg-dark-lighter rounded mt-3" />
    </div>
  </div>
);

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
    { value: 'manga', label: 'Manga' },
    { value: 'books', label: 'Libros' },
  ];

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <FaCompass className="text-primary text-2xl" />
          <div>
            <h1 className="text-2xl font-bold">Descubrir</h1>
            <p className="text-gray-400 text-sm">Recomendaciones basadas en tu biblioteca</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Type filter */}
          <div className="flex gap-1 bg-dark-lighter rounded-lg p-1">
            {typeFilters.map((f) => (
              <button
                key={f.value}
                onClick={() => setTypeFilter(f.value)}
                className={`px-3 py-1.5 rounded text-sm transition-colors ${
                  typeFilter === f.value
                    ? 'bg-primary text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          <button
            onClick={loadRecommendations}
            className="text-gray-400 hover:text-white p-2 rounded-lg hover:bg-dark-lighter transition-colors"
            title="Actualizar recomendaciones"
          >
            <FaSync className={loading ? 'animate-spin' : ''} />
          </button>
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
            className="mt-4 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/80 transition-colors text-sm"
          >
            Explorar contenido
          </button>
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        {loading
          ? Array.from({ length: 12 }).map((_, i) => <SkeletonCard key={i} />)
          : recommendations.map((rec, i) => (
              <RecommendationCard
                key={`${rec.content_type}-${rec.external_id || i}`}
                rec={rec}
                onAdd={handleAdd}
                addedIds={addedIds}
              />
            ))}
      </div>
    </div>
  );
};

export default Discover;
