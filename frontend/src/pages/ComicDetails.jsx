import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { comicApi, mangaApi } from '../services/api';
import ContentDetailPage from '../components/ContentDetailPage';
import ComicIssueList from '../components/ComicIssueList';
import ConfirmModal from '../components/ConfirmModal';
import {
  FaBuilding,
  FaUser,
  FaPaintBrush,
  FaPalette,
  FaSync,
  FaTrash,
  FaSpinner,
  FaSearch,
  FaEye,
  FaEyeSlash,
  FaCalendar,
} from 'react-icons/fa';

const ComicDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [comic, setComic] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [searchingSources, setSearchingSources] = useState(false);
  const [issueRefreshKey, setIssueRefreshKey] = useState(0);
  const [translatedDescription, setTranslatedDescription] = useState(null);
  const [translating, setTranslating] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    loadComic();
  }, [id]);

  const loadComic = async () => {
    try {
      setLoading(true);
      setTranslatedDescription(null);
      const response = await comicApi.getComic(id);
      setComic(response.data);

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
      toast('Buscando fuentes… los links aparecerán según se resuelvan', { icon: 'ℹ️' });

      // Poll every 5s for up to 90s so resolved links appear progressively
      let polls = 0;
      const maxPolls = 18;
      const interval = setInterval(() => {
        polls++;
        setIssueRefreshKey(k => k + 1);
        if (polls >= maxPolls) {
          clearInterval(interval);
          setSearchingSources(false);
        }
      }, 5000);
    } catch (error) {
      console.error('Error searching sources:', error);
      toast.error('Error al buscar fuentes');
      setSearchingSources(false);
    }
  };

  const handleToggleMonitored = async () => {
    try {
      const newValue = !comic.monitored;
      await comicApi.updateComic(id, { monitored: newValue });
      setComic({ ...comic, monitored: newValue });
      toast(newValue ? `Siguiendo "${comic.title}"` : `Dejaste de seguir "${comic.title}"`, {
        icon: newValue ? '👁' : '👁‍🗨',
      });
    } catch (error) {
      console.error('Error updating comic:', error);
      toast.error('Error al actualizar el seguimiento');
    }
  };

  const handleDelete = async () => {
    try {
      setDeleting(true);
      await comicApi.deleteComic(id);
      toast.success('Cómic eliminado');
      navigate('/comics');
    } catch (error) {
      console.error('Error deleting:', error);
      toast.error('Error al eliminar el cómic');
      setDeleting(false);
    }
  };

  // Build props
  const totalIssues = comic?.count_of_issues || comic?.total_issues || 0;
  const downloadedIssues = comic?.downloaded_issues || 0;

  const badges = [];
  if (comic?.publisher) {
    badges.push({ label: comic.publisher, className: 'px-3 py-1 bg-dark-lighter rounded flex items-center gap-2' });
  }
  if (comic?.start_year) {
    badges.push({ label: `${comic.start_year}` });
  }

  const infoGrid = [];
  if (totalIssues) infoGrid.push({ label: 'Tomos totales', value: totalIssues });
  if (downloadedIssues) infoGrid.push({ label: 'Descargados', value: downloadedIssues });
  if (comic?.start_year) infoGrid.push({ label: 'Año inicio', value: comic.start_year, icon: <FaCalendar /> });

  const creators = [];
  if (comic?.writers?.length > 0) creators.push({ role: 'Escritores', names: comic.writers });
  if (comic?.artists?.length > 0) creators.push({ role: 'Artistas', names: comic.artists });
  if (comic?.colorists?.length > 0) creators.push({ role: 'Coloristas', names: comic.colorists });

  const externalLinks = [];
  if (comic?.comicvine_url) externalLinks.push({ label: 'ComicVine', url: comic.comicvine_url });

  const actions = [];
  actions.push({
    label: comic?.monitored ? 'Siguiendo' : 'Seguir',
    onClick: handleToggleMonitored,
    className: `btn ${comic?.monitored ? 'bg-red-500 hover:bg-red-600 text-white' : 'btn-secondary'} flex items-center gap-2`,
    icon: comic?.monitored ? <FaEye /> : <FaEyeSlash />,
    tooltip: comic?.monitored
      ? 'Fuentes buscadas automáticamente — Click para dejar de seguir'
      : 'Click para seguir y buscar fuentes automáticamente',
  });
  actions.push({
    label: searchingSources ? 'Buscando...' : 'Buscar Fuentes',
    onClick: handleSearchSources,
    disabled: searchingSources,
    className: 'btn bg-red-500 hover:bg-red-600 text-white flex items-center gap-2',
    icon: searchingSources ? <FaSpinner className="animate-spin" /> : <FaSearch />,
  });
  actions.push({
    label: 'Actualizar',
    onClick: handleRefresh,
    disabled: refreshing,
    className: 'btn btn-secondary flex items-center gap-2',
    icon: <FaSync className={refreshing ? 'animate-spin' : ''} />,
  });
  actions.push({
    label: 'Eliminar',
    onClick: () => setShowDeleteConfirm(true),
    disabled: deleting,
    className: 'btn btn-secondary text-red-500 hover:bg-red-500/20 flex items-center gap-2',
    icon: deleting ? <FaSpinner className="animate-spin" /> : <FaTrash />,
  });

  const statsCards = totalIssues > 0 ? [
    { label: 'Tomos totales', value: totalIssues, color: 'text-red-500' },
    { label: 'Descargados', value: downloadedIssues, color: 'text-green-500' },
    { label: 'Monitorizado', value: comic?.monitored ? 'Si' : 'No' },
    { label: 'Año inicio', value: comic?.start_year || '-' },
  ] : [];

  const progressData = totalIssues > 0
    ? { current: downloadedIssues, total: totalIssues, color: '#EF4444' }
    : null;

  return (
    <ContentDetailPage
      accentColor="#EF4444"
      coverImage={comic?.cover_image}
      title={comic?.title}
      badges={badges}
      description={comic?.description}
      translatedDescription={translatedDescription}
      translating={translating}
      infoGrid={infoGrid}
      creators={creators}
      externalLinks={externalLinks}
      actions={actions}
      stats={statsCards}
      progress={progressData}
      loading={loading}
      notFoundMessage="Comic no encontrado"
      backLink={{ to: '/comics', label: 'Volver a Comics' }}
    >
      <ComicIssueList comicId={id} refreshKey={issueRefreshKey} />
      <ConfirmModal
        isOpen={showDeleteConfirm}
        title="Eliminar cómic"
        message={`¿Eliminar "${comic?.title}" de la biblioteca?`}
        confirmText="Eliminar"
        onConfirm={() => { setShowDeleteConfirm(false); handleDelete(); }}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </ContentDetailPage>
  );
};

export default ComicDetails;
