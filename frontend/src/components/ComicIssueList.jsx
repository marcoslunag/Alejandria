import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { comicApi } from '../services/api';
import ComicSendToKindleButton from './ComicSendToKindleButton';
import {
  FaDownload,
  FaCheck,
  FaTimes,
  FaClock,
  FaSpinner,
  FaCheckCircle,
  FaTimesCircle,
  FaMask,
  FaExternalLinkAlt,
  FaCopy,
  FaExclamationTriangle,
  FaSortAmountDown,
  FaSortAmountUp,
  FaTabletAlt,
  FaBox,
  FaLink,
  FaLock
} from 'react-icons/fa';

const ComicIssueList = ({ comicId }) => {
  const [issues, setIssues] = useState([]);
  const [selectedIssues, setSelectedIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('asc'); // 'asc' or 'desc'

  useEffect(() => {
    loadIssues();
  }, [comicId]);

  const loadIssues = async () => {
    try {
      setLoading(true);
      const response = await comicApi.getIssues(comicId);
      setIssues(response.data);
    } catch (error) {
      console.error('Error cargando issues:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAll = () => {
    const filteredItems = getFilteredIssues();
    // Only select issues that have download_url and are pending/error
    const downloadableItems = filteredItems.filter(i =>
      (i.status === 'pending' || i.status === 'error') && i.download_url
    );

    if (selectedIssues.length === downloadableItems.length) {
      setSelectedIssues([]);
    } else {
      setSelectedIssues(downloadableItems.map(i => i.id));
    }
  };

  const handleToggleIssue = (issueId) => {
    const issue = issues.find(i => i.id === issueId);
    if (!issue) return;

    // Find all issues in the same bundle (by bundle_id or same download_url)
    const bundledIssues = issue.download_url
      ? issues.filter(i =>
          ((issue.bundle_id && i.bundle_id === issue.bundle_id) ||
           (!issue.bundle_id && i.download_url === issue.download_url)) &&
          (i.status === 'pending' || i.status === 'error')
        )
      : [issue];

    const bundledIds = bundledIssues.map(i => i.id);

    if (selectedIssues.includes(issueId)) {
      // Deselect all in bundle
      setSelectedIssues(selectedIssues.filter(id => !bundledIds.includes(id)));
    } else {
      // Select all in bundle
      const newSelection = [...new Set([...selectedIssues, ...bundledIds])];
      setSelectedIssues(newSelection);
    }
  };

  const handleDownload = async () => {
    if (selectedIssues.length === 0) {
      toast.error('Selecciona al menos un issue para descargar');
      return;
    }

    try {
      setDownloading(true);
      await comicApi.downloadIssues(comicId, selectedIssues);
      toast.success(`${selectedIssues.length} issue(s) añadido(s) a la cola`);
      setSelectedIssues([]);
      setTimeout(loadIssues, 2000);
    } catch (error) {
      console.error('Error descargando issues:', error);
      toast.error('Error al añadir issues a la cola');
    } finally {
      setDownloading(false);
    }
  };

  const copyToClipboard = (text, issueNumber) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success(`URL del issue #${issueNumber} copiada`);
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
        return <FaSpinner className="text-red-500 animate-spin" />;
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

  const handleKindleSent = (issueId, sentAt) => {
    setIssues(prev => prev.map(i =>
      i.id === issueId
        ? { ...i, sent_at: sentAt, status: 'sent' }
        : i
    ));
  };

  const getFilteredIssues = () => {
    let filtered = statusFilter === 'all' ? issues : issues.filter(i => i.status === statusFilter);

    // Sort by issue number
    return [...filtered].sort((a, b) => {
      if (sortOrder === 'asc') {
        return (a.issue_number || 0) - (b.issue_number || 0);
      } else {
        return (b.issue_number || 0) - (a.issue_number || 0);
      }
    });
  };

  const toggleSortOrder = () => {
    setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
  };

  if (loading) {
    return (
      <div className="mt-12">
        <h2 className="text-2xl font-bold mb-6">Issues</h2>
        <div className="animate-pulse space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-12 bg-dark-lighter rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (issues.length === 0) {
    return (
      <div className="mt-12">
        <h2 className="text-2xl font-bold mb-6">Issues</h2>
        <div className="card p-8 text-center">
          <FaMask className="text-4xl text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">No se encontraron issues</p>
          <p className="text-sm text-gray-500 mt-2">
            Haz clic en "Buscar fuentes" para encontrar links de descarga
          </p>
        </div>
      </div>
    );
  }

  const filteredIssues = getFilteredIssues();
  // Only issues with download_url can be downloaded
  const downloadableIssues = filteredIssues.filter(i =>
    (i.status === 'pending' || i.status === 'error') && i.download_url
  );

  return (
    <div className="mt-12">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Issues ({issues.length})</h2>

        {/* Sort and Filter */}
        <div className="flex gap-4 items-center">
          {/* Sort Order Button */}
          <button
            onClick={toggleSortOrder}
            className="flex items-center gap-2 px-4 py-2 bg-dark-lighter rounded border border-gray-700 hover:border-red-500 transition-colors"
            title={sortOrder === 'asc' ? 'Orden: Primeros primero' : 'Orden: Ultimos primero'}
          >
            {sortOrder === 'asc' ? (
              <>
                <FaSortAmountUp />
                <span className="text-sm">1 - {issues.length}</span>
              </>
            ) : (
              <>
                <FaSortAmountDown />
                <span className="text-sm">{issues.length} - 1</span>
              </>
            )}
          </button>

          {/* Filter dropdown */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-4 py-2 bg-dark-lighter rounded border border-gray-700 focus:border-red-500 focus:outline-none"
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
      {downloadableIssues.length > 0 && (
        <div className="flex gap-4 mb-4">
          <button
            onClick={handleSelectAll}
            className="btn btn-secondary flex items-center gap-2"
          >
            <FaCheck />
            {selectedIssues.length === downloadableIssues.length ? 'Deseleccionar todo' : 'Seleccionar pendientes'}
          </button>
          <button
            onClick={handleDownload}
            disabled={selectedIssues.length === 0 || downloading}
            className="btn bg-red-500 hover:bg-red-600 text-white flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {downloading ? (
              <>
                <FaSpinner className="animate-spin" />
                <span>Anadiendo...</span>
              </>
            ) : (
              <>
                <FaDownload />
                <span>Descargar seleccionados ({selectedIssues.length})</span>
              </>
            )}
          </button>
        </div>
      )}

      {/* Issue List */}
      <div className="space-y-2">
        {filteredIssues.map((issue) => {
          // Can only select if has download_url AND status is pending/error
          const canSelect = (issue.status === 'pending' || issue.status === 'error') && issue.download_url;
          const isSelected = selectedIssues.includes(issue.id);

          // Check if this issue is in a bundle with other selected issues
          const isBundled = issue.download_url && issues.some(i =>
            i.id !== issue.id &&
            ((issue.bundle_id && i.bundle_id === issue.bundle_id) ||
             (!issue.bundle_id && i.download_url === issue.download_url)) &&
            selectedIssues.includes(i.id)
          );

          // Count how many issues share this bundle/URL
          const bundleCount = issue.download_url
            ? issues.filter(i =>
                (issue.bundle_id && i.bundle_id === issue.bundle_id) ||
                (!issue.bundle_id && i.download_url === issue.download_url)
              ).length
            : 1;

          return (
            <div
              key={issue.id}
              className={`flex items-center gap-4 p-4 rounded transition-colors ${
                canSelect
                  ? 'bg-dark-lighter hover:bg-dark-lighter/70 cursor-pointer'
                  : 'bg-dark-lighter/50'
              } ${isSelected ? 'ring-2 ring-red-500' : ''} ${isBundled && !isSelected ? 'ring-2 ring-red-500/50 bg-red-500/10' : ''}`}
              onClick={() => canSelect && handleToggleIssue(issue.id)}
            >
              {/* Checkbox */}
              {canSelect && (
                <input
                  type="checkbox"
                  checked={isSelected || isBundled}
                  onChange={() => handleToggleIssue(issue.id)}
                  className={`w-5 h-5 rounded border-gray-600 text-red-500 focus:ring-red-500 ${isBundled && !isSelected ? 'opacity-50' : ''}`}
                />
              )}

              {/* Status Icon */}
              <div className="flex-shrink-0">
                {getStatusIcon(issue.status)}
              </div>

              {/* Cover thumbnail */}
              {issue.cover_image && (
                <div className="flex-shrink-0 w-10 h-14 overflow-hidden rounded">
                  <img
                    src={issue.cover_image}
                    alt={`Issue #${issue.issue_number}`}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </div>
              )}

              {/* Issue Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <span className="font-medium">
                    {issue.title || `Issue #${issue.issue_number || '?'}`}
                  </span>
                  {issue.source && (
                    <span className="text-xs px-2 py-0.5 bg-red-500/20 text-red-400 rounded-full">
                      {issue.source.replace(' (bundle)', '')}
                    </span>
                  )}
                  {bundleCount > 1 && (
                    <span
                      className="text-xs px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded-full flex items-center gap-1"
                      title={issue.bundle_title || `${bundleCount} issues comparten la misma descarga`}
                    >
                      <FaBox className="text-[9px]" />
                      Bundle ({bundleCount} issues)
                    </span>
                  )}
                </div>

                {/* Download URL */}
                {issue.download_url ? (
                  <div className="flex items-center gap-2 mt-1">
                    {/* Link status indicator */}
                    {issue.link_status === 'shortener' && (
                      <span className="text-xs px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 rounded flex items-center gap-1" title="Link acortado (ouo.io) - se resuelve al descargar">
                        <FaLink className="text-[9px]" />
                        Shortener
                      </span>
                    )}
                    {issue.link_status === 'needs_captcha' && (
                      <span className="text-xs px-1.5 py-0.5 bg-orange-500/20 text-orange-400 rounded flex items-center gap-1" title="Requiere resolver captcha manualmente">
                        <FaLock className="text-[9px]" />
                        Captcha
                      </span>
                    )}
                    <a
                      href={issue.download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <FaExternalLinkAlt className="text-[10px]" />
                      <span className="truncate max-w-xs">{issue.download_url}</span>
                    </a>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        copyToClipboard(issue.download_url, issue.issue_number);
                      }}
                      className="text-gray-400 hover:text-white p-1"
                      title="Copiar URL"
                    >
                      <FaCopy className="text-xs" />
                    </button>
                  </div>
                ) : issue.status === 'pending' && (
                  <div className="text-xs text-yellow-500 mt-1 flex items-center gap-1">
                    <FaExclamationTriangle className="text-[10px]" />
                    <span>Sin link de descarga - Usa "Buscar Fuentes"</span>
                  </div>
                )}

                {/* File size */}
                {issue.file_size && (
                  <div className="text-xs text-gray-500 mt-1">
                    Tamano: {(issue.file_size / (1024 * 1024)).toFixed(2)} MB
                  </div>
                )}

                {/* Error Message */}
                {issue.status === 'error' && issue.error_message && (
                  <div className="flex items-start gap-2 mt-1 text-xs text-red-400">
                    <FaExclamationTriangle className="mt-0.5 flex-shrink-0" />
                    <span>{issue.error_message}</span>
                  </div>
                )}
              </div>

              {/* Status */}
              <div className="flex-shrink-0 flex items-center gap-3">
                <span className={`text-sm ${
                  issue.status === 'downloaded' || issue.status === 'sent' ? 'text-green-500' :
                  issue.status === 'error' ? 'text-red-500' :
                  issue.status === 'downloading' ? 'text-red-500' :
                  'text-gray-400'
                }`}>
                  {getStatusText(issue.status)}
                </span>

                {/* Send to Kindle button - show for downloaded/sent */}
                {(issue.status === 'downloaded' || issue.status === 'sent' || issue.file_path) && (
                  <ComicSendToKindleButton
                    comicId={comicId}
                    issueId={issue.id}
                    sentAt={issue.sent_at}
                    hasFile={!!issue.file_path}
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

      {filteredIssues.length === 0 && (
        <div className="card p-8 text-center">
          <p className="text-gray-400">No hay issues que coincidan con el filtro seleccionado</p>
        </div>
      )}
    </div>
  );
};

export default ComicIssueList;
