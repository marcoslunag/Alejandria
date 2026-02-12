import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { comicApi, mangaApi } from '../services/api';
import ComicIssueList from '../components/ComicIssueList';
import {
  FaMask,
  FaBuilding,
  FaUser,
  FaPaintBrush,
  FaPalette,
  FaSync,
  FaTrash,
  FaArrowLeft,
  FaExternalLinkAlt,
  FaSpinner,
  FaCheck,
  FaSearch,
  FaEye,
  FaEyeSlash,
  FaLanguage
} from 'react-icons/fa';

const ComicDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [comic, setComic] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [searchingSources, setSearchingSources] = useState(false);
  const [translatedDescription, setTranslatedDescription] = useState(null);
  const [translating, setTranslating] = useState(false);

  useEffect(() => {
    loadComic();
  }, [id]);

  const loadComic = async () => {
    try {
      setLoading(true);
      setTranslatedDescription(null);
      const response = await comicApi.getComic(id);
      setComic(response.data);

      // Auto-translate description if available
      if (response.data.description) {
        translateDescription(response.data.description);
      }
    } catch (error) {
      console.error('Error loading comic:', error);
      if (error.response?.status === 404) {
        navigate('/comics');
      }
    } finally {
      setLoading(false);
    }
  };

  const translateDescription = async (text) => {
    if (!text) return;

    try {
      setTranslating(true);
      const cleanText = text.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '');
      const response = await mangaApi.translateText(cleanText);
      if (response.data.translated) {
        setTranslatedDescription(response.data.translated);
      }
    } catch (error) {
      console.error('Error translating:', error);
    } finally {
      setTranslating(false);
    }
  };

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      await comicApi.refreshComic(id);
      // Wait a bit for background task to start
      setTimeout(() => loadComic(), 2000);
    } catch (error) {
      console.error('Error refreshing:', error);
    } finally {
      setRefreshing(false);
    }
  };

  const handleSearchSources = async () => {
    try {
      setSearchingSources(true);
      await comicApi.searchSources(id);
      alert('Buscando fuentes de descarga en segundo plano...');
      // Reload after a delay
      setTimeout(() => loadComic(), 3000);
    } catch (error) {
      console.error('Error searching sources:', error);
      alert('Error al buscar fuentes');
    } finally {
      setSearchingSources(false);
    }
  };

  const handleToggleMonitored = async () => {
    try {
      await comicApi.updateComic(id, { monitored: !comic.monitored });
      setComic({ ...comic, monitored: !comic.monitored });
    } catch (error) {
      console.error('Error updating comic:', error);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Eliminar "${comic.title}" de la biblioteca?`)) return;

    try {
      setDeleting(true);
      await comicApi.deleteComic(id);
      navigate('/comics');
    } catch (error) {
      console.error('Error deleting:', error);
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <FaSpinner className="animate-spin text-4xl text-red-500 mx-auto mb-4" />
        <p className="text-gray-400">Cargando comic...</p>
      </div>
    );
  }

  if (!comic) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <p className="text-gray-400">Comic no encontrado</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Banner with blur background */}
      <div className="relative h-64 md:h-80 overflow-hidden">
        {comic.cover_image ? (
          <>
            <img
              src={comic.cover_image}
              alt=""
              className="absolute inset-0 w-full h-full object-cover blur-xl scale-110 opacity-50"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-dark via-dark/80 to-transparent" />
          </>
        ) : (
          <div className="absolute inset-0 bg-gradient-to-t from-dark to-red-900/30" />
        )}
      </div>

      <div className="container mx-auto px-4 -mt-32 relative z-10">
        {/* Back button */}
        <button
          onClick={() => navigate('/comics')}
          className="btn btn-secondary mb-6 flex items-center gap-2"
        >
          <FaArrowLeft />
          Volver a Comics
        </button>

        {/* Header with cover and info */}
        <div className="card overflow-hidden mb-8" style={{ borderTop: '4px solid #EF4444' }}>
          <div className="md:flex">
            {/* Cover */}
            <div className="md:w-64 flex-shrink-0">
              {comic.cover_image ? (
                <img
                  src={comic.cover_image}
                  alt={comic.title}
                  className="w-full h-auto md:h-96 object-cover"
                />
              ) : (
                <div className="w-full h-64 md:h-96 bg-gray-700 flex items-center justify-center">
                  <FaMask className="text-6xl text-gray-500" />
                </div>
              )}
            </div>

            {/* Info */}
            <div className="p-6 flex-1">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h1 className="text-3xl font-bold mb-2">{comic.title}</h1>
                  {comic.publisher && (
                    <div className="flex items-center gap-2 text-gray-400 mb-2">
                      <FaBuilding />
                      <span>{comic.publisher}</span>
                      {comic.start_year && <span>({comic.start_year})</span>}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex gap-2">
                  <button
                    onClick={handleToggleMonitored}
                    className={`btn ${comic.monitored ? 'bg-red-500 hover:bg-red-600 text-white' : 'btn-secondary'}`}
                    title={comic.monitored ? 'Dejar de monitorizar' : 'Monitorizar'}
                  >
                    {comic.monitored ? <FaEye /> : <FaEyeSlash />}
                  </button>
                  <button
                    onClick={handleRefresh}
                    disabled={refreshing}
                    className="btn btn-secondary"
                    title="Actualizar metadatos"
                  >
                    <FaSync className={refreshing ? 'animate-spin' : ''} />
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="btn btn-secondary text-red-500 hover:bg-red-500/20"
                    title="Eliminar de biblioteca"
                  >
                    {deleting ? <FaSpinner className="animate-spin" /> : <FaTrash />}
                  </button>
                </div>
              </div>

              {/* Description */}
              {comic.description && (
                <div className="mb-4">
                  {translating ? (
                    <div className="flex items-center gap-2 text-gray-400">
                      <FaSpinner className="animate-spin" />
                      <span>Traduciendo...</span>
                    </div>
                  ) : (
                    <p className="text-gray-300 line-clamp-4">
                      {translatedDescription || comic.description.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '')}
                    </p>
                  )}
                </div>
              )}

              {/* Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div className="bg-surface-light rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-red-500">
                    {comic.count_of_issues || comic.total_issues || 0}
                  </p>
                  <p className="text-sm text-gray-400">Tomos totales</p>
                </div>
                <div className="bg-surface-light rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-green-500">
                    {comic.downloaded_issues || 0}
                  </p>
                  <p className="text-sm text-gray-400">Descargados</p>
                </div>
                <div className="bg-surface-light rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold">
                    {comic.monitored ? (
                      <FaCheck className="text-green-500 mx-auto" />
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </p>
                  <p className="text-sm text-gray-400">Monitorizado</p>
                </div>
                <div className="bg-surface-light rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold">
                    {comic.start_year || '-'}
                  </p>
                  <p className="text-sm text-gray-400">Ano inicio</p>
                </div>
              </div>

              {/* Creators */}
              <div className="space-y-2 text-sm">
                {comic.writers?.length > 0 && (
                  <div className="flex items-center gap-2">
                    <FaUser className="text-gray-500" />
                    <span className="text-gray-400">Escritores:</span>
                    <span>{comic.writers.join(', ')}</span>
                  </div>
                )}
                {comic.artists?.length > 0 && (
                  <div className="flex items-center gap-2">
                    <FaPaintBrush className="text-gray-500" />
                    <span className="text-gray-400">Artistas:</span>
                    <span>{comic.artists.join(', ')}</span>
                  </div>
                )}
                {comic.colorists?.length > 0 && (
                  <div className="flex items-center gap-2">
                    <FaPalette className="text-gray-500" />
                    <span className="text-gray-400">Coloristas:</span>
                    <span>{comic.colorists.join(', ')}</span>
                  </div>
                )}
              </div>

              {/* External link */}
              {comic.comicvine_url && (
                <a
                  href={comic.comicvine_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-red-400 hover:text-red-300 hover:underline mt-4"
                >
                  <FaExternalLinkAlt />
                  Ver en ComicVine
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Search Sources Button */}
        <div className="card p-6 mb-8" style={{ borderTop: '4px solid #EF4444' }}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold">Buscar Fuentes de Descarga</h3>
              <p className="text-sm text-gray-400">
                Busca links de descarga en GetComics y otras fuentes
              </p>
            </div>
            <button
              onClick={handleSearchSources}
              disabled={searchingSources}
              className="btn bg-red-500 hover:bg-red-600 text-white flex items-center gap-2"
            >
              {searchingSources ? (
                <>
                  <FaSpinner className="animate-spin" />
                  Buscando...
                </>
              ) : (
                <>
                  <FaSearch />
                  Buscar Fuentes
                </>
              )}
            </button>
          </div>
        </div>

        {/* Issues list using ComicIssueList component */}
        <ComicIssueList comicId={id} />
      </div>
    </div>
  );
};

export default ComicDetails;
