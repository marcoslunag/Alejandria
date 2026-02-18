import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { mangaApi } from '../services/api';
import ContentDetailPage from '../components/ContentDetailPage';
import ChapterList from '../components/ChapterList';
import ConfirmModal from '../components/ConfirmModal';
import {
  FaCalendar,
  FaBook,
  FaGlobe,
  FaSync,
  FaTrash,
} from 'react-icons/fa';

const MangaDetails = () => {
  const { id } = useParams();
  const [manga, setManga] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

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
      toast('Actualización en cola. Los nuevos tomos se obtendrán en breve.', { icon: 'ℹ️' });
      setTimeout(loadManga, 2000);
    } catch (error) {
      console.error('Error actualizando:', error);
      toast.error('Error al actualizar');
    }
  };

  const handleDelete = async () => {
    try {
      await mangaApi.deleteManga(id);
      toast.success('Manga eliminado correctamente');
      window.location.href = '/library';
    } catch (error) {
      console.error('Error eliminando:', error);
      toast.error('Error al eliminar el manga');
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

  const getStatusBadge = () => {
    if (!manga?.status) return null;
    const colorMap = {
      'RELEASING': 'bg-green-500/20 text-green-500',
      'FINISHED': 'bg-blue-500/20 text-blue-500',
    };
    return {
      label: getStatusText(manga.status),
      className: `px-3 py-1 rounded ${colorMap[manga.status] || 'bg-gray-500/20 text-gray-500'}`,
    };
  };

  // Build props for ContentDetailPage
  const badges = [];
  if (manga?.format) badges.push({ label: manga.format });
  const statusBadge = getStatusBadge();
  if (statusBadge) badges.push(statusBadge);

  const infoGrid = [];
  if (manga?.start_date) infoGrid.push({ label: 'Fecha de inicio', value: manga.start_date, icon: <FaCalendar /> });
  if (manga?.chapters_total) infoGrid.push({ label: 'Total de Tomos', value: manga.chapters_total, icon: <FaBook /> });
  if (manga?.country) infoGrid.push({ label: 'Origen', value: manga.country, icon: <FaGlobe /> });

  const creators = [];
  if (manga?.authors?.length > 0) creators.push({ role: 'Autor', names: manga.authors });
  if (manga?.artists?.length > 0) creators.push({ role: 'Artista', names: manga.artists });

  const externalLinks = [];
  if (manga?.anilist_url) externalLinks.push({ label: 'Anilist', url: manga.anilist_url });
  if (manga?.source_url) externalLinks.push({ label: 'Fuente', url: manga.source_url });

  const actions = [];
  if (manga?.status === 'RELEASING') {
    actions.push({
      label: manga.monitored ? '🔔 Monitorizado' : '🔕 No monitorizado',
      onClick: handleToggleMonitored,
      className: `btn ${manga.monitored ? 'btn-primary' : 'btn-secondary'}`,
      tooltip: manga.monitored
        ? 'Los nuevos tomos se descargarán automáticamente'
        : 'Recibirás una notificación cuando salgan nuevos tomos pero no se descargarán automáticamente',
    });
  }
  if (manga?.status === 'FINISHED') {
    actions.push({
      label: '📕 Finalizado',
      onClick: () => {},
      className: 'btn btn-secondary cursor-default opacity-75',
      title: 'El manga ha finalizado, no hay nuevos tomos que monitorizar',
    });
  }
  actions.push({
    label: 'Actualizar',
    onClick: handleRefresh,
    className: 'btn btn-secondary flex items-center gap-2',
    icon: <FaSync />,
  });
  actions.push({
    label: 'Eliminar',
    onClick: () => setShowDeleteConfirm(true),
    className: 'btn bg-red-500 hover:bg-red-600 text-white flex items-center gap-2',
    icon: <FaTrash />,
  });

  const statsCards = stats ? [
    { label: 'Total', value: stats.total_chapters },
    { label: 'Descargados', value: stats.downloaded, color: 'text-green-500' },
    { label: 'Descargando', value: stats.downloading, color: 'text-blue-500' },
    { label: 'Pendientes', value: stats.pending, color: 'text-yellow-500' },
    { label: 'Con errores', value: stats.failed, color: 'text-red-500' },
    { label: 'Enviados a Kindle', value: stats.sent_to_kindle, color: 'text-purple-500' },
  ] : [];

  const progressData = stats && stats.total_chapters > 0
    ? { current: stats.downloaded + stats.sent_to_kindle, total: stats.total_chapters }
    : null;

  return (
    <ContentDetailPage
      accentColor={manga?.cover_color || '#3B82F6'}
      bannerImage={manga?.banner_image}
      coverImage={manga?.cover_image}
      title={manga?.title}
      subtitles={[
        manga?.title_romaji !== manga?.title ? manga?.title_romaji : null,
        manga?.title_native,
      ]}
      badges={badges}
      score={manga?.average_score ? manga.average_score / 10 : null}
      description={manga?.description}
      genres={manga?.genres || []}
      infoGrid={infoGrid}
      creators={creators}
      externalLinks={externalLinks}
      actions={actions}
      stats={statsCards}
      progress={progressData}
      loading={loading}
      notFoundMessage="Manga no encontrado"
      backLink={{ to: '/library', label: 'Ir a la Biblioteca' }}
    >
      <ChapterList mangaId={id} />
      <ConfirmModal
        isOpen={showDeleteConfirm}
        title="Eliminar manga"
        message={`¿Eliminar "${manga?.title}"? Esto eliminará todos los tomos descargados.`}
        confirmText="Eliminar"
        onConfirm={() => { setShowDeleteConfirm(false); handleDelete(); }}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </ContentDetailPage>
  );
};

export default MangaDetails;
