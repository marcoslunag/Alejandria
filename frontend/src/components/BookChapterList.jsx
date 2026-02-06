import { useState, useEffect } from 'react';
import { bookApi } from '../services/api';
import BookSendToKindleButton from './BookSendToKindleButton';
import {
  FaDownload,
  FaCheck,
  FaTimes,
  FaClock,
  FaSpinner,
  FaCheckCircle,
  FaTimesCircle,
  FaBook,
  FaExternalLinkAlt,
  FaCopy,
  FaExclamationTriangle,
  FaSortAmountDown,
  FaSortAmountUp,
  FaTabletAlt
} from 'react-icons/fa';

const BookChapterList = ({ bookId }) => {
  const [chapters, setChapters] = useState([]);
  const [selectedChapters, setSelectedChapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('asc'); // 'asc' or 'desc'

  useEffect(() => {
    loadChapters();
  }, [bookId]);

  const loadChapters = async () => {
    try {
      setLoading(true);
      const response = await bookApi.getChapters(bookId);
      setChapters(response.data);
    } catch (error) {
      console.error('Error cargando archivos:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAll = () => {
    const filteredItems = getFilteredChapters();
    const pendingItems = filteredItems.filter(c => c.status === 'pending' || c.status === 'error');

    if (selectedChapters.length === pendingItems.length) {
      setSelectedChapters([]);
    } else {
      setSelectedChapters(pendingItems.map(c => c.id));
    }
  };

  const handleToggleChapter = (chapterId) => {
    const chapter = chapters.find(c => c.id === chapterId);
    if (!chapter) return;

    if (selectedChapters.includes(chapterId)) {
      setSelectedChapters(selectedChapters.filter(id => id !== chapterId));
    } else {
      setSelectedChapters([...selectedChapters, chapterId]);
    }
  };

  const handleDownload = async () => {
    if (selectedChapters.length === 0) {
      alert('Selecciona al menos un archivo para descargar');
      return;
    }

    try {
      setDownloading(true);
      await bookApi.downloadChapters(bookId, selectedChapters);
      alert(`${selectedChapters.length} archivo(s) añadido(s) a la cola de descargas!`);
      setSelectedChapters([]);

      // Reload after a delay to show updated status
      setTimeout(loadChapters, 2000);
    } catch (error) {
      console.error('Error descargando archivos:', error);
      alert('Error al añadir archivos a la cola');
    } finally {
      setDownloading(false);
    }
  };

  const copyToClipboard = (text, chapterNumber) => {
    navigator.clipboard.writeText(text).then(() => {
      alert(`URL del archivo ${chapterNumber} copiada al portapapeles!`);
    }).catch(err => {
      console.error('Error copying to clipboard:', err);
    });
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'downloaded':
      case 'converted':
      case 'sent':
        return <FaCheckCircle className="text-green-500" />;
      case 'downloading':
      case 'converting':
        return <FaSpinner className="text-emerald-500 animate-spin" />;
      case 'pending':
        return <FaClock className="text-yellow-500" />;
      case 'error':
        return <FaTimesCircle className="text-red-500" />;
      default:
        return <FaClock className="text-gray-500" />;
    }
  };

  const getStatusText = (status) => {
    const statusMap = {
      'pending': 'Pendiente',
      'downloading': 'Descargando...',
      'downloaded': 'Descargado',
      'converting': 'Convirtiendo...',
      'converted': 'Convertido',
      'sent': 'Enviado a Kindle',
      'error': 'Error'
    };
    return statusMap[status] || status;
  };

  const handleKindleSent = (chapterId, sentAt) => {
    setChapters(prev => prev.map(c =>
      c.id === chapterId
        ? { ...c, sent_at: sentAt, status: 'sent' }
        : c
    ));
  };

  const getFilteredChapters = () => {
    let filtered = statusFilter === 'all' ? chapters : chapters.filter(c => c.status === statusFilter);

    // Sort by number
    return [...filtered].sort((a, b) => {
      if (sortOrder === 'asc') {
        return a.number - b.number;
      } else {
        return b.number - a.number;
      }
    });
  };

  const toggleSortOrder = () => {
    setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
  };

  if (loading) {
    return (
      <div className="mt-12">
        <h2 className="text-2xl font-bold mb-6">Archivos EPUB</h2>
        <div className="animate-pulse space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-12 bg-dark-lighter rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (chapters.length === 0) {
    return (
      <div className="mt-12">
        <h2 className="text-2xl font-bold mb-6">Archivos EPUB</h2>
        <div className="card p-8 text-center">
          <FaBook className="text-4xl text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">No se encontraron archivos</p>
          <p className="text-sm text-gray-500 mt-2">
            Haz clic en "Actualizar" para buscar archivos en los scrapers
          </p>
        </div>
      </div>
    );
  }

  const filteredChapters = getFilteredChapters();
  const downloadableChapters = filteredChapters.filter(c => c.status === 'pending' || c.status === 'error');

  return (
    <div className="mt-12">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Archivos EPUB ({chapters.length})</h2>

        {/* Sort and Filter */}
        <div className="flex gap-4 items-center">
          {/* Sort Order Button */}
          <button
            onClick={toggleSortOrder}
            className="flex items-center gap-2 px-4 py-2 bg-dark-lighter rounded border border-gray-700 hover:border-emerald-500 transition-colors"
            title={sortOrder === 'asc' ? 'Orden: Primeros primero' : 'Orden: Ultimos primero'}
          >
            {sortOrder === 'asc' ? (
              <>
                <FaSortAmountUp />
                <span className="text-sm">1 - {chapters.length}</span>
              </>
            ) : (
              <>
                <FaSortAmountDown />
                <span className="text-sm">{chapters.length} - 1</span>
              </>
            )}
          </button>

          {/* Filter dropdown */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-4 py-2 bg-dark-lighter rounded border border-gray-700 focus:border-emerald-500 focus:outline-none"
          >
            <option value="all">Todos los estados</option>
            <option value="pending">Pendientes</option>
            <option value="downloading">Descargando</option>
            <option value="downloaded">Descargados</option>
            <option value="error">Con errores</option>
          </select>
        </div>
      </div>

      {/* Actions */}
      {downloadableChapters.length > 0 && (
        <div className="flex gap-4 mb-4">
          <button
            onClick={handleSelectAll}
            className="btn btn-secondary flex items-center gap-2"
          >
            <FaCheck />
            {selectedChapters.length === downloadableChapters.length ? 'Deseleccionar todo' : 'Seleccionar pendientes'}
          </button>
          <button
            onClick={handleDownload}
            disabled={selectedChapters.length === 0 || downloading}
            className="btn bg-emerald-500 hover:bg-emerald-600 text-white flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {downloading ? (
              <>
                <FaSpinner className="animate-spin" />
                <span>Añadiendo...</span>
              </>
            ) : (
              <>
                <FaDownload />
                <span>Descargar seleccionados ({selectedChapters.length})</span>
              </>
            )}
          </button>
        </div>
      )}

      {/* Chapter List */}
      <div className="space-y-2">
        {filteredChapters.map((chapter) => {
          const canSelect = chapter.status === 'pending' || chapter.status === 'error';
          const isSelected = selectedChapters.includes(chapter.id);

          return (
            <div
              key={chapter.id}
              className={`flex items-center gap-4 p-4 rounded transition-colors ${
                canSelect
                  ? 'bg-dark-lighter hover:bg-dark-lighter/70 cursor-pointer'
                  : 'bg-dark-lighter/50'
              } ${isSelected ? 'ring-2 ring-emerald-500' : ''}`}
              onClick={() => canSelect && handleToggleChapter(chapter.id)}
            >
              {/* Checkbox */}
              {canSelect && (
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => handleToggleChapter(chapter.id)}
                  className="w-5 h-5 rounded border-gray-600 text-emerald-500 focus:ring-emerald-500"
                />
              )}

              {/* Status Icon */}
              <div className="flex-shrink-0">
                {getStatusIcon(chapter.status)}
              </div>

              {/* Chapter Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <span className="font-medium">
                    {chapter.title || `Volumen ${chapter.number}`}
                  </span>
                  {chapter.source && (
                    <span className="text-xs px-2 py-0.5 bg-emerald-500/20 text-emerald-400 rounded-full">
                      {chapter.source}
                    </span>
                  )}
                </div>

                {/* Download URL */}
                {chapter.download_url && (
                  <div className="flex items-center gap-2 mt-1">
                    <a
                      href={chapter.download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <FaExternalLinkAlt className="text-[10px]" />
                      <span className="truncate max-w-xs">{chapter.download_url}</span>
                    </a>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        copyToClipboard(chapter.download_url, chapter.number);
                      }}
                      className="text-gray-400 hover:text-white p-1"
                      title="Copiar URL"
                    >
                      <FaCopy className="text-xs" />
                    </button>
                  </div>
                )}

                {/* File size */}
                {chapter.file_size && (
                  <div className="text-xs text-gray-500 mt-1">
                    Tamano: {(chapter.file_size / (1024 * 1024)).toFixed(2)} MB
                  </div>
                )}

                {/* Error Message */}
                {chapter.status === 'error' && chapter.error_message && (
                  <div className="flex items-start gap-2 mt-1 text-xs text-red-400">
                    <FaExclamationTriangle className="mt-0.5 flex-shrink-0" />
                    <span>{chapter.error_message}</span>
                  </div>
                )}
              </div>

              {/* Status */}
              <div className="flex-shrink-0 flex items-center gap-3">
                <span className={`text-sm ${
                  chapter.status === 'downloaded' || chapter.status === 'sent' ? 'text-green-500' :
                  chapter.status === 'error' ? 'text-red-500' :
                  chapter.status === 'downloading' ? 'text-emerald-500' :
                  'text-gray-400'
                }`}>
                  {getStatusText(chapter.status)}
                </span>

                {/* Send to Kindle button - show for downloaded/sent */}
                {(chapter.status === 'downloaded' || chapter.status === 'sent' || chapter.file_path) && (
                  <BookSendToKindleButton
                    bookId={bookId}
                    chapterId={chapter.id}
                    sentAt={chapter.sent_at}
                    hasEpub={!!chapter.file_path}
                    onSent={handleKindleSent}
                    size="sm"
                    showLabel={false}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {filteredChapters.length === 0 && (
        <div className="card p-8 text-center">
          <p className="text-gray-400">No hay archivos que coincidan con el filtro seleccionado</p>
        </div>
      )}
    </div>
  );
};

export default BookChapterList;
