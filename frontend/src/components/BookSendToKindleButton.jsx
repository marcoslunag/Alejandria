import { useState } from 'react';
import { bookApi, mangaApi } from '../services/api';
import {
  FaTabletAlt,
  FaSpinner,
  FaCheck,
  FaTimes,
  FaRedo
} from 'react-icons/fa';

/**
 * BookSendToKindleButton Component - Uses STK (Send to Kindle) API for books
 *
 * @param {Object} props
 * @param {number} props.bookId - Book ID
 * @param {number} props.chapterId - Chapter ID to send
 * @param {string|null} props.sentAt - Datetime when it was sent (null if never sent)
 * @param {boolean} props.hasEpub - Whether the EPUB file exists
 * @param {function} props.onSent - Callback when successfully sent
 * @param {string} props.size - Button size: 'sm', 'md', 'lg'
 * @param {boolean} props.showLabel - Whether to show text label
 */
const BookSendToKindleButton = ({
  bookId,
  chapterId,
  sentAt = null,
  hasEpub = false,
  onSent,
  size = 'md',
  showLabel = true
}) => {
  const [status, setStatus] = useState('idle'); // idle, sending, success, error
  const [errorMessage, setErrorMessage] = useState('');

  const handleSend = async (e) => {
    e.stopPropagation(); // Prevent triggering parent click handlers

    if (status === 'sending') return;

    try {
      setStatus('sending');
      setErrorMessage('');

      // Check if STK is authenticated
      const stkStatus = await mangaApi.stkGetStatus();
      if (!stkStatus.data.authenticated) {
        throw new Error('STK no autenticado. Ve a Ajustes para conectar tu cuenta de Amazon.');
      }

      // Send via book API
      const response = await bookApi.sendToKindle(bookId, chapterId);

      if (response.data.success) {
        setStatus('success');
        if (onSent) {
          onSent(chapterId, new Date().toISOString());
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
        'Error de conexion'
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
        disabled={status === 'sending'}
        title={
          errorMessage
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
            status === 'error'
              ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/30'
              : status === 'success' || wasSent
              ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30 border border-green-500/30'
              : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30'
          }
          disabled:opacity-50 disabled:cursor-wait
        `}
      >
        {status === 'sending' ? (
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

export default BookSendToKindleButton;
