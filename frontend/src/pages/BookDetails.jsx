import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { bookApi } from '../services/api';
import BookChapterList from '../components/BookChapterList';
import {
  FaStar,
  FaBookReader,
  FaCalendar,
  FaTrash,
  FaSync,
  FaExternalLinkAlt,
  FaGlobe,
  FaFileAlt,
  FaBook,
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

  if (!book) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <p className="text-gray-400">Libro no encontrado</p>
        <Link to="/books" className="btn bg-emerald-500 hover:bg-emerald-600 text-white mt-4 inline-block">
          Ir a Libros
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Banner - use cover as banner with blur effect if no specific banner */}
      {book.cover_image && (
        <div
          className="w-full h-64 bg-cover bg-center relative"
          style={{
            backgroundImage: `url(${book.cover_image})`,
            filter: 'blur(0px)'
          }}
        >
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{
              backgroundImage: `url(${book.cover_image})`,
              filter: 'blur(8px)',
              transform: 'scale(1.1)'
            }}
          />
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-dark/50 to-dark" />
        </div>
      )}

      <div className="container mx-auto px-4 pb-8" style={{ marginTop: book.cover_image ? '-8rem' : '2rem' }}>
        <div className="flex flex-col md:flex-row gap-8">
          {/* Cover */}
          <div className="flex-shrink-0">
            {book.cover_image ? (
              <img
                src={book.cover_image}
                alt={book.title}
                className="w-64 rounded-lg shadow-2xl"
                style={{ borderTop: '4px solid #10B981' }}
              />
            ) : (
              <div
                className="w-64 h-96 rounded-lg shadow-2xl bg-dark-lighter flex items-center justify-center"
                style={{ borderTop: '4px solid #10B981' }}
              >
                <FaBookReader className="text-6xl text-gray-600" />
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1">
            {/* Title */}
            <h1 className="text-4xl font-bold mb-2">{book.title}</h1>
            {book.subtitle && (
              <p className="text-xl text-gray-400 mb-4">{book.subtitle}</p>
            )}

            {/* Meta */}
            <div className="flex flex-wrap gap-4 mb-6">
              {book.average_rating && (
                <div className="flex items-center gap-2">
                  <FaStar className="text-yellow-400" />
                  <span className="font-bold">{book.average_rating.toFixed(1)}</span>
                  {book.ratings_count && (
                    <span className="text-gray-400 text-sm">({book.ratings_count})</span>
                  )}
                </div>
              )}
              {book.language && (
                <span className="px-3 py-1 bg-dark-lighter rounded">{book.language.toUpperCase()}</span>
              )}
              {book.page_count && (
                <span className="px-3 py-1 bg-dark-lighter rounded">{book.page_count} paginas</span>
              )}
            </div>

            {/* Categories */}
            {book.categories && book.categories.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-6">
                {book.categories.map((category, idx) => (
                  <span key={idx} className="px-3 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-sm">
                    {category}
                  </span>
                ))}
              </div>
            )}

            {/* Description */}
            {book.description && (
              <div className="mb-6">
                <h3 className="text-lg font-bold mb-2">Descripcion</h3>
                <p className="text-gray-300 leading-relaxed">
                  {book.description.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '')}
                </p>
              </div>
            )}

            {/* Additional Info */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
              {book.authors && book.authors.length > 0 && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Autor(es)</p>
                  <p className="font-medium">{book.authors.join(', ')}</p>
                </div>
              )}
              {book.publisher && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Editorial</p>
                  <p className="font-medium">{book.publisher}</p>
                </div>
              )}
              {book.published_date && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Publicacion</p>
                  <p className="flex items-center gap-2">
                    <FaCalendar />
                    {book.published_date}
                  </p>
                </div>
              )}
              {book.isbn_13 && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">ISBN-13</p>
                  <p className="font-medium text-sm">{book.isbn_13}</p>
                </div>
              )}
              {book.isbn_10 && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">ISBN-10</p>
                  <p className="font-medium text-sm">{book.isbn_10}</p>
                </div>
              )}
            </div>

            {/* External Links */}
            <div className="flex gap-4 mb-6">
              {book.google_books_url && (
                <a
                  href={book.google_books_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <FaExternalLinkAlt />
                  Google Books
                </a>
              )}
              {book.preview_link && (
                <a
                  href={book.preview_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary flex items-center gap-2"
                >
                  <FaFileAlt />
                  Vista previa
                </a>
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-wrap gap-4">
              <div className="relative group">
                <button
                  onClick={handleToggleMonitored}
                  className={`btn ${book.monitored ? 'bg-emerald-500 hover:bg-emerald-600 text-white' : 'btn-secondary'}`}
                >
                  {book.monitored ? '🔔 Monitoreado' : '🔕 No monitoreado'}
                </button>
                <div className="absolute bottom-full left-0 mb-2 hidden group-hover:block bg-dark-lighter text-sm text-gray-300 p-2 rounded shadow-lg w-64 z-10">
                  {book.monitored
                    ? 'Los nuevos archivos se descargaran automaticamente'
                    : 'Recibiras una notificacion cuando se encuentren nuevos archivos'}
                </div>
              </div>
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
            <h2 className="text-2xl font-bold mb-6">Estadisticas de Descarga</h2>
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
                <p className="text-2xl font-bold text-emerald-500">{stats.downloading}</p>
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
                    className="bg-emerald-500 h-3 rounded-full transition-all"
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
        <BookChapterList bookId={id} />
      </div>
    </div>
  );
};

export default BookDetails;
