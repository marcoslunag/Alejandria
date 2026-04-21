import { Link } from 'react-router-dom';
import { FaStar, FaBook, FaBookReader, FaMask, FaCheck, FaPlus, FaEye, FaEyeSlash, FaEllipsisV } from 'react-icons/fa';
import { useState, useRef, useEffect } from 'react';
import toast from 'react-hot-toast';
import { mangaApi, comicApi, bookApi } from '../services/api';

/**
 * ContentCard - Tarjeta unificada para manga, cómics y libros.
 *
 * Props:
 *   item             - El objeto de datos (manga, comic o book)
 *   type             - 'manga' | 'comic' | 'book'
 *   onAdd            - Callback para añadir a biblioteca
 *   showAddButton    - Mostrar botón de añadir
 */
const READ_STATUS_LABELS = {
  not_started: 'Sin leer',
  reading: 'Leyendo',
  completed: 'Leído',
};

const ContentCard = ({ item, type = 'manga', onAdd, showAddButton = false, onToggleMonitor, onReadingStatusChange }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [isTogglingMonitor, setIsTogglingMonitor] = useState(false);
  const [readingStatus, setReadingStatus] = useState(item.reading_status || 'not_started');
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    setReadingStatus(item.reading_status || 'not_started');
  }, [item.reading_status]);

  useEffect(() => {
    const handleOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    if (menuOpen) document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [menuOpen]);

  const apiMap = { manga: mangaApi, comic: comicApi, book: bookApi };

  const handleSetReadingStatus = async (e, status) => {
    e.preventDefault();
    e.stopPropagation();
    setMenuOpen(false);
    const id = item.library_id || item.id;
    if (!id) return;
    try {
      await apiMap[type].setReadingStatus(id, status);
      setReadingStatus(status);
      onReadingStatusChange?.(id, status);
      toast.success(`"${item.title}" marcado como ${READ_STATUS_LABELS[status].toLowerCase()}`);
    } catch {
      toast.error('Error actualizando estado de lectura');
    }
  };

  const config = {
    manga: {
      accentColor: item.cover_color || '#6b9bd2',
      icon: FaBook,
      hoverTextClass: 'group-hover:text-manga',
      badgeClass: 'bg-manga',
      typeTextClass: 'text-manga',
      typeBgClass: 'bg-manga/10 border border-manga/20',
      addBtnClass: 'btn btn-primary',
      progressGradient: 'from-manga to-manga/60',
      borderTopColor: item.cover_color || '#6b9bd2',
      detailPath: '/manga',
      getLink: () => {
        const id = item.library_id || (item.id && item.id > 0 ? item.id : null);
        return id ? `/manga/${id}` : null;
      },
      getCover: () => item.cover_image || item.cover,
      getScore: () => item.average_score ? (item.average_score / 10).toFixed(1) : null,
      getSubInfo: () => item.genres?.slice(0, 3).map(g => ({ key: g, label: g })) || [],
      getStats: () => {
        const parts = [];
        if (item.average_score) parts.push({ type: 'score', value: (item.average_score / 10).toFixed(1) });
        if (item.chapters_total) parts.push({ type: 'count', label: `${item.chapters_total} tomos` });
        if (item.format) parts.push({ type: 'text', label: item.format });
        return parts;
      },
      getProgress: () => ({
        current: item.downloaded_chapters || 0,
        total: item.chapters_total || 0,
        show: item.in_library && item.downloaded_chapters !== undefined,
      }),
      getStatusBadge: () => item.status ? {
        label: item.status,
        className: item.status === 'RELEASING'
          ? 'bg-manga/20 text-manga border border-manga/30'
          : item.status === 'FINISHED'
            ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
            : 'bg-gray-500/20 text-gray-400',
      } : null,
    },
    comic: {
      accentColor: '#c07a5a',
      icon: FaMask,
      hoverTextClass: 'group-hover:text-comic',
      badgeClass: 'bg-comic',
      typeTextClass: 'text-comic',
      typeBgClass: 'bg-comic/10 border border-comic/20',
      addBtnClass: 'btn bg-comic hover:bg-comic/80 text-white',
      progressGradient: 'from-comic to-comic/60',
      borderTopColor: '#c07a5a',
      detailPath: '/comics',
      getLink: () => {
        const id = item.library_id || item.id;
        return id ? `/comics/${id}` : null;
      },
      getCover: () => item.cover_image,
      getScore: () => null,
      getSubInfo: () => {
        const parts = [];
        if (item.publisher) parts.push({ key: 'pub', label: item.publisher });
        if (item.start_year) parts.push({ key: 'year', label: `${item.start_year}` });
        return parts;
      },
      getStats: () => {
        const total = item.count_of_issues || item.total_issues || '?';
        return [{ type: 'count', label: `${item.downloaded_issues || 0}/${total} issues`, className: 'text-comic' }];
      },
      getProgress: () => ({
        current: item.downloaded_issues || 0,
        total: item.count_of_issues || item.total_issues || 0,
        show: item.in_library && (item.count_of_issues || item.total_issues) > 0,
      }),
      getStatusBadge: () => item.downloaded_issues > 0
        ? { label: 'Descargado', className: 'bg-comic/20 text-comic border border-comic/30' }
        : null,
    },
    book: {
      accentColor: '#7aa67a',
      icon: FaBookReader,
      hoverTextClass: 'group-hover:text-book',
      badgeClass: 'bg-book',
      typeTextClass: 'text-book',
      typeBgClass: 'bg-book/10 border border-book/20',
      addBtnClass: 'btn btn-primary',
      progressGradient: 'from-book to-book/60',
      borderTopColor: '#7aa67a',
      detailPath: '/books',
      getLink: () => {
        const id = item.library_id || item.id;
        return id ? `/books/${id}` : null;
      },
      getCover: () => item.cover_image || item.thumbnail,
      getScore: () => item.average_rating ? item.average_rating.toFixed(1) : null,
      getSubInfo: () => item.authors?.slice(0, 2).map((a, i) => ({ key: i, label: a })) || [],
      getStats: () => {
        const parts = [];
        if (item.average_rating) parts.push({ type: 'score', value: item.average_rating.toFixed(1) });
        if (item.page_count) parts.push({ type: 'count', label: `${item.page_count}p` });
        if (item.language) parts.push({ type: 'text', label: item.language.toUpperCase() });
        return parts;
      },
      getProgress: () => ({
        current: item.downloaded_chapters || 0,
        total: item.total_chapters || 0,
        show: item.in_library && item.total_chapters > 0,
      }),
      getStatusBadge: () => item.downloaded_chapters > 0
        ? { label: 'Descargado', className: 'bg-book/20 text-book border border-book/30' }
        : null,
    },
  };

  const c = config[type];
  const coverUrl = c.getCover();
  const link = c.getLink();
  const score = c.getScore();
  const subInfo = c.getSubInfo();
  const statsList = c.getStats();
  const progress = c.getProgress();
  const statusBadge = c.getStatusBadge();
  const IconComponent = c.icon;

  const handleAdd = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsAdding(true);
    try {
      await onAdd(item);
    } finally {
      setIsAdding(false);
    }
  };

  const handleToggleMonitor = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!onToggleMonitor || isTogglingMonitor) return;
    setIsTogglingMonitor(true);
    try {
      await onToggleMonitor(item);
    } finally {
      setIsTogglingMonitor(false);
    }
  };

  const CardContent = () => (
    <div
      className="card group cursor-pointer transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_12px_40px_rgba(0,0,0,0.6)] relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{ borderTop: `2px solid ${c.borderTopColor}` }}
    >
      {/* Cover Image */}
      <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt={item.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <IconComponent className="text-6xl text-gray-600" />
          </div>
        )}

        {/* Hover overlay with description */}
        {isHovered && item.description && (
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/70 to-transparent flex flex-col justify-end p-4 animate-fade-in">
            <p className="text-sm text-gray-300 line-clamp-3">
              {item.description.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '')}
            </p>
          </div>
        )}

        {/* Status badge */}
        {statusBadge && (
          <div className={`absolute top-2 right-2 px-2 py-1 rounded text-xs font-medium ${statusBadge.className}`}>
            {statusBadge.label}
          </div>
        )}

        {/* Reading status badge */}
        {item.in_library && item.reading_status === 'completed' && (
          <div className="absolute bottom-2 left-0 right-0 flex justify-center pointer-events-none">
            <span className="bg-book/80 text-white text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
              <FaEye className="text-[8px]" /> Leído
            </span>
          </div>
        )}

        {/* In Library / Watchlist indicator */}
        {item.in_library && (
          <div className="absolute top-2 left-2 flex flex-col gap-1">
            <div className={`${c.badgeClass} rounded-full p-1.5`}>
              <FaCheck className="text-white text-xs" />
            </div>
            {onToggleMonitor ? (
              <button
                onClick={handleToggleMonitor}
                disabled={isTogglingMonitor}
                title={item.monitored ? 'Siguiendo — Click para dejar de seguir' : 'No siguiendo — Click para seguir'}
                className={`rounded-full p-1.5 transition-colors ${
                  item.monitored
                    ? `${c.badgeClass} text-white opacity-90 hover:opacity-100`
                    : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                }`}
              >
                {item.monitored
                  ? <FaEye className="text-xs" />
                  : <FaEyeSlash className="text-xs" />
                }
              </button>
            ) : item.monitored !== undefined && (
              <div
                title={item.monitored ? 'Siguiendo' : 'No siguiendo'}
                className={`rounded-full p-1.5 ${
                  item.monitored ? `${c.badgeClass} opacity-80` : 'bg-gray-700'
                }`}
              >
                {item.monitored
                  ? <FaEye className="text-white text-xs" />
                  : <FaEyeSlash className="text-gray-400 text-xs" />
                }
              </div>
            )}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-4">
        {/* Title — Playfair Display */}
        <h3 className={`font-serif font-bold text-lg mb-1 line-clamp-2 ${c.hoverTextClass} transition-colors`}>
          {item.title}
        </h3>

        {/* Subtitle — first subInfo item in type color */}
        {subInfo.length > 0 && (
          <p className={`text-xs font-semibold uppercase tracking-wider mb-2 ${c.typeTextClass}`}>
            {subInfo[0].label}
          </p>
        )}

        {/* Genre badges — remaining subInfo items */}
        {subInfo.length > 1 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {subInfo.slice(1).map((info) => (
              <span
                key={info.key}
                className={`text-[10px] px-2 py-0.5 rounded ${c.typeBgClass} ${c.typeTextClass}`}
              >
                {info.label}
              </span>
            ))}
          </div>
        )}

        {/* Stats row */}
        <div className="flex items-center gap-3 text-sm text-gray-400 mb-2">
          {statsList.map((stat, i) => {
            if (stat.type === 'score') {
              return (
                <div key={i} className="flex items-center gap-1">
                  <FaStar className="text-gold text-xs" />
                  <span className="text-gold font-semibold">{stat.value}</span>
                </div>
              );
            }
            if (stat.type === 'count') {
              return (
                <span key={i} className={stat.className || ''}>
                  {stat.label}
                </span>
              );
            }
            return (
              <span key={i} className="text-xs uppercase">{stat.label}</span>
            );
          })}
        </div>

        {/* Progress bar — gradient, 3px height */}
        {progress.show && progress.total > 0 && (
          <div className="mt-2">
            <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1 font-light">
              <span>{progress.current} de {progress.total}</span>
              <span>{Math.round((progress.current / progress.total) * 100)}%</span>
            </div>
            <div className="w-full bg-dark-base rounded-full h-[3px]">
              <div
                className={`bg-gradient-to-r ${c.progressGradient} h-[3px] rounded-full transition-all`}
                style={{ width: `${(progress.current / progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Add button */}
        {showAddButton && !item.in_library && (
          <button
            onClick={handleAdd}
            disabled={isAdding}
            className={`w-full mt-3 ${c.addBtnClass} flex items-center justify-center gap-2 disabled:opacity-50`}
          >
            <FaPlus />
            {isAdding ? 'Agregando...' : 'Añadir a biblioteca'}
          </button>
        )}

        {/* Reading status quick-set (library items only) */}
        {item.in_library && (
          <div className="flex items-center justify-between mt-3 pt-2 border-t border-dark-lighter">
            <span className={`text-xs ${
              readingStatus === 'completed' ? 'text-book' :
              readingStatus === 'reading' ? 'text-gold' :
              'text-gray-500'
            }`}>
              {READ_STATUS_LABELS[readingStatus]}
            </span>
            <div className="relative" ref={menuRef}>
              <button
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setMenuOpen(v => !v); }}
                className="p-1 text-gray-500 hover:text-white rounded transition-colors"
                title="Cambiar estado de lectura"
              >
                <FaEllipsisV className="text-xs" />
              </button>
              {menuOpen && (
                <div className="absolute bottom-full right-0 mb-1 bg-dark-card border border-dark-lighter rounded-lg shadow-xl z-50 py-1 min-w-[130px]">
                  {Object.entries(READ_STATUS_LABELS).map(([key, label]) => (
                    <button
                      key={key}
                      onClick={(e) => handleSetReadingStatus(e, key)}
                      className={`w-full text-left px-3 py-1.5 text-xs hover:bg-dark-lighter transition-colors ${
                        readingStatus === key ? 'text-white font-medium' : 'text-gray-400'
                      }`}
                    >
                      {readingStatus === key ? '✓ ' : ''}{label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  if (link) {
    return (
      <Link to={link}>
        <CardContent />
      </Link>
    );
  }

  return <CardContent />;
};

export default ContentCard;
