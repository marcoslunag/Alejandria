import { useState, useEffect } from 'react';
import { mangaApi, comicApi } from '../services/api';
import {
  FaTabletAlt,
  FaSpinner,
  FaCheck,
  FaTimes,
  FaRedo,
  FaExclamationTriangle
} from 'react-icons/fa';

/**
 * SendToKindleButton Component - Uses STK (Send to Kindle) API
 *
 * @param {Object} props
 * @param {number} props.chapterId - Chapter ID to send
 * @param {string|null} props.sentAt - Datetime when it was sent (null if never sent)
 * @param {boolean} props.hasEpub - Whether the EPUB file exists
 * @param {function} props.onSent - Callback when successfully sent
 * @param {string} props.size - Button size: 'sm', 'md', 'lg'
 * @param {boolean} props.showLabel - Whether to show text label
 */
const SendToKindleButton = ({
  chapterId,
  sentAt = null,
  hasEpub = false,
  onSent,
  size = 'md',
  showLabel = true,
  comicId = null,
  isComic = false
}) => {
  const [status, setStatus] = useState('idle'); // idle, sending, success, error
  const [errorMessage, setErrorMessage] = useState('');
  // STK proactivo (roadmap #4): si la sesión de Amazon no está disponible,
  // el botón se deshabilita con explicación en vez de lanzar un 409/500.
  const [reauthNeeded, setReauthNeeded] = useState(false);

  useEffect(() => {
    mangaApi.stkGetStatus()
      .then((res) => setReauthNeeded(!!res.data.needs_reauth))
      .catch(() => {});
  }, []);

  const handleSend = async (e) => {
    e.stopPropagation(); // Prevent triggering parent click handlers

    if (status === 'sending') return;

    try {
      setStatus('sending');
      setErrorMessage('');

      // Check if STK is authenticated (recheck: la sesión pudo caducar desde el mount)
      const stkStatus = await mangaApi.stkGetStatus();
      if (stkStatus.data.needs_reauth) {
        throw new Error('Sesión de Amazon no disponible. Reconecta en Ajustes → Amazon Send to Kindle.');
      }

      // Send via STK (manga) or comic API
      const response = isComic && comicId
        ? await comicApi.sendToKindle(comicId, chapterId)
        : await mangaApi.stkSendToKindle(chapterId);

      if (response.data.ok || response.data.success) {
        setStatus('success');
        if (onSent) {
          onSent(chapterId, response.data.sent_at);
        }
        // Reset to idle after 3 seconds to allow resending
        setTimeout(() => setStatus('idle'), 3000);
      } else {
        setStatus('error');
        setErrorMessage(response.data.message || 'Error al enviar');
      }
    } catch (error) {
      setStatus('error');
      setErrorMessage(
        error.response?.data?.detail ||
        error.message ||
        'Error de conexión'
      );
      // Reset error state after 5 seconds
      setTimeout(() => {
        setStatus('idle');
        setErrorMessage('');
      }, 5000);
    }
  };

  // Size classes
  const sizeClasses = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-2 text-sm',
    lg: 'px-4 py-2.5 text-base'
  };

  const iconSize = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base'
  };

  // Don't render if no EPUB
  if (!hasEpub) {
    return null;
  }

  // Format sent date
  const formatSentDate = (dateStr) => {
    if (!dateStr) return null;
    const date = new Date(dateStr);
    return date.toLocaleDateString('es-ES', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const wasSent = sentAt || status === 'success';

  return (
    <div className="inline-flex items-center gap-2">
      <button
        onClick={handleSend}
        disabled={status === 'sending' || reauthNeeded}
        title={
          reauthNeeded
            ? 'Sesión de Amazon no disponible. Reconecta en Ajustes → Amazon Send to Kindle'
            : errorMessage
            ? errorMessage
            : wasSent
            ? `Enviado el ${formatSentDate(sentAt)} - Click para reenviar`
            : 'Enviar a Kindle'
        }
        className={`
          inline-flex items-center gap-1.5 rounded-lg font-medium
          transition-all duration-200
          ${sizeClasses[size]}
          ${
            reauthNeeded
              ? 'bg-gray-500/20 text-gray-400 border border-gray-500/30 cursor-not-allowed'
              : status === 'error'
              ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/30'
              : status === 'success' || wasSent
              ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30 border border-green-500/30'
              : 'bg-orange-500/20 text-orange-400 hover:bg-orange-500/30 border border-orange-500/30'
          }
          disabled:opacity-50 disabled:cursor-wait
        `}
      >
        {reauthNeeded ? (
          <>
            <FaExclamationTriangle className={iconSize[size]} />
            {showLabel && 'Reconectar'}
          </>
        ) : status === 'sending' ? (
          <>
            <FaSpinner className={`animate-spin ${iconSize[size]}`} />
            {showLabel && 'Enviando...'}
          </>
        ) : status === 'success' ? (
          <>
            <FaCheck className={iconSize[size]} />
            {showLabel && 'Enviado'}
          </>
        ) : status === 'error' ? (
          <>
            <FaTimes className={iconSize[size]} />
            {showLabel && 'Error'}
          </>
        ) : wasSent ? (
          <>
            <FaRedo className={iconSize[size]} />
            {showLabel && 'Reenviar'}
          </>
        ) : (
          <>
            <FaTabletAlt className={iconSize[size]} />
            {showLabel && 'Kindle'}
          </>
        )}
      </button>

      {/* Sent indicator */}
      {wasSent && !showLabel && (
        <span
          className="text-green-500"
          title={`Enviado el ${formatSentDate(sentAt)}`}
        >
          <FaCheck className={iconSize[size]} />
        </span>
      )}
    </div>
  );
};

export default SendToKindleButton;
