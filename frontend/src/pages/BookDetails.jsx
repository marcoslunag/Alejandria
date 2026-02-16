import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { bookApi } from '../services/api';
import ContentDetailPage from '../components/ContentDetailPage';
import BookChapterList from '../components/BookChapterList';
import {
  FaCalendar,
  FaSync,
  FaTrash,
  FaFileAlt,
} from 'react-icons/fa';

const BookDetails = () => {
  const { id } = useParams();
  const [book, setBook] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadBook();
    loadStats();
  }, [id]);

  const loadBook = async () => {
    try {
      setLoading(true);
      const response = await bookApi.getBook(id);
      setBook(response.data);
    } catch (error) {
      console.error('Error cargando libro:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await bookApi.getBookStats(id);
      setStats(response.data);
    } catch (error) {
      console.error('Error cargando estadisticas:', error);
    }
  };

  const handleRefresh = async () => {
    try {
      await bookApi.refreshBook(id);
      alert('Actualizacion en cola. Buscando nuevos archivos...');
      setTimeout(() => {
        loadBook();
        loadStats();
      }, 2000);
    } catch (error) {
      console.error('Error actualizando:', error);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Eliminar "${book.title}"? Esto eliminara todos los archivos descargados.`)) {
      return;
    }
    try {
      await bookApi.deleteBook(id);
      alert('Libro eliminado correctamente');
      window.location.href = '/books';
    } catch (error) {
      console.error('Error eliminando:', error);
      alert('Error al eliminar el libro');
    }
  };

  const handleToggleMonitored = async () => {
    try {
      await bookApi.updateBook(id, { monitored: !book.monitored });
      setBook({ ...book, monitored: !book.monitored });
    } catch (error) {
      console.error('Error actualizando:', error);
    }
  };

  // Build props
  const badges = [];
  if (book?.language) badges.push({ label: book.language.toUpperCase() });
  if (book?.page_count) badges.push({ label: `${book.page_count} paginas` });

  const infoGrid = [];
  if (book?.authors?.length > 0) infoGrid.push({ label: 'Autor(es)', value: book.authors.join(', ') });
  if (book?.publisher) infoGrid.push({ label: 'Editorial', value: book.publisher });
  if (book?.published_date) infoGrid.push({ label: 'Publicacion', value: book.published_date, icon: <FaCalendar /> });
  if (book?.isbn_13) infoGrid.push({ label: 'ISBN-13', value: book.isbn_13 });
  if (book?.isbn_10) infoGrid.push({ label: 'ISBN-10', value: book.isbn_10 });

  const externalLinks = [];
  if (book?.google_books_url) externalLinks.push({ label: 'Google Books', url: book.google_books_url });
  if (book?.preview_link) externalLinks.push({ label: 'Vista previa', url: book.preview_link, icon: <FaFileAlt /> });

  const actions = [];
  actions.push({
    label: book?.monitored ? '🔔 Monitoreado' : '🔕 No monitoreado',
    onClick: handleToggleMonitored,
    className: `btn ${book?.monitored ? 'bg-emerald-500 hover:bg-emerald-600 text-white' : 'btn-secondary'}`,
    tooltip: book?.monitored
      ? 'Los nuevos archivos se descargaran automaticamente'
      : 'Recibiras una notificacion cuando se encuentren nuevos archivos',
  });
  actions.push({
    label: 'Actualizar',
    onClick: handleRefresh,
    className: 'btn btn-secondary flex items-center gap-2',
    icon: <FaSync />,
  });
  actions.push({
    label: 'Eliminar',
    onClick: handleDelete,
    className: 'btn bg-red-500 hover:bg-red-600 text-white flex items-center gap-2',
    icon: <FaTrash />,
  });

  const statsCards = stats ? [
    { label: 'Total', value: stats.total_chapters },
    { label: 'Descargados', value: stats.downloaded, color: 'text-green-500' },
    { label: 'Descargando', value: stats.downloading, color: 'text-emerald-500' },
    { label: 'Pendientes', value: stats.pending, color: 'text-yellow-500' },
    { label: 'Con errores', value: stats.failed, color: 'text-red-500' },
    { label: 'Enviados a Kindle', value: stats.sent_to_kindle, color: 'text-purple-500' },
  ] : [];

  const progressData = stats && stats.total_chapters > 0
    ? { current: stats.downloaded + stats.sent_to_kindle, total: stats.total_chapters, color: '#10B981' }
    : null;

  return (
    <ContentDetailPage
      accentColor="#10B981"
      coverImage={book?.cover_image}
      title={book?.title}
      subtitles={[book?.subtitle]}
      badges={badges}
      score={book?.average_rating}
      description={book?.description}
      genres={book?.categories || []}
      infoGrid={infoGrid}
      externalLinks={externalLinks}
      actions={actions}
      stats={statsCards}
      progress={progressData}
      loading={loading}
      notFoundMessage="Libro no encontrado"
      backLink={{ to: '/books', label: 'Ir a Libros' }}
    >
      <BookChapterList bookId={id} />
    </ContentDetailPage>
  );
};

export default BookDetails;
