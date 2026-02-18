import { useEffect, useState, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { mangaApi, bookApi, comicApi } from '../services/api';
import SendToKindleButton from '../components/SendToKindleButton';
import BookSendToKindleButton from '../components/BookSendToKindleButton';
import ConfirmModal from '../components/ConfirmModal';
import {
  FaDownload,
  FaSync,
  FaTrash,
  FaCheckCircle,
  FaExclamationTriangle,
  FaSpinner,
  FaStop,
  FaBook,
  FaBookReader,
  FaMask,
  FaCircle,
} from 'react-icons/fa';

const Queue = () => {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [confirmAction, setConfirmAction] = useState(null);
  const [sseConnected, setSseConnected] = useState(false);
  const esRef = useRef(null);

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

  // SSE for real-time updates
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token || typeof EventSource === 'undefined') return;

    const apiBase = import.meta.env.VITE_API_URL || '/api/v1';
    const url = `${apiBase}/queue/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setSseConnected(true);
    es.onerror = () => {
      setSseConnected(false);
      es.close();
      esRef.current = null;
    };
    es.onmessage = (evt) => {
      try {
        const active = JSON.parse(evt.data);
        if (active.length > 0) loadQueue();
      } catch {}
    };

    return () => {
      es.close();
      esRef.current = null;
      setSseConnected(false);
    };
  }, [loadQueue]);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  // Polling fallback when SSE not available
  useEffect(() => {
    if (!autoRefresh || sseConnected) return;
    const interval = setInterval(loadQueue, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadQueue, sseConnected]);

  const retryDownload = async (item) => {
    try {
      if (item.content_type === 'manga') {
        await mangaApi.retryDownload(item.chapter_id);
      } else if (item.content_type === 'comic') {
        await comicApi.retryDownload(item.comic_issue_id);
      }
      loadQueue();
    } catch (error) {
      console.error('Error reintentando descarga:', error);
    }
  };

  const cancelDownload = async (item) => {
    setConfirmAction({
      title: 'Cancelar descarga',
      message: 'Cancelar esta descarga? Si forma parte de un bundle, se cancelarán todos los issues del bundle.',
      onConfirm: async () => {
        setConfirmAction(null);
        try {
          if (item.content_type === 'manga') {
            const response = await mangaApi.cancelDownload(item.chapter_id);
            if (response.data?.bundle_size > 1) {
              toast(`Se han cancelado ${response.data.bundle_size} tomos del bundle`, { icon: 'ℹ️' });
            }
          } else if (item.content_type === 'comic') {
            const response = await comicApi.cancelDownload(item.comic_issue_id);
            if (response.data?.bundle_size > 1) {
              toast(`Se han cancelado ${response.data.bundle_size} issues del bundle`, { icon: 'ℹ️' });
            }
          }
          loadQueue();
        } catch (error) {
          console.error('Error cancelando descarga:', error);
          toast.error('Error al cancelar la descarga');
        }
      },
    });
  };

  const deleteDownload = async (item) => {
    setConfirmAction({
      title: 'Eliminar archivo',
      message: '¿Eliminar este archivo descargado?',
      onConfirm: async () => {
        setConfirmAction(null);
        try {
          if (item.content_type === 'manga') {
            await mangaApi.deleteDownloadFile(item.chapter_id);
          } else if (item.content_type === 'comic') {
            await comicApi.deleteFile(item.comic_issue_id);
          }
          loadQueue();
        } catch (error) {
          console.error('Error eliminando descarga:', error);
          toast.error('Error al eliminar el archivo');
        }
      },
    });
  };

  const handleKindleSent = (chapterId, sentAt) => {
    setQueue(prev => prev.map(item =>
      (item.chapter_id === chapterId || item.book_chapter_id === chapterId || item.comic_issue_id === chapterId)
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

  const formatRetryCountdown = (nextRetryAt) => {
    if (!nextRetryAt) return null;
    const diff = new Date(nextRetryAt) - new Date();
    if (diff <= 0) return 'En breve';
    const mins = Math.round(diff / 60000);
    if (mins < 60) return `en ${mins} min`;
    return `en ${Math.round(diff / 3600000)}h`;
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
    if (item.content_type === 'comic') {
      return {
        isBook: false,
        isComic: true,
        title: item.comic_title || 'Comic',
        cover: item.comic_cover,
        detailUrl: `/comics/${item.comic_id}`,
        itemLabel: 'Issue',
        itemNumber: item.issue_number || '?',
        itemId: item.comic_issue_id,
        accentColor: 'red',
        icon: FaMask
      };
    }
    if (item.content_type === 'book') {
      return {
        isBook: true,
        isComic: false,
        title: item.book_title || 'Libro',
        cover: item.book_cover,
        detailUrl: `/books/${item.book_id}`,
        itemLabel: 'Archivo',
        itemNumber: item.chapter_number,
        itemId: item.book_chapter_id,
        accentColor: 'emerald',
        icon: FaBookReader
      };
    }
    // manga (default)
    return {
      isBook: false,
      isComic: false,
      title: item.manga_title || 'Manga',
      cover: item.manga_cover,
      detailUrl: `/manga/${item.manga_id}`,
      itemLabel: 'Tomo',
      itemNumber: item.chapter_number,
      itemId: item.chapter_id,
      accentColor: 'blue',
      icon: FaBook
    };
  };

  // Calcular stats del queue actual (solo actividad real)
  const stats = {
    downloading: queue.filter(d => d.status === 'downloading').length,
    completed: queue.filter(d => d.status === 'completed').length,
    failed: queue.filter(d => d.status === 'failed').length
  };

  // Filtrar queue por estado y tipo
  const filteredQueue = queue.filter(item => {
    if (filter !== 'all' && item.status !== filter) return false;
    if (typeFilter !== 'all' && item.content_type !== typeFilter) return false;
    return true;
  });

  // Stats por tipo
  const typeStats = {
    manga: queue.filter(d => d.content_type === 'manga').length,
    comic: queue.filter(d => d.content_type === 'comic').length,
    book: queue.filter(d => d.content_type === 'book').length,
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-4xl font-bold flex items-center gap-3">
              <FaDownload className="text-primary" />
              Cola de Descargas
              {sseConnected && (
                <span className="flex items-center gap-1.5 text-xs font-normal text-green-400 bg-green-500/10 border border-green-500/20 px-2 py-0.5 rounded-full">
                  <FaCircle className="text-[6px] animate-pulse" />
                  En vivo
                </span>
              )}
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
        <div className="card p-4 space-y-3">
          {/* Filtro por estado */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">Estado:</span>
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
          {/* Filtro por tipo */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">Tipo:</span>
            <button
              onClick={() => setTypeFilter('all')}
              className={`btn btn-sm ${typeFilter === 'all' ? 'btn-primary' : 'btn-secondary'}`}
            >
              Todos
            </button>
            <button
              onClick={() => setTypeFilter('manga')}
              className={`btn btn-sm flex items-center gap-1 ${typeFilter === 'manga' ? 'bg-blue-500 text-white' : 'btn-secondary'}`}
            >
              <FaBook className="text-xs" /> Manga {typeStats.manga > 0 && `(${typeStats.manga})`}
            </button>
            <button
              onClick={() => setTypeFilter('comic')}
              className={`btn btn-sm flex items-center gap-1 ${typeFilter === 'comic' ? 'bg-red-500 text-white' : 'btn-secondary'}`}
            >
              <FaMask className="text-xs" /> Comics {typeStats.comic > 0 && `(${typeStats.comic})`}
            </button>
            <button
              onClick={() => setTypeFilter('book')}
              className={`btn btn-sm flex items-center gap-1 ${typeFilter === 'book' ? 'bg-emerald-500 text-white' : 'btn-secondary'}`}
            >
              <FaBookReader className="text-xs" /> Libros {typeStats.book > 0 && `(${typeStats.book})`}
            </button>
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
            const ringColorMap = { emerald: 'ring-emerald-500', red: 'ring-red-500', blue: 'ring-blue-500' };
            const ringColor = item.status === 'downloading' ? (ringColorMap[info.accentColor] || 'ring-blue-500') : '';
            const badgeColorMap = { emerald: 'bg-emerald-500', red: 'bg-red-500', blue: 'bg-primary' };
            const badgeColor = badgeColorMap[info.accentColor] || 'bg-primary';

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
                    {/* Volume/Issue number badge */}
                    <div className={`absolute bottom-0 right-0 ${badgeColor} text-white text-xs font-bold px-1.5 py-0.5 rounded-tl rounded-br`}>
                      {info.isComic ? `#${info.itemNumber}` : Math.floor(info.itemNumber || 0)}
                    </div>
                    {/* Content type indicator */}
                    {(info.isBook || info.isComic) && (
                      <div className={`absolute top-0 left-0 ${badgeColor} text-white text-[8px] font-bold px-1 py-0.5 rounded-br rounded-tl`}>
                        {info.isComic ? 'COMIC' : 'LIBRO'}
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
                      <span className="text-gray-400">{info.itemLabel} {info.isComic ? `#${info.itemNumber}` : info.itemNumber}</span>
                    </div>

                    {/* Barra de progreso para downloading */}
                    {item.status === 'downloading' && (
                      <div className="mt-2">
                        <div className="w-full bg-gray-700 rounded-full h-2">
                          <div
                            className={`${info.accentColor === 'emerald' ? 'bg-emerald-500' : info.accentColor === 'red' ? 'bg-red-500' : 'bg-blue-500'} h-2 rounded-full transition-all`}
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
                    <div className="flex gap-4 text-xs text-gray-500 mt-2 flex-wrap">
                      {item.created_at && <span>Creado: {formatTime(item.created_at)}</span>}
                      {item.completed_at && item.status === 'completed' && (
                        <span>Completado: {formatTime(item.completed_at)}</span>
                      )}
                      {item.retry_count > 0 && (
                        <span className="text-yellow-500">Reintentos: {item.retry_count}</span>
                      )}
                      {item.status === 'failed' && item.next_retry_at && (() => {
                        const countdown = formatRetryCountdown(item.next_retry_at);
                        return countdown ? (
                          <span className="text-orange-400">Reintento automático: {countdown}</span>
                        ) : null;
                      })()}
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
                      ) : info.isComic ? (
                        item.comic_issue_id && (
                          <SendToKindleButton
                            chapterId={item.comic_issue_id}
                            sentAt={item.sent_at}
                            hasEpub={item.has_epub || item.converted_path}
                            onSent={handleKindleSent}
                            size="sm"
                            showLabel={true}
                            comicId={item.comic_id}
                            isComic={true}
                          />
                        )
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
                    {/* Cancelar descarga en progreso */}
                    {item.status === 'downloading' && (item.content_type === 'manga' || item.content_type === 'comic') && (
                      <button
                        onClick={() => cancelDownload(item)}
                        className="btn btn-sm bg-orange-500 hover:bg-orange-600 text-white"
                        title="Cancelar descarga"
                      >
                        <FaStop />
                        <span className="ml-1">Cancelar</span>
                      </button>
                    )}
                    {item.status === 'failed' && (item.content_type === 'manga' || item.content_type === 'comic') && (
                      <button
                        onClick={() => retryDownload(item)}
                        className="btn btn-sm btn-primary flex items-center gap-1"
                        title="Reintentar ahora (ignora el delay automático)"
                      >
                        <FaSync className="text-xs" />
                        <span>Ahora</span>
                      </button>
                    )}
                    {(item.status === 'completed' || item.status === 'failed') && (item.content_type === 'manga' || item.content_type === 'comic') && (
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
      <ConfirmModal
        isOpen={!!confirmAction}
        title={confirmAction?.title || ''}
        message={confirmAction?.message || ''}
        confirmText="Confirmar"
        onConfirm={confirmAction?.onConfirm || (() => {})}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
};

export default Queue;
