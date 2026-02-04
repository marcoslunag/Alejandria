import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { comicApi } from '../services/api';
import {
  FaBook,
  FaCalendar,
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
  FaDownload,
  FaEye,
  FaEyeSlash
} from 'react-icons/fa';

const ComicDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [comic, setComic] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadComic();
  }, [id]);

  const loadComic = async () => {
    try {
      setLoading(true);
      const response = await comicApi.getComic(id);
      setComic(response.data);
    } catch (error) {
      console.error('Error loading comic:', error);
      if (error.response?.status === 404) {
        navigate('/comics');
      }
    } finally {
      setLoading(false);
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

  const handleToggleMonitored = async () => {
    try {
      await comicApi.updateComic(id, { monitored: !comic.monitored });
      setComic({ ...comic, monitored: !comic.monitored });
    } catch (error) {
      console.error('Error updating comic:', error);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`¿Eliminar "${comic.title}" de la biblioteca?`)) return;
    
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
        <FaSpinner className="animate-spin text-4xl text-primary mx-auto mb-4" />
        <p className="text-gray-400">Cargando cómic...</p>
      </div>
    );
  }

  if (!comic) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <p className="text-gray-400">Cómic no encontrado</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Back button */}
      <button
        onClick={() => navigate('/comics')}
        className="btn btn-secondary mb-6 flex items-center gap-2"
      >
        <FaArrowLeft />
        Volver a Cómics
      </button>

      {/* Header with cover and info */}
      <div className="card overflow-hidden mb-8">
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
                <FaBook className="text-6xl text-gray-500" />
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
                  className={`btn ${comic.monitored ? 'btn-primary' : 'btn-secondary'}`}
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
              <p className="text-gray-300 mb-4 line-clamp-4">
                {comic.description}
              </p>
            )}

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="bg-surface-light rounded-lg p-3 text-center">
                <p className="text-2xl font-bold text-primary">
                  {comic.count_of_issues || comic.total_issues || 0}
                </p>
                <p className="text-sm text-gray-400">Issues totales</p>
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
                    <span className="text-gray-500">—</span>
                  )}
                </p>
                <p className="text-sm text-gray-400">Monitored</p>
              </div>
              <div className="bg-surface-light rounded-lg p-3 text-center">
                <p className="text-2xl font-bold">
                  {comic.start_year || '—'}
                </p>
                <p className="text-sm text-gray-400">Año inicio</p>
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
                className="inline-flex items-center gap-2 text-primary hover:underline mt-4"
              >
                <FaExternalLinkAlt />
                Ver en ComicVine
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Issues list */}
      <div className="card p-6">
        <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
          <FaBook className="text-primary" />
          Issues ({comic.issues?.length || 0})
        </h2>

        {comic.issues?.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {comic.issues.map((issue) => (
              <div
                key={issue.id}
                className={`relative rounded-lg overflow-hidden ${
                  issue.status === 'downloaded' 
                    ? 'ring-2 ring-green-500' 
                    : 'bg-surface-light'
                }`}
              >
                {/* Cover */}
                <div className="aspect-[2/3]">
                  {issue.cover_image ? (
                    <img
                      src={issue.cover_image}
                      alt={`Issue ${issue.issue_number}`}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full bg-gray-700 flex items-center justify-center">
                      <span className="text-2xl font-bold text-gray-500">
                        #{issue.issue_number || '?'}
                      </span>
                    </div>
                  )}
                </div>

                {/* Status badge */}
                {issue.status === 'downloaded' && (
                  <div className="absolute top-2 right-2 bg-green-500 text-white p-1 rounded-full">
                    <FaCheck className="text-xs" />
                  </div>
                )}
                {issue.status === 'downloading' && (
                  <div className="absolute top-2 right-2 bg-blue-500 text-white p-1 rounded-full">
                    <FaSpinner className="text-xs animate-spin" />
                  </div>
                )}

                {/* Issue info */}
                <div className="p-2 bg-surface-dark">
                  <p className="font-bold text-sm truncate">
                    #{issue.issue_number || '?'}
                  </p>
                  {issue.title && (
                    <p className="text-xs text-gray-400 truncate" title={issue.title}>
                      {issue.title}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <FaBook className="text-4xl text-gray-600 mx-auto mb-2" />
            <p className="text-gray-400">
              No hay issues disponibles. Intenta actualizar los metadatos.
            </p>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="btn btn-primary mt-4"
            >
              <FaSync className={`mr-2 ${refreshing ? 'animate-spin' : ''}`} />
              Buscar Issues
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ComicDetails;
