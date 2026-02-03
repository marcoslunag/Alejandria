import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { mangaApi } from '../services/api';
import ChapterList from '../components/ChapterList';
import {
  FaStar,
  FaBook,
  FaCalendar,
  FaGlobe,
  FaEdit,
  FaTrash,
  FaSync,
  FaDownload,
  FaExternalLinkAlt,
} from 'react-icons/fa';

const MangaDetails = () => {
  const { id } = useParams();
  const [manga, setManga] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadManga();
    loadStats();
  }, [id]);

  const loadManga = async () => {
    try {
      setLoading(true);
      const response = await mangaApi.getManga(id);
      setManga(response.data);
    } catch (error) {
      console.error('Error cargando manga:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await mangaApi.getMangaStats(id);
      setStats(response.data);
    } catch (error) {
      console.error('Error cargando estadísticas:', error);
    }
  };

  const handleRefresh = async () => {
    try {
      await mangaApi.refreshManga(id);
      alert('Actualización en cola. Los nuevos tomos se obtendrán en breve.');
      setTimeout(loadManga, 2000);
    } catch (error) {
      console.error('Error actualizando:', error);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`¿Eliminar "${manga.title}"? Esto eliminará todos los tomos descargados.`)) {
      return;
    }
    try {
      await mangaApi.deleteManga(id);
      alert('Manga eliminado correctamente');
      window.location.href = '/library';
    } catch (error) {
      console.error('Error eliminando:', error);
      alert('Error al eliminar el manga');
    }
  };

  const handleToggleMonitored = async () => {
    try {
      await mangaApi.updateManga(id, { monitored: !manga.monitored });
      setManga({ ...manga, monitored: !manga.monitored });
    } catch (error) {
      console.error('Error actualizando:', error);
    }
  };

  const getStatusText = (status) => {
    const statusMap = {
      'RELEASING': 'En publicación',
      'FINISHED': 'Finalizado',
      'NOT_YET_RELEASED': 'Por publicar',
      'CANCELLED': 'Cancelado',
      'HIATUS': 'En pausa'
    };
    return statusMap[status] || status;
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="animate-pulse space-y-4">
          <div className="h-64 bg-dark-lighter rounded-lg" />
          <div className="h-8 bg-dark-lighter rounded w-1/2" />
          <div className="h-4 bg-dark-lighter rounded w-3/4" />
        </div>
      </div>
    );
  }

  if (!manga) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <p className="text-gray-400">Manga no encontrado</p>
        <Link to="/library" className="btn btn-primary mt-4">
          Ir a la Biblioteca
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Banner */}
      {manga.banner_image && (
        <div
          className="w-full h-64 bg-cover bg-center relative"
          style={{ backgroundImage: `url(${manga.banner_image})` }}
        >
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-dark/50 to-dark" />
        </div>
      )}

      <div className="container mx-auto px-4 pb-8" style={{ marginTop: manga.banner_image ? '-8rem' : '2rem' }}>
        <div className="flex flex-col md:flex-row gap-8">
          {/* Cover */}
          <div className="flex-shrink-0">
            <img
              src={manga.cover_image}
              alt={manga.title}
              className="w-64 rounded-lg shadow-2xl"
              style={{ borderTop: manga.cover_color ? `4px solid ${manga.cover_color}` : 'none' }}
            />
          </div>

          {/* Info */}
          <div className="flex-1">
            {/* Title */}
            <h1 className="text-4xl font-bold mb-2">{manga.title}</h1>
            {manga.title_romaji && manga.title_romaji !== manga.title && (
              <p className="text-xl text-gray-400 mb-2">{manga.title_romaji}</p>
            )}
            {manga.title_native && (
              <p className="text-lg text-gray-500 mb-4">{manga.title_native}</p>
            )}

            {/* Meta */}
            <div className="flex flex-wrap gap-4 mb-6">
              {manga.average_score && (
                <div className="flex items-center gap-2">
                  <FaStar className="text-yellow-400" />
                  <span className="font-bold">{(manga.average_score / 10).toFixed(1)}</span>
                </div>
              )}
              {manga.format && (
                <span className="px-3 py-1 bg-dark-lighter rounded">{manga.format}</span>
              )}
              {manga.status && (
                <span className={`px-3 py-1 rounded ${
                  manga.status === 'RELEASING' ? 'bg-green-500/20 text-green-500' :
                  manga.status === 'FINISHED' ? 'bg-blue-500/20 text-blue-500' :
                  'bg-gray-500/20 text-gray-500'
                }`}>
                  {getStatusText(manga.status)}
                </span>
              )}
            </div>

            {/* Genres */}
            {manga.genres && manga.genres.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-6">
                {manga.genres.map((genre) => (
                  <span key={genre} className="px-3 py-1 bg-primary/20 text-primary rounded-full text-sm">
                    {genre}
                  </span>
                ))}
              </div>
            )}

            {/* Description */}
            {manga.description && (
              <div className="mb-6">
                <h3 className="text-lg font-bold mb-2">Sinopsis</h3>
                <p className="text-gray-300 leading-relaxed">
                  {manga.description.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '')}
                </p>
              </div>
            )}

            {/* Additional Info */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
              {manga.start_date && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Fecha de inicio</p>
                  <p className="flex items-center gap-2">
                    <FaCalendar />
                    {manga.start_date}
                  </p>
                </div>
              )}
              {manga.chapters_total && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Total de Tomos</p>
                  <p className="flex items-center gap-2">
                    <FaBook />
                    {manga.chapters_total}
                  </p>
                </div>
              )}
              {manga.country && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Origen</p>
                  <p className="flex items-center gap-2">
                    <FaGlobe />
                    {manga.country}
                  </p>
                </div>
              )}
            </div>

            {/* Authors/Artists */}
            {(manga.authors?.length > 0 || manga.artists?.length > 0) && (
              <div className="mb-6">
                {manga.authors?.length > 0 && (
                  <p><span className="text-gray-400">Autor:</span> {manga.authors.join(', ')}</p>
                )}
                {manga.artists?.length > 0 && (
                  <p><span className="text-gray-400">Artista:</span> {manga.artists.join(', ')}</p>
                )}
              </div>
            )}

            {/* External Links */}
            <div className="flex gap-4 mb-6">
              {manga.anilist_url && (
                <a
                  href={manga.anilist_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <FaExternalLinkAlt />
                  Anilist
                </a>
              )}
              {manga.source_url && (
                <a
                  href={manga.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <FaExternalLinkAlt />
                  Fuente
                </a>
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-4">
              <button
                onClick={handleToggleMonitored}
                className={`btn ${manga.monitored ? 'btn-primary' : 'btn-secondary'}`}
              >
                {manga.monitored ? 'Monitorizado' : 'No monitorizado'}
              </button>
              <button onClick={handleRefresh} className="btn btn-secondary flex items-center gap-2">
                <FaSync />
                Actualizar
              </button>
              <button onClick={handleDelete} className="btn bg-red-500 hover:bg-red-600 text-white flex items-center gap-2">
                <FaTrash />
                Eliminar
              </button>
            </div>
          </div>
        </div>

        {/* Stats */}
        {stats && (
          <div className="mt-12">
            <h2 className="text-2xl font-bold mb-6">Estadísticas de Descarga</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              <div className="card p-4">
                <p className="text-gray-400 text-sm">Total</p>
                <p className="text-2xl font-bold">{stats.total_chapters}</p>
              </div>
              <div className="card p-4">
                <p className="text-gray-400 text-sm">Descargados</p>
                <p className="text-2xl font-bold text-green-500">{stats.downloaded}</p>
              </div>
              <div className="card p-4">
                <p className="text-gray-400 text-sm">Descargando</p>
                <p className="text-2xl font-bold text-blue-500">{stats.downloading}</p>
              </div>
              <div className="card p-4">
                <p className="text-gray-400 text-sm">Pendientes</p>
                <p className="text-2xl font-bold text-yellow-500">{stats.pending}</p>
              </div>
              <div className="card p-4">
                <p className="text-gray-400 text-sm">Con errores</p>
                <p className="text-2xl font-bold text-red-500">{stats.failed}</p>
              </div>
              <div className="card p-4">
                <p className="text-gray-400 text-sm">Enviados a Kindle</p>
                <p className="text-2xl font-bold text-purple-500">{stats.sent_to_kindle}</p>
              </div>
            </div>

            {/* Progress bar */}
            {stats.total_chapters > 0 && (
              <div className="mt-6">
                <div className="flex justify-between text-sm text-gray-400 mb-2">
                  <span>Progreso general</span>
                  <span>
                    {stats.downloaded + stats.sent_to_kindle} / {stats.total_chapters} ({
                      Math.round((stats.downloaded + stats.sent_to_kindle) / stats.total_chapters * 100)
                    }%)
                  </span>
                </div>
                <div className="w-full bg-dark-lighter rounded-full h-3">
                  <div
                    className="bg-primary h-3 rounded-full transition-all"
                    style={{
                      width: `${(stats.downloaded + stats.sent_to_kindle) / stats.total_chapters * 100}%`
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Chapter List */}
        <ChapterList mangaId={id} />
      </div>
    </div>
  );
};

export default MangaDetails;
