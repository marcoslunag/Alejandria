import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { mangaApi } from '../services/api';
import { sanitizeUrl } from '../utils/sanitizeUrl';
import SendToKindleButton from './SendToKindleButton';
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
  FaTabletAlt,
  FaEye
} from 'react-icons/fa';

const ChapterList = ({ mangaId }) => {
  const navigate = useNavigate();
  const [tomos, setTomos] = useState([]);
  const [selectedTomos, setSelectedTomos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('asc'); // 'asc' or 'desc'

  useEffect(() => {
    loadTomos();
  }, [mangaId]);

  const loadTomos = async () => {
    try {
      setLoading(true);
      const response = await mangaApi.getChapters(mangaId);
      setTomos(response.data);
    } catch (error) {
      console.error('Error cargando tomos:', error);
    } finally {
      setLoading(false);
    }
  };

  // Polling inteligente: refresca cada 5s mientras haya descargas activas
  useEffect(() => {
    const hasActive = tomos.some(t => ['downloading', 'converting'].includes(t.status));
    if (!hasActive) return;
    const interval = setInterval(loadTomos, 5000);
    return () => clearInterval(interval);
  }, [tomos]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelectAll = () => {
    const filteredItems = getFilteredTomos();
    const pendingItems = filteredItems.filter(t => t.status === 'pending' || t.status === 'error');

    if (selectedTomos.length === pendingItems.length) {
      setSelectedTomos([]);
    } else {
      setSelectedTomos(pendingItems.map(t => t.id));
    }
  };

  const handleToggleTomo = (tomoId) => {
    // Encontrar el tomo seleccionado
    const tomo = tomos.find(t => t.id === tomoId);
    if (!tomo) return;

    // Encontrar todos los tomos que comparten la misma download_url (bundle)
    const bundledTomos = tomo.download_url
      ? tomos.filter(t =>
          t.download_url === tomo.download_url &&
          (t.status === 'pending' || t.status === 'error')
        )
      : [tomo];

    const bundledIds = bundledTomos.map(t => t.id);

    if (selectedTomos.includes(tomoId)) {
      // Deseleccionar todos los del bundle
      setSelectedTomos(selectedTomos.filter(id => !bundledIds.includes(id)));
    } else {
      // Seleccionar todos los del bundle
      const newSelection = [...new Set([...selectedTomos, ...bundledIds])];
      setSelectedTomos(newSelection);
    }
  };

  const handleDownload = async () => {
    if (selectedTomos.length === 0) {
      toast.error('Selecciona al menos un tomo para descargar');
      return;
    }

    try {
      setDownloading(true);
      await mangaApi.downloadChapters(mangaId, selectedTomos);
      toast.success(`${selectedTomos.length} tomo(s) añadido(s) a la cola`);
      setSelectedTomos([]);
      setTimeout(loadTomos, 2000);
    } catch (error) {
      console.error('Error descargando tomos:', error);
      toast.error('Error al añadir tomos a la cola');
    } finally {
      setDownloading(false);
    }
  };

  const handleDownloadAll = async () => {
    const allPending = tomos.filter(t => t.status === 'pending' || t.status === 'error');
    if (allPending.length === 0) return;
    try {
      setDownloading(true);
      await mangaApi.downloadChapters(mangaId, allPending.map(t => t.id));
      toast.success(`${allPending.length} tomo(s) añadido(s) a la cola`);
      setSelectedTomos([]);
      setTimeout(loadTomos, 2000);
    } catch (error) {
      console.error('Error descargando todos:', error);
      toast.error('Error al añadir tomos a la cola');
    } finally {
      setDownloading(false);
    }
  };

  const copyToClipboard = (text, tomoNumber) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success(`URL del Tomo ${tomoNumber} copiada`);
    }).catch(err => {
      console.error('Error copying to clipboard:', err);
      toast.error('Error al copiar URL');
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
        return <FaSpinner className="text-blue-500 animate-spin" />;
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
    setTomos(prev => prev.map(t =>
      t.id === chapterId
        ? { ...t, sent_at: sentAt, status: 'sent' }
        : t
    ));
  };

  const handleMarkRead = async (tomoId) => {
    try {
      await mangaApi.markChapterRead(mangaId, tomoId);
      setTomos(prev => prev.map(t =>
        t.id === tomoId ? { ...t, read_at: new Date().toISOString() } : t
      ));
    } catch (error) {
      console.error('Error marcando como leído:', error);
      toast.error('Error al marcar como leído');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await mangaApi.markAllRead(mangaId);
      const now = new Date().toISOString();
      setTomos(prev => prev.map(t =>
        ['sent', 'converted', 'downloaded'].includes(t.status) ? { ...t, read_at: now } : t
      ));
      toast.success('Todos los tomos marcados como leídos');
    } catch (error) {
      console.error('Error marcando todos como leídos:', error);
      toast.error('Error al marcar todos como leídos');
    }
  };

  const getFilteredTomos = () => {
    let filtered = statusFilter === 'all' ? tomos : tomos.filter(t => t.status === statusFilter);

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
        <h2 className="text-2xl font-bold mb-6">Tomos</h2>
        <div className="animate-pulse space-y-2">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="h-12 bg-dark-lighter rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (tomos.length === 0) {
    return (
      <div className="mt-12">
        <h2 className="text-2xl font-bold mb-6">Tomos</h2>
        <div className="card p-8 text-center">
          <FaBook className="text-4xl text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">No se encontraron tomos</p>
          <p className="text-sm text-gray-500 mt-2">
            Haz clic en "Actualizar" para obtener tomos de la fuente
          </p>
        </div>
      </div>
    );
  }

  const filteredTomos = getFilteredTomos();
  const downloadableTomos = filteredTomos.filter(t => t.status === 'pending' || t.status === 'error');
  const readableTomos = tomos.filter(t => ['sent', 'converted', 'downloaded'].includes(t.status) && !t.read_at);

  return (
    <div className="mt-12">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Tomos ({tomos.length})</h2>

        {/* Sort and Filter */}
        <div className="flex gap-4 items-center">
          {/* Sort Order Button */}
          <button
            onClick={toggleSortOrder}
            className="flex items-center gap-2 px-4 py-2 bg-dark-lighter rounded border border-gray-700 hover:border-primary transition-colors"
            title={sortOrder === 'asc' ? 'Orden: Primeros primero' : 'Orden: Últimos primero'}
          >
            {sortOrder === 'asc' ? (
              <>
                <FaSortAmountUp />
                <span className="text-sm">1 → {tomos.length}</span>
              </>
            ) : (
              <>
                <FaSortAmountDown />
                <span className="text-sm">{tomos.length} → 1</span>
              </>
            )}
          </button>

          {/* Filter dropdown */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-4 py-2 bg-dark-lighter rounded border border-gray-700 focus:border-primary focus:outline-none"
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
      <div className="flex gap-4 mb-4 flex-wrap">
        {downloadableTomos.length > 0 && (<>
          <button
            onClick={handleSelectAll}
            className="btn btn-secondary flex items-center gap-2"
          >
            <FaCheck />
            {selectedTomos.length === downloadableTomos.length ? 'Deseleccionar todo' : 'Seleccionar pendientes'}
          </button>
          <button
            onClick={handleDownload}
            disabled={selectedTomos.length === 0 || downloading}
            className="btn btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {downloading ? (
              <>
                <FaSpinner className="animate-spin" />
                <span>Añadiendo...</span>
              </>
            ) : (
              <>
                <FaDownload />
                <span>Descargar seleccionados ({selectedTomos.length})</span>
              </>
            )}
          </button>
          <button
            onClick={handleDownloadAll}
            disabled={downloading}
            className="btn btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed bg-blue-700 hover:bg-blue-600"
          >
            {downloading ? (
              <>
                <FaSpinner className="animate-spin" />
                <span>Añadiendo...</span>
              </>
            ) : (
              <>
                <FaDownload />
                <span>Descargar todos ({downloadableTomos.length})</span>
              </>
            )}
          </button>
        </>)}
        {readableTomos.length > 0 && (
          <button
            onClick={handleMarkAllRead}
            className="btn btn-secondary flex items-center gap-2 text-green-400 hover:text-green-300"
          >
            <FaEye />
            <span>Marcar todos como leídos ({readableTomos.length})</span>
          </button>
        )}
      </div>

      {/* Tomo List */}
      <div className="space-y-2">
        {filteredTomos.map((tomo) => {
          const canSelect = tomo.status === 'pending' || tomo.status === 'error';
          const isSelected = selectedTomos.includes(tomo.id);
          
          // Verificar si este tomo está en un bundle con otros seleccionados
          const isBundled = tomo.download_url && tomos.some(t => 
            t.id !== tomo.id && 
            t.download_url === tomo.download_url &&
            selectedTomos.includes(t.id)
          );
          
          // Contar cuántos tomos comparten esta URL
          const bundleCount = tomo.download_url 
            ? tomos.filter(t => t.download_url === tomo.download_url).length 
            : 1;

          return (
            <div
              key={tomo.id}
              className={`flex items-center gap-4 p-4 rounded transition-colors ${
                canSelect
                  ? 'bg-dark-lighter hover:bg-dark-lighter/70 cursor-pointer'
                  : 'bg-dark-lighter/50'
              } ${isSelected ? 'ring-2 ring-primary' : ''} ${isBundled && !isSelected ? 'ring-2 ring-primary/50 bg-primary/10' : ''}`}
              onClick={() => canSelect && handleToggleTomo(tomo.id)}
            >
              {/* Checkbox */}
              {canSelect && (
                <input
                  type="checkbox"
                  checked={isSelected || isBundled}
                  onChange={() => handleToggleTomo(tomo.id)}
                  className={`w-5 h-5 rounded border-gray-600 text-primary focus:ring-primary ${isBundled && !isSelected ? 'opacity-50' : ''}`}
                />
              )}

              {/* Status Icon */}
              <div className="flex-shrink-0">
                {getStatusIcon(tomo.status)}
              </div>

              {/* Tomo Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <span className="font-medium">Tomo {tomo.number}</span>
                  {tomo.title && (
                    <span className="text-gray-400 truncate">{tomo.title}</span>
                  )}
                  {bundleCount > 1 && (
                    <span className="text-xs px-2 py-0.5 bg-primary/20 text-primary rounded-full">
                      Bundle ({bundleCount} tomos)
                    </span>
                  )}
                </div>

                {/* Download URL */}
                {tomo.download_url && (
                  <div className="flex items-center gap-2 mt-1">
                    <a
                      href={sanitizeUrl(tomo.download_url)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary hover:text-primary-light flex items-center gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <FaExternalLinkAlt className="text-[10px]" />
                      <span className="truncate max-w-xs">{tomo.download_url}</span>
                    </a>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        copyToClipboard(tomo.download_url, tomo.number);
                      }}
                      className="text-gray-400 hover:text-white p-1"
                      title="Copiar URL"
                    >
                      <FaCopy className="text-xs" />
                    </button>
                  </div>
                )}

                {/* Error Message */}
                {tomo.status === 'error' && tomo.error_message && (
                  <div className="flex items-start gap-2 mt-1 text-xs text-red-400">
                    <FaExclamationTriangle className="mt-0.5 flex-shrink-0" />
                    <span>{tomo.error_message}</span>
                  </div>
                )}
              </div>

              {/* Status */}
              <div className="flex-shrink-0 flex items-center gap-2">
                <span className={`text-sm ${
                  tomo.status === 'downloaded' || tomo.status === 'sent' ? 'text-green-500' :
                  tomo.status === 'error' ? 'text-red-500' :
                  tomo.status === 'downloading' ? 'text-blue-500' :
                  'text-gray-400'
                }`}>
                  {getStatusText(tomo.status)}
                </span>

                {/* Read indicator / mark-read button */}
                {['downloaded', 'converted', 'sent'].includes(tomo.status) && (
                  tomo.read_at ? (
                    <span title={`Leído`} className="text-green-400">
                      <FaEye className="text-sm" />
                    </span>
                  ) : (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleMarkRead(tomo.id); }}
                      title="Marcar como leído"
                      className="text-gray-500 hover:text-green-400 transition-colors"
                    >
                      <FaEye className="text-sm" />
                    </button>
                  )
                )}

                {/* Read button - show for downloaded chapters */}
                {['downloaded', 'converting', 'converted', 'sent'].includes(tomo.status) && (
                  <button
                    onClick={() => navigate(`/manga/${mangaId}/chapters/${tomo.id}/read`)}
                    title="Leer en línea"
                    className="p-1.5 rounded text-purple-400 hover:text-purple-300 hover:bg-purple-900/30 transition-colors"
                  >
                    <FaBook className="text-sm" />
                  </button>
                )}

                {/* Send to Kindle button - show for converted/sent */}
                {(tomo.status === 'converted' || tomo.status === 'sent' || tomo.converted_path) && (
                  <SendToKindleButton
                    chapterId={tomo.id}
                    sentAt={tomo.sent_at}
                    hasEpub={!!tomo.converted_path}
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

      {filteredTomos.length === 0 && (
        <div className="card p-8 text-center">
          <p className="text-gray-400">No hay tomos que coincidan con el filtro seleccionado</p>
        </div>
      )}
    </div>
  );
};

export default ChapterList;
