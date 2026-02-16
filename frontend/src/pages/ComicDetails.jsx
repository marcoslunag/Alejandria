import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { comicApi, mangaApi } from '../services/api';
import ContentDetailPage from '../components/ContentDetailPage';
import ComicIssueList from '../components/ComicIssueList';
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
      alert('Buscando fuentes de descarga en segundo plano...');
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
    label: comic?.monitored ? 'Monitorizado' : 'No monitorizado',
    onClick: handleToggleMonitored,
    className: `btn ${comic?.monitored ? 'bg-red-500 hover:bg-red-600 text-white' : 'btn-secondary'} flex items-center gap-2`,
    icon: comic?.monitored ? <FaEye /> : <FaEyeSlash />,
    tooltip: comic?.monitored
      ? 'Se buscarán fuentes automáticamente'
      : 'No se buscarán fuentes automáticamente',
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
    onClick: handleDelete,
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
      <ComicIssueList comicId={id} />
    </ContentDetailPage>
  );
};

export default ComicDetails;
