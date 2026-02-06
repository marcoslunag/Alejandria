import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { mangaApi, bookApi } from '../services/api';
import SendToKindleButton from '../components/SendToKindleButton';
import BookSendToKindleButton from '../components/BookSendToKindleButton';
import {
  FaDownload,
  FaSync,
  FaTrash,
  FaCheckCircle,
  FaExclamationTriangle,
  FaSpinner,
  FaStop,
  FaBook,
  FaBookReader
} from 'react-icons/fa';

const Queue = () => {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [autoRefresh, setAutoRefresh] = useState(true);

  const loadQueue = useCallback(async () => {
    try {
      const response = await mangaApi.getQueue();
      setQueue(response.data);
    } catch (error) {
      console.error('Error cargando cola:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(loadQueue, 3000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadQueue]);

  const retryDownload = async (item) => {
    try {
      // For now, retry only works for manga
      if (item.content_type === 'manga') {
        await mangaApi.retryDownload(item.chapter_id);
      }
      loadQueue();
    } catch (error) {
      console.error('Error reintentando descarga:', error);
    }
  };

  const cancelDownload = async (item) => {
    if (!confirm('Cancelar esta descarga? Si forma parte de un bundle, se cancelaran todos los tomos del bundle.')) return;
    try {
      if (item.content_type === 'manga') {
        const response = await mangaApi.cancelDownload(item.chapter_id);
        if (response.data?.bundle_size > 1) {
          alert(`Se han cancelado ${response.data.bundle_size} tomos del bundle.`);
        }
      }
      // For books, we'd need a similar endpoint
      loadQueue();
    } catch (error) {
      console.error('Error cancelando descarga:', error);
    }
  };

  const deleteDownload = async (item) => {
    if (!confirm('Eliminar este archivo descargado?')) return;
    try {
      if (item.content_type === 'manga') {
        await mangaApi.deleteDownloadFile(item.chapter_id);
      }
      // For books, we'd need a similar endpoint
      loadQueue();
    } catch (error) {
      console.error('Error eliminando descarga:', error);
    }
  };

  const handleKindleSent = (chapterId, sentAt) => {
    setQueue(prev => prev.map(item =>
      (item.chapter_id === chapterId || item.book_chapter_id === chapterId)
        ? { ...item, sent_at: sentAt }
        : item
    ));
  };

  const formatTime = (date) => {
    if (!date) return '-';
    return new Date(date).toLocaleString('es-ES', {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit'
    });
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'downloading':
        return <FaSpinner className="animate-spin text-blue-500" />;
      case 'completed':
        return <FaCheckCircle className="text-green-500" />;
      case 'failed':
        return <FaExclamationTriangle className="text-red-500" />;
      default:
        return <FaDownload className="text-gray-500" />;
    }
  };

  const getStatusText = (status) => {
    const map = {
      'downloading': 'Descargando',
      'completed': 'Completado',
      'failed': 'Error'
    };
    return map[status] || status;
  };

  // Helper to get item display info
  const getItemInfo = (item) => {
    const isBook = item.content_type === 'book';
    return {
      isBook,
      title: isBook ? (item.book_title || 'Libro') : (item.manga_title || 'Manga'),
      cover: isBook ? item.book_cover : item.manga_cover,
      detailUrl: isBook ? `/books/${item.book_id}` : `/manga/${item.manga_id}`,
      itemLabel: isBook ? 'Archivo' : 'Tomo',
      itemId: isBook ? item.book_chapter_id : item.chapter_id,
      accentColor: isBook ? 'emerald' : 'blue',
      icon: isBook ? FaBookReader : FaBook
    };
  };

  // Calcular stats del queue actual (solo actividad real)
  const stats = {
    downloading: queue.filter(d => d.status === 'downloading').length,
    completed: queue.filter(d => d.status === 'completed').length,
    failed: queue.filter(d => d.status === 'failed').length
  };

  // Filtrar queue
  const filteredQueue = filter === 'all'
    ? queue
    : queue.filter(item => item.status === filter);

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-4xl font-bold flex items-center gap-3">
              <FaDownload className="text-primary" />
              Cola de Descargas
            </h1>
            <p className="text-gray-400 mt-2">
              Monitoriza el estado de tus descargas
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="w-4 h-4 rounded border-gray-600 text-primary focus:ring-primary"
              />
              Auto-actualizar
            </label>
            <button
              onClick={loadQueue}
              className="btn btn-secondary flex items-center gap-2"
              disabled={loading}
            >
              <FaSync className={loading ? 'animate-spin' : ''} />
              Actualizar
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="card p-4 border-l-4 border-blue-500">
            <div className="flex items-center gap-3">
              <FaSpinner className={`text-blue-500 text-xl ${stats.downloading > 0 ? 'animate-spin' : ''}`} />
              <div>
                <p className="text-gray-400 text-sm">Descargando</p>
                <p className="text-2xl font-bold">{stats.downloading}</p>
              </div>
            </div>
          </div>
          <div className="card p-4 border-l-4 border-green-500">
            <div className="flex items-center gap-3">
              <FaCheckCircle className="text-green-500 text-xl" />
              <div>
                <p className="text-gray-400 text-sm">Completados</p>
                <p className="text-2xl font-bold">{stats.completed}</p>
              </div>
            </div>
          </div>
          <div className="card p-4 border-l-4 border-red-500">
            <div className="flex items-center gap-3">
              <FaExclamationTriangle className="text-red-500 text-xl" />
              <div>
                <p className="text-gray-400 text-sm">Con Error</p>
                <p className="text-2xl font-bold">{stats.failed}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Filtros */}
        <div className="card p-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">Filtrar:</span>
            {['all', 'downloading', 'completed', 'failed'].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`}
              >
                {f === 'all' ? 'Todas' : getStatusText(f)}
                {f !== 'all' && ` (${stats[f]})`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Lista */}
      {loading && queue.length === 0 ? (
        <div className="text-center py-20">
          <FaSpinner className="text-4xl text-primary animate-spin mx-auto mb-4" />
          <p className="text-gray-400">Cargando cola de descargas...</p>
        </div>
      ) : filteredQueue.length === 0 ? (
        <div className="text-center py-20">
          <FaDownload className="text-6xl text-gray-600 mx-auto mb-4" />
          <h3 className="text-2xl font-bold mb-2">
            {filter === 'all' ? 'Cola vacia' : `Sin descargas "${getStatusText(filter)}"`}
          </h3>
          <p className="text-gray-400 mb-6">
            {filter === 'all'
              ? 'No hay descargas activas. Selecciona tomos desde un manga o libro para descargar.'
              : 'No hay descargas con este estado.'
            }
          </p>
          <Link to="/library" className="btn btn-primary">
            Ir a la Biblioteca
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredQueue.map((item) => {
            const info = getItemInfo(item);
            const IconComponent = info.icon;
            const ringColor = item.status === 'downloading'
              ? (info.isBook ? 'ring-emerald-500' : 'ring-blue-500')
              : '';
            const badgeColor = info.isBook ? 'bg-emerald-500' : 'bg-primary';

            return (
              <div
                key={item.id}
                className={`card p-4 transition-all ${
                  item.status === 'downloading' ? `ring-2 ${ringColor}` : ''
                }`}
              >
                <div className="flex items-center gap-4">
                  {/* Cover with volume number overlay */}
                  <div className="relative w-14 h-20 flex-shrink-0">
                    {info.cover ? (
                      <img
                        src={info.cover}
                        alt={info.title}
                        className="w-full h-full object-cover rounded"
                      />
                    ) : (
                      <div className="w-full h-full bg-gray-700 rounded flex items-center justify-center">
                        <IconComponent className={`text-gray-500 ${info.isBook ? 'text-emerald-500/50' : ''}`} />
                      </div>
                    )}
                    {/* Volume number badge */}
                    <div className={`absolute bottom-0 right-0 ${badgeColor} text-white text-xs font-bold px-1.5 py-0.5 rounded-tl rounded-br`}>
                      {Math.floor(item.chapter_number)}
                    </div>
                    {/* Content type indicator */}
                    {info.isBook && (
                      <div className="absolute top-0 left-0 bg-emerald-500 text-white text-[8px] font-bold px-1 py-0.5 rounded-br rounded-tl">
                        LIBRO
                      </div>
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {getStatusIcon(item.status)}
                      <Link
                        to={info.detailUrl}
                        className={`font-bold hover:${info.isBook ? 'text-emerald-400' : 'text-primary'} truncate`}
                      >
                        {info.title}
                      </Link>
                      <span className="text-gray-500">-</span>
                      <span className="text-gray-400">{info.itemLabel} {item.chapter_number}</span>
                    </div>

                    {/* Barra de progreso para downloading */}
                    {item.status === 'downloading' && (
                      <div className="mt-2">
                        <div className="w-full bg-gray-700 rounded-full h-2">
                          <div
                            className={`${info.isBook ? 'bg-emerald-500' : 'bg-blue-500'} h-2 rounded-full transition-all`}
                            style={{ width: `${item.progress || 0}%` }}
                          />
                        </div>
                        <p className="text-xs text-gray-500 mt-1">{item.progress || 0}%</p>
                      </div>
                    )}

                    {/* Error */}
                    {item.status === 'failed' && item.error_message && (
                      <p className="text-red-400 text-sm mt-1">{item.error_message}</p>
                    )}

                    {/* Tiempo */}
                    <div className="flex gap-4 text-xs text-gray-500 mt-2">
                      {item.created_at && <span>Creado: {formatTime(item.created_at)}</span>}
                      {item.completed_at && item.status === 'completed' && (
                        <span>Completado: {formatTime(item.completed_at)}</span>
                      )}
                      {item.retry_count > 0 && (
                        <span className="text-yellow-500">Reintentos: {item.retry_count}</span>
                      )}
                    </div>
                  </div>

                  {/* Acciones */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {/* Send to Kindle button for completed downloads */}
                    {item.status === 'completed' && (
                      info.isBook ? (
                        <BookSendToKindleButton
                          bookId={item.book_id}
                          chapterId={item.book_chapter_id}
                          sentAt={item.sent_at}
                          hasEpub={item.has_epub || item.file_path}
                          onSent={handleKindleSent}
                          size="sm"
                          showLabel={true}
                        />
                      ) : (
                        item.chapter_id && (
                          <SendToKindleButton
                            chapterId={item.chapter_id}
                            sentAt={item.sent_at}
                            hasEpub={item.has_epub || item.converted_path}
                            onSent={handleKindleSent}
                            size="sm"
                            showLabel={true}
                          />
                        )
                      )
                    )}
                    {/* Cancelar descarga en progreso - solo para manga por ahora */}
                    {item.status === 'downloading' && item.content_type === 'manga' && (
                      <button
                        onClick={() => cancelDownload(item)}
                        className="btn btn-sm bg-orange-500 hover:bg-orange-600 text-white"
                        title="Cancelar descarga"
                      >
                        <FaStop />
                        <span className="ml-1">Cancelar</span>
                      </button>
                    )}
                    {item.status === 'failed' && item.content_type === 'manga' && (
                      <button
                        onClick={() => retryDownload(item)}
                        className="btn btn-sm btn-primary"
                        title="Reintentar"
                      >
                        <FaSync />
                      </button>
                    )}
                    {(item.status === 'completed' || item.status === 'failed') && item.content_type === 'manga' && (
                      <button
                        onClick={() => deleteDownload(item)}
                        className="btn btn-sm bg-red-500 hover:bg-red-600 text-white"
                        title="Eliminar archivo"
                      >
                        <FaTrash />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Queue;
